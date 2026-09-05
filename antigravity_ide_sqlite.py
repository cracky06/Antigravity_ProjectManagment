"""antigravity_ide_sqlite.py — Lecture des conversations Antigravity IDE au format SQLite.

Contexte : depuis mi-2026, l'Antigravity IDE stocke ses sessions dans
`%USERPROFILE%\\.gemini\\antigravity-ide\\conversations\\<cid>.db` (SQLite).
Pour les sessions « légères » (sans artéfact créé sur disque), AUCUN dossier
`brain/<cid>/` n'est matérialisé — donc `data_loader._find_transcript_file()`
ne trouve rien et la conversation s'affiche vide (titre = cid[:12], 0 message).

Ce module lit le dialogue directement depuis la base `.db`, sans dépendance
externe (protobuf décodé à la main sur le format filaire, stdlib uniquement).

Schéma pertinent de la base :
  steps(idx, step_type, status, ..., step_payload BLOB, ...)
  trajectory_metadata_blob(id, data BLOB)   # id = 'main' : workspace / git

Dans `step_payload` (message protobuf racine) :
  f1  (varint)  step_type (redondant avec la colonne)
  f5  (bytes)   métadonnées ; f5.f1.f1 = epoch Unix (secondes)
  f19 (bytes)   step_type 14 (USER_INPUT) ; f19.f2 = prompt utilisateur épuré
  f20 (bytes)   step_type 15 (MODEL_RESPONSE) ; f20.f1 = réponse visible (Markdown)

step_type retenus pour le dialogue : 14 (user) et 15 (model, si f20.f1 présent).
Tous les autres (9 tool_result, 21 approval, 23 diff, 90/98/99 heartbeats…) sont
du bruit technique et ignorés.

Spécification établie par l'agent Antigravity (il connaît son propre format) puis
validée sur les 33 bases sans `brain/` de la machine : 33 décodées, 0 vide, 0 erreur.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SIBLINGS = ("antigravity-ide", "antigravity", "antigravity-backup")

# step_type => rôle de chat. Le reste est du bruit technique.
_STEP_USER = 14
_STEP_MODEL = 15


def _gemini_parent() -> Path:
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())
    return home / ".gemini"


def find_ide_db(conv_id: str) -> Path | None:
    """Localise `<sub>/conversations/<conv_id>.db` (IDE puis app puis backup)."""
    parent = _gemini_parent()
    for sub in _SIBLINGS:
        cand = parent / sub / "conversations" / f"{conv_id}.db"
        if cand.is_file():
            return cand
    return None


def _decode_proto_fields(data: bytes) -> dict[int, list[tuple[str, Any]]]:
    """Décodeur du format filaire protobuf (varint / length-delimited / fixed).

    Retourne {field_number: [(wire_kind, value), ...]}. Sans schéma : les
    sous-messages restent des `bytes` que l'on re-décode à la demande.
    """
    fields: dict[int, list[tuple[str, Any]]] = {}
    i = 0
    n = len(data)
    while i < n:
        key = 0
        shift = 0
        while i < n:
            b = data[i]
            i += 1
            key |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        fn = key >> 3
        wt = key & 0x7
        if wt == 0:  # varint
            v = 0
            shift = 0
            while i < n:
                b = data[i]
                i += 1
                v |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            fields.setdefault(fn, []).append(("varint", v))
        elif wt == 2:  # length-delimited
            length = 0
            shift = 0
            while i < n:
                b = data[i]
                i += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
            val = data[i : i + length]
            i += length
            fields.setdefault(fn, []).append(("bytes", val))
        elif wt == 1:  # fixed64
            fields.setdefault(fn, []).append(("fixed64", data[i : i + 8]))
            i += 8
        elif wt == 5:  # fixed32
            fields.setdefault(fn, []).append(("fixed32", data[i : i + 4]))
        else:  # wire type inconnu (3/4 groupes dépréciés) : on arrête proprement
            break
    return fields


def _first_bytes(fields: dict[int, list[tuple[str, Any]]], fn: int) -> bytes | None:
    entries = fields.get(fn)
    if not entries:
        return None
    kind, val = entries[0]
    return val if kind == "bytes" else None


def _extract_step_epoch(payload: bytes) -> float:
    """epoch Unix (secondes, float) depuis payload.f5.f1.f1, sinon 0.0."""
    if not payload:
        return 0.0
    f5 = _first_bytes(_decode_proto_fields(payload), 5)
    if f5 is None:
        return 0.0
    f5_1 = _first_bytes(_decode_proto_fields(f5), 1)
    if f5_1 is None:
        return 0.0
    secs = _decode_proto_fields(f5_1).get(1)
    if secs and secs[0][0] == "varint":
        return float(secs[0][1])
    return 0.0


def _sanitize_user_text(raw: str) -> str:
    """Isole le prompt réel des enrobages `<USER_REQUEST>` / métadonnées injectées."""
    if not raw:
        return ""
    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.DOTALL)
    txt = m.group(1).strip() if m else raw
    txt = re.sub(r"<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>", "", txt, flags=re.DOTALL)
    txt = re.sub(r"<SYSTEM_MESSAGE>.*?</SYSTEM_MESSAGE>", "", txt, flags=re.DOTALL)
    txt = re.sub(r"<[^>]+>", "", txt).strip()
    return txt


def _looks_like_context_dump(txt: str) -> bool:
    head = txt.lstrip()[:80].lower()
    return (
        head.startswith("the following is a summary")
        or head.startswith("# resuming from a compaction")
        or head.startswith("# conversation history")
    )


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def extract_workspace(db_path: Path | str) -> str:
    """Chemin du workspace depuis trajectory_metadata_blob(id='main').f1.f1."""
    db_path = Path(db_path)
    try:
        conn = _connect_ro(db_path)
    except Exception:
        return ""
    try:
        row = conn.execute(
            "SELECT data FROM trajectory_metadata_blob WHERE id='main'"
        ).fetchone()
    except Exception:
        return ""
    finally:
        conn.close()
    if not row or not row[0]:
        return ""
    f1 = _first_bytes(_decode_proto_fields(row[0]), 1)
    if f1 is None:
        return ""
    ws = _first_bytes(_decode_proto_fields(f1), 1)
    if ws is None:
        return ""
    val = ws.decode("utf-8", errors="ignore").strip()
    if val.startswith("file:///"):
        val = val[len("file:///") :]
    return val


def load_ide_sqlite_conversation(db_path: Path | str) -> dict:
    """Charge une conversation IDE SQLite.

    Retourne `{title, workspace, last_dt, messages}` où `messages` est une liste
    `{role: 'user'|'model', text, timestamp, epoch}` triée par ordre des steps.
    """
    db_path = Path(db_path)
    result: dict[str, Any] = {"title": "", "workspace": "", "last_dt": None, "messages": []}

    try:
        conn = _connect_ro(db_path)
    except Exception:
        return result

    messages: list[dict] = []
    first_title = ""
    last_epoch = 0.0
    try:
        rows = conn.execute(
            "SELECT idx, step_type, step_payload FROM steps "
            "WHERE step_type IN (?, ?) ORDER BY idx ASC",
            (_STEP_USER, _STEP_MODEL),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    for _idx, stype, payload in rows:
        if not payload:
            continue
        fields = _decode_proto_fields(payload)
        epoch = _extract_step_epoch(payload)
        if epoch > last_epoch:
            last_epoch = epoch
        time_disp = (
            datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%d/%m %H:%M")
            if epoch
            else ""
        )

        if stype == _STEP_USER:
            f19 = _first_bytes(fields, 19)
            if f19 is None:
                continue
            f19_2 = _first_bytes(_decode_proto_fields(f19), 2)
            if f19_2 is None:
                continue
            text = _sanitize_user_text(f19_2.decode("utf-8", errors="ignore"))
            if not text or _looks_like_context_dump(text):
                continue
            if not first_title:
                first_title = text.splitlines()[0].strip()[:80]
            messages.append(
                {"role": "user", "text": text, "timestamp": time_disp, "epoch": epoch}
            )

        elif stype == _STEP_MODEL:
            f20 = _first_bytes(fields, 20)
            if f20 is None:
                continue
            f20_1 = _first_bytes(_decode_proto_fields(f20), 1)
            if f20_1 is None:  # le modèle n'a produit aucun texte visible à ce step
                continue
            text = f20_1.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            messages.append(
                {"role": "model", "text": text, "timestamp": time_disp, "epoch": epoch}
            )

    last_dt = (
        datetime.fromtimestamp(last_epoch, tz=timezone.utc) if last_epoch else None
    )
    if last_dt is None:
        # repli : mtime max du .db et de son WAL
        try:
            mt = db_path.stat().st_mtime
            wal = db_path.with_suffix(".db-wal")
            if wal.is_file():
                mt = max(mt, wal.stat().st_mtime)
            last_dt = datetime.fromtimestamp(mt, tz=timezone.utc)
        except Exception:
            pass

    result["title"] = first_title
    result["workspace"] = extract_workspace(db_path)
    result["last_dt"] = last_dt
    result["messages"] = messages
    return result


def ide_sqlite_has_dialogue(db_path: Path | str) -> bool:
    """Vrai si au moins un step user (14) ou model-avec-texte (15) est présent."""
    db_path = Path(db_path)
    try:
        conn = _connect_ro(db_path)
    except Exception:
        return False
    try:
        rows = conn.execute(
            "SELECT step_type, step_payload FROM steps WHERE step_type IN (?, ?)",
            (_STEP_USER, _STEP_MODEL),
        ).fetchall()
    except Exception:
        return False
    finally:
        conn.close()

    for stype, payload in rows:
        if not payload:
            continue
        fields = _decode_proto_fields(payload)
        if stype == _STEP_USER:
            f19 = _first_bytes(fields, 19)
            if f19 and _first_bytes(_decode_proto_fields(f19), 2):
                return True
        elif stype == _STEP_MODEL:
            f20 = _first_bytes(fields, 20)
            if f20 and _first_bytes(_decode_proto_fields(f20), 1):
                return True
    return False
