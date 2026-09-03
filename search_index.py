"""search_index.py — Index de recherche plein-texte (SQLite FTS5).

Objectif : rendre la recherche globale instantanée et permettre trois modes —
« contient » (sous-chaîne), « mots » (FTS5, tolérant aux formes) et « regex ».

L'index vit à côté de config.json (`search_index.db`). Il est reconstructible
à tout moment : ce n'est qu'un cache dérivé des transcripts Antigravity.

Schéma :
    docs(conv_id TEXT PRIMARY KEY, mtime REAL, project TEXT, title TEXT, body TEXT)
    docs_fts  = table virtuelle FTS5 (contentless, synchronisée par triggers)

`mtime` = date de modification du fichier transcript au moment de l'indexation ;
elle sert de clé d'invalidation lors des synchronisations incrémentales.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Callable, Iterable

from config import _get_base_dir
from data_loader import _find_transcript_file, load_chat_messages

# Un handle sqlite ne peut pas être partagé entre threads ; on ouvre une
# connexion par thread appelant.
_LOCAL = threading.local()

SCHEMA_VERSION = 1

ProgressCallback = Callable[[int, int], None]  # (traités, total)


# ---------------------------------------------------------------------------
# Connexion & schéma
# ---------------------------------------------------------------------------
def get_index_path() -> Path:
    """Chemin du fichier d'index, à côté de config.json / de l'exe."""
    return _get_base_dir() / "search_index.db"


def _connect() -> sqlite3.Connection:
    """Connexion sqlite propre au thread courant, schéma garanti."""
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        return conn
    conn = sqlite3.connect(str(get_index_path()))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _ensure_schema(conn)
    _LOCAL.conn = conn
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);

        CREATE TABLE IF NOT EXISTS docs(
            conv_id TEXT PRIMARY KEY,
            mtime   REAL NOT NULL,
            project TEXT,
            title   TEXT,
            body    TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
            body,
            content='docs',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2'
        );

        CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs BEGIN
            INSERT INTO docs_fts(rowid, body) VALUES (new.rowid, new.body);
        END;
        CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs BEGIN
            INSERT INTO docs_fts(docs_fts, rowid, body) VALUES ('delete', old.rowid, old.body);
        END;
        CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON docs BEGIN
            INSERT INTO docs_fts(docs_fts, rowid, body) VALUES ('delete', old.rowid, old.body);
            INSERT INTO docs_fts(rowid, body) VALUES (new.rowid, new.body);
        END;
        """
    )
    cur = conn.execute("SELECT value FROM meta WHERE key='schema_version'")
    row = cur.fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()


def close_thread_connection() -> None:
    """Ferme la connexion du thread courant (à appeler en fin de tâche worker)."""
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        try:
            conn.close()
        finally:
            _LOCAL.conn = None


# ---------------------------------------------------------------------------
# État de santé
# ---------------------------------------------------------------------------
class IndexStatus:
    """Photographie de l'état de l'index pour l'affichage."""

    def __init__(self, ok: bool, message: str, doc_count: int = 0, corrupt: bool = False):
        self.ok = ok
        self.message = message
        self.doc_count = doc_count
        self.corrupt = corrupt

    def __repr__(self) -> str:  # pragma: no cover - debug
        return f"IndexStatus(ok={self.ok}, docs={self.doc_count}, corrupt={self.corrupt})"


def check_status() -> IndexStatus:
    """Vérifie que l'index est ouvrable et cohérent."""
    path = get_index_path()
    if not path.is_file():
        return IndexStatus(False, "Index absent — sera construit au démarrage.", 0)
    try:
        conn = sqlite3.connect(str(path))
        try:
            integ = conn.execute("PRAGMA quick_check").fetchone()
            if not integ or integ[0] != "ok":
                return IndexStatus(False, "Index corrompu (quick_check).", 0, corrupt=True)
            _ensure_schema(conn)
            n = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return IndexStatus(False, f"Index illisible : {exc}", 0, corrupt=True)
    return IndexStatus(True, f"Index prêt — {n} conversation(s).", n)


