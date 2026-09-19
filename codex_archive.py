"""Sauvegarde incrémentale Codex, distincte de l'archivage Antigravity."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path

from codex_loader import (
    build_codex_conversation_markdown, conversation_signature, load_codex_messages,
)


def codex_archive_due() -> bool:
    from config import get_archive_frequency, load_config
    mode = get_archive_frequency()
    if mode == "manual":
        return False
    if mode in ("always", "launch"):
        return True
    last = load_config().get("last_codex_archive_ts", 0)
    try:
        last = float(last)
    except (ValueError, TypeError):
        last = 0
    return time.time() - last >= (86400 if mode == "daily" else 604800)


def _atomic_text(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def archive_codex_conversations(convs, destination: Path | None = None) -> tuple[int, int]:
    """Copie les sessions modifiées ; ne supprime jamais les anciennes archives.

    destination est utilisée pour un export isolé/tests. En usage normal :
    <projet>/_archive/codex, ou <racine projets>/_CODEX_HORS_PROJET/_archive/codex.
    Aucun fichier de configuration/authentification Codex n'est copié.
    """
    from config import get_projects_root
    groups = {}
    for conv in convs:
        base = Path(destination) if destination is not None else (conv.project_root or get_projects_root() / "_CODEX_HORS_PROJET") / "_archive" / "codex"
        groups.setdefault(base, []).append(conv)
    copied = failures = 0
    for base, sessions in groups.items():
        try:
            base.mkdir(parents=True, exist_ok=True)
            manifest_path = base / "manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict): manifest = {}
            except (OSError, ValueError):
                manifest = {}
            changed = False
            for conv in sessions:
                try:
                    messages = load_codex_messages(conv)
                    if not messages and (not conv.path or not conv.path.is_file()):
                        failures += 1
                        continue
                    signature = conversation_signature(conv)
                    folder = hashlib.sha256(conv.conv_id.encode()).hexdigest()[:24]
                    store = base / "store" / folder
                    if manifest.get(conv.conv_id) == signature and (store / "conversation.md").is_file():
                        continue
                    store.mkdir(parents=True, exist_ok=True)
                    _atomic_text(store / "metadata.json", json.dumps({
                        "id": conv.conv_id, "title": conv.title, "project": conv.project,
                        "project_root": str(conv.project_root or ""), "cwd": conv.cwd,
                        "archived_in_codex": conv.archived,
                    }, ensure_ascii=False, indent=2))
                    if conv.path and conv.path.is_file():
                        temp = store / "rollout.jsonl.tmp"
                        shutil.copyfile(conv.path, temp)
                        os.replace(temp, store / "rollout.jsonl")
                    _atomic_text(store / "messages.json", json.dumps(messages, ensure_ascii=False, indent=2))
                    _atomic_text(store / "conversation.md", build_codex_conversation_markdown(conv))
                    manifest[conv.conv_id] = signature
                    copied += 1
                    changed = True
                except (OSError, ValueError):
                    failures += 1
            if changed or not (base / "conversations.zip").is_file():
                temp_zip = base / "conversations.zip.tmp"
                with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as archive:
                    for path in sorted((base / "store").rglob("*")):
                        if path.is_file() and not path.name.endswith(".tmp"):
                            archive.write(path, path.relative_to(base))
                os.replace(temp_zip, base / "conversations.zip")
                # Le manifeste n'est publié qu'après le ZIP ; un échec sera réessayé.
                _atomic_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        except (OSError, ValueError, zipfile.BadZipFile):
            failures += 1
    return copied, failures
