"""archive.py — Archivage automatique et incrémental des conversations Antigravity.

But : anticiper les disparitions de conversations (réinitialisation de l'index
`agyhub_summaries_proto.pb`, purge, corruption, suppression accidentelle…) en
gardant, dans le dossier de chaque projet, une copie de ses conversations.

Emplacement (par projet) :
    <projects_root>/<projet>/_archive/
        store/<conv_id>/…          copie EN CLAIR, incrémentale, jamais purgée
        conversations.zip          régénéré depuis store/ (écriture atomique)
        manifest.json              {conv_id: {chemin_relatif: [mtime_ns, size]}}

Les conversations « hors projet » vont sous
    <projects_root>/_ANTIGRAVITY_HORS_PROJET/_archive/…

Contenu archivé par conversation (sous `store/<conv_id>/`) :
    <conv_id>.db (+ .pb, -wal, -shm si présents)   — brut, restaurable
    brain/…                                         — artéfacts SANS les images
    <conv_id>.md                                    — export Markdown lisible

Règles :
  - INCRÉMENTAL : une conversation n'est recopiée que si un couple (mtime, size)
    d'un de ses fichiers source a changé, ou si elle est nouvelle.
  - JAMAIS DE SUPPRESSION : une conversation entrée dans `store/` y reste, même
    si Antigravity ne la connaît plus. On ne conserve qu'UNE version (l'actuelle).
  - Seuls les projets ayant au moins une conversation nouvelle ou modifiée voient
    leur `conversations.zip` régénéré.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import zipfile
from pathlib import Path

from config import get_projects_root
from data_loader import (
    _IMAGE_EXTS,
    _find_brain_path,
    get_paths,
    build_conversation_markdown,
)

logger = logging.getLogger("antigravity_manager.archive")

#: nom du dossier d'archive créé dans chaque projet
ARCHIVE_DIRNAME = "_archive"
#: projet fictif pour les conversations sans projet rattaché
NO_PROJECT_BUCKET = "_ANTIGRAVITY_HORS_PROJET"
#: fichiers annexes du .db SQLite à copier s'ils existent
_DB_SIDECARS = ("-wal", "-shm")


# ---------------------------------------------------------------------------
# Localisation des fichiers source d'une conversation
# ---------------------------------------------------------------------------
def _find_conv_db(conv_id: str) -> Path | None:
    """Fichier `conversations/<conv_id>.db` (ou `.pb`) le plus pertinent."""
    _, antigravity_root, _, _, _ = get_paths()
    gemini_parent = antigravity_root.parent
    for sub in ("antigravity-ide", "antigravity", "antigravity-backup"):
        for ext in (".db", ".pb"):
            cand = gemini_parent / sub / "conversations" / f"{conv_id}{ext}"
            if cand.is_file():
                return cand
    return None


def _iter_source_files(conv_id: str):
    """Itère (chemin_absolu, chemin_relatif_dans_store) des fichiers à archiver.

    Exclut les images des `brain/` (elles peuvent peser des centaines de Mo).
    """
    db = _find_conv_db(conv_id)
    if db is not None:
        yield db, db.name
        for sc in _DB_SIDECARS:
            side = db.with_name(db.name + sc)
            if side.is_file():
                yield side, side.name

    brain = _find_brain_path(conv_id)
    if brain is not None and brain.is_dir():
        for f in brain.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() in _IMAGE_EXTS:
                continue
            rel = Path("brain") / f.relative_to(brain)
            yield f, str(rel).replace("\\", "/")


def _signature(paths) -> dict[str, list[int]]:
    """{chemin_relatif: [mtime_ns, size]} pour la liste (abs, rel) fournie."""
    sig: dict[str, list[int]] = {}
    for abs_path, rel in paths:
        try:
            st = abs_path.stat()
            sig[rel] = [st.st_mtime_ns, st.st_size]
        except OSError:
            continue
    return sig


# ---------------------------------------------------------------------------
# Manifeste par projet
# ---------------------------------------------------------------------------
def _load_manifest(archive_dir: Path) -> dict:
    mf = archive_dir / "manifest.json"
    if not mf.is_file():
        return {}
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Manifeste illisible %s : %s — repart de zéro", mf, exc)
        return {}


def _save_manifest(archive_dir: Path, manifest: dict) -> None:
    mf = archive_dir / "manifest.json"
    tmp = mf.with_name(mf.name + ".tmp")
    try:
        tmp.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        os.replace(tmp, mf)
    except Exception as exc:
        logger.warning("Échec écriture manifeste %s : %s", mf, exc)
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Copie incrémentale d'une conversation dans store/
# ---------------------------------------------------------------------------
def _archive_one_conversation(
    conv_id: str, title: str, project_name: str, store_dir: Path
) -> None:
    """(Re)copie les fichiers source de la conversation dans `store/<conv_id>/`.

    Remplace le contenu existant de ce sous-dossier (on ne garde qu'une version).
    """
    dest = store_dir / conv_id
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)

    for abs_path, rel in _iter_source_files(conv_id):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(abs_path, target)
        except OSError as exc:
            logger.warning("Copie impossible %s -> %s : %s", abs_path, target, exc)

    # Export Markdown SANS copier les images (on passe `images=None` : le .md
    # se contente de lister les noms d'images présents dans le brain). Le brut
    # léger exclut déjà les binaires — l'archive reste petite. Best-effort.
    try:
        md = build_conversation_markdown(
            conv_id, title=title, project=project_name, images=None
        )
        (dest / f"{conv_id}.md").write_text(md, encoding="utf-8")
    except Exception as exc:
        logger.debug("Export MD en échec pour %s : %s", conv_id, exc)


def _rezip_project(archive_dir: Path, store_dir: Path) -> None:
    """Régénère `conversations.zip` depuis `store/`, en écriture atomique."""
    zip_path = archive_dir / "conversations.zip"
    tmp_path = zip_path.with_name(zip_path.name + ".tmp")
    try:
        with zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zf:
            for f in sorted(store_dir.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(store_dir).as_posix())
        os.replace(tmp_path, zip_path)
    except Exception as exc:
        logger.warning("Échec (re)génération %s : %s", zip_path, exc)
        try:
            if tmp_path.is_file():
                tmp_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
def _bucket_for(project: str) -> str:
    return project if project else NO_PROJECT_BUCKET


def archive_all(convs, progress_cb=None) -> dict:
    """Archive (incrémental) toutes les conversations, groupées par projet.

    `convs` : itérable d'objets ayant `.conv_id`, `.title`, `.project`.
    Retourne un récapitulatif {projet: {"updated": int, "total": int}}.
    Seuls les projets ayant au moins une conversation nouvelle/modifiée voient
    leur `store/` touché et leur `conversations.zip` régénéré.
    """
    projects_root = get_projects_root()

    # Regrouper par « bucket » (nom de projet, ou HORS PROJET).
    by_bucket: dict[str, list] = {}
    for c in convs:
        by_bucket.setdefault(_bucket_for(getattr(c, "project", "") or ""), []).append(c)

    summary: dict = {}
    buckets = sorted(by_bucket.items())
    for bi, (bucket, items) in enumerate(buckets):
        archive_dir = projects_root / bucket / ARCHIVE_DIRNAME
        store_dir = archive_dir / "store"
        try:
            archive_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Impossible de créer %s : %s — projet ignoré", archive_dir, exc)
            continue

        manifest = _load_manifest(archive_dir)
        updated = 0

        for c in items:
            cid = c.conv_id
            new_sig = _signature(_iter_source_files(cid))

            if not new_sig:
                # Aucun fichier source lisible pour cette conversation :
                #  - jamais archivée -> rien à faire ;
                #  - déjà archivée   -> on LAISSE la copie existante intacte
                #    (règle « jamais de suppression »), on ne la réécrit pas.
                continue

            if manifest.get(cid) == new_sig:
                continue  # sources inchangées

            _archive_one_conversation(cid, getattr(c, "title", "") or "", bucket, store_dir)
            manifest[cid] = new_sig
            updated += 1

        if updated:
            _save_manifest(archive_dir, manifest)
            _rezip_project(archive_dir, store_dir)
            logger.info(
                "Archive %s : %d conversation(s) (re)copiée(s) / %d au total",
                bucket, updated, len(items),
            )

        summary[bucket] = {"updated": updated, "total": len(items)}
        if progress_cb:
            progress_cb(bi + 1, len(buckets), bucket)

    return summary