def drop_index() -> None:
    """Supprime physiquement le fichier d'index et ses annexes WAL/SHM."""
    close_thread_connection()
    base = get_index_path()
    for p in (base, base.with_suffix(base.suffix + "-wal"), base.with_suffix(base.suffix + "-shm")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Construction / synchronisation
# ---------------------------------------------------------------------------
def _concat_body(conv_id: str) -> str:
    """Texte indexable d'une conversation : tous les messages concaténés."""
    messages = load_chat_messages(conv_id)
    return "\n".join(m.get("text", "") for m in messages if m.get("text"))


def _transcript_mtime(conv_id: str) -> float:
    t = _find_transcript_file(conv_id)
    if t and t.is_file():
        try:
            return t.stat().st_mtime
        except OSError:
            return 0.0
    return 0.0


def sync_index(
    convs: Iterable,
    progress_cb: ProgressCallback | None = None,
) -> tuple[int, int]:
    """Synchronisation incrémentale.

    - (ré)indexe toute conversation absente ou dont le transcript a changé
      (mtime différent) ;
    - supprime les entrées orphelines (conversation disparue).

    `convs` est un itérable d'objets ayant .conv_id / .project / .title.
    Retourne (nb_indexées, nb_supprimées).
    """
    conv_list = list(convs)
    conn = _connect()

    existing = dict(conn.execute("SELECT conv_id, mtime FROM docs").fetchall())
    seen: set[str] = set()
    updated = 0
    total = len(conv_list)

    for i, c in enumerate(conv_list):
        cid = c.conv_id
        seen.add(cid)
        mtime = _transcript_mtime(cid)
        if cid in existing and abs(existing[cid] - mtime) < 1e-6 and mtime > 0:
            if progress_cb:
                progress_cb(i + 1, total)
            continue
        body = _concat_body(cid)
        conn.execute(
            """
            INSERT INTO docs(conv_id, mtime, project, title, body)
            VALUES (:cid, :mtime, :project, :title, :body)
            ON CONFLICT(conv_id) DO UPDATE SET
                mtime=excluded.mtime, project=excluded.project,
                title=excluded.title, body=excluded.body
            """,
            {
                "cid": cid,
                "mtime": mtime,
                "project": getattr(c, "project", "") or "",
                "title": getattr(c, "title", "") or "",
                "body": body,
            },
        )
        updated += 1
        if progress_cb:
            progress_cb(i + 1, total)

    orphans = [cid for cid in existing if cid not in seen]
    for cid in orphans:
        conn.execute("DELETE FROM docs WHERE conv_id = ?", (cid,))

    conn.commit()
    return updated, len(orphans)


def rebuild_index(
    convs: Iterable,
    progress_cb: ProgressCallback | None = None,
) -> tuple[int, int]:
    """Reconstruction complète : vide la table puis réindexe tout."""
    conn = _connect()
    conn.execute("DELETE FROM docs")
    conn.commit()
    return sync_index(convs, progress_cb)


# ---------------------------------------------------------------------------
# Recherche
# ---------------------------------------------------------------------------
def _rows_for_scope(conn: sqlite3.Connection, conv_ids: set[str] | None):
    if conv_ids is None:
        yield from conn.execute("SELECT conv_id, body FROM docs")
        return
    # sqlite limite le nombre de paramètres ; on filtre côté Python si la portée
    # est large.
    if len(conv_ids) <= 800:
        placeholders = ",".join("?" * len(conv_ids))
        yield from conn.execute(
            f"SELECT conv_id, body FROM docs WHERE conv_id IN ({placeholders})",
            tuple(conv_ids),
        )
    else:
        for cid, body in conn.execute("SELECT conv_id, body FROM docs"):
            if cid in conv_ids:
                yield cid, body


def search_substring(query: str, conv_ids: set[str] | None = None) -> set[str]:
    """Mode « contient » : sous-chaîne insensible à la casse, via l'index."""
    q = query.strip()
    if not q:
        return set()
    conn = _connect()
    if conv_ids is None:
        # LIKE de SQLite est déjà insensible à la casse pour l'ASCII ; on échappe
        # les métacaractères % et _ pour un test littéral.
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = conn.execute(
            "SELECT conv_id FROM docs WHERE body LIKE ? ESCAPE '\\'",
            (f"%{esc}%",),
        )
        return {r[0] for r in rows}
    ql = q.lower()
    return {cid for cid, body in _rows_for_scope(conn, conv_ids) if ql in body.lower()}


def search_words(query: str, conv_ids: set[str] | None = None, limit: int = 2000) -> set[str]:
    """Mode « mots » : FTS5 MATCH. Chaque terme devient un préfixe (`terme*`)."""
    q = query.strip()
    if not q:
        return set()
    terms = re.findall(r"\w+", q, flags=re.UNICODE)
    if not terms:
        return set()
    match_expr = " AND ".join(f'"{t}"*' for t in terms)
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT d.conv_id
            FROM docs_fts f
            JOIN docs d ON d.rowid = f.rowid
            WHERE docs_fts MATCH ?
            LIMIT ?
            """,
            (match_expr, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        # Expression MATCH invalide -> aucun résultat plutôt qu'une exception.
        return set()
    found = {r[0] for r in rows}
    if conv_ids is not None:
        found &= conv_ids
    return found


def search_regex(
    pattern: str,
    conv_ids: set[str] | None = None,
    ignore_case: bool = True,
) -> set[str]:
    """Mode « regex » : `re.search` sur le corps stocké de chaque conversation.

    Lève `re.error` si le motif est invalide (l'appelant l'affiche).
    """
    if not pattern:
        return set()
    flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)
    rx = re.compile(pattern, flags)  # peut lever re.error : voulu
    conn = _connect()
    out: set[str] = set()
    for cid, body in _rows_for_scope(conn, conv_ids):
        if rx.search(body):
            out.add(cid)
    return out


def search(
    query: str,
    mode: str = "substring",
    conv_ids: set[str] | None = None,
    ignore_case: bool = True,
) -> set[str]:
    """Point d'entrée unique. `mode` ∈ {"substring", "words", "regex"}."""
    if mode == "words":
        return search_words(query, conv_ids)
    if mode == "regex":
        return search_regex(query, conv_ids, ignore_case=ignore_case)
    return search_substring(query, conv_ids)
