"""live_watch.py — Résolution des fichiers à surveiller pour le suivi « live »
d'une conversation ouverte dans le chat viewer.

Le suivi live (bouton 🔴 Suivre) réaffiche la conversation dès qu'un de ses
fichiers source change sur le disque — utile pour observer en direct une
conversation pilotée par un orchestrateur (Claude Orchestrator, Antigravity +
watcher, mode Multi-IA) dont les échanges n'apparaissent pas dans le chat du
client au fil de l'eau.

Ce module ne fait QUE localiser les chemins pertinents ; l'armement du
`QFileSystemWatcher` / `QTimer` et le rendu restent dans `antigravity_manager`.
"""

from __future__ import annotations

from pathlib import Path

from data_loader import (
    _find_transcript_file,
    _find_ide_sqlite_db,
    _find_brain_path,
)


def antigravity_watch_paths(conv_id: str) -> list[Path]:
    """Fichiers dont la modification signale du nouveau contenu pour `conv_id`
    (source Antigravity). Renvoie une liste possiblement vide.

    On surveille, selon ce qui existe :
      - le transcript complet ET partiel (`transcript.jsonl`,
        `transcript_full.jsonl`) — cas normal des sessions avec `brain/` ;
      - la base SQLite `conversations/<id>.db` et son journal WAL — cas des
        conversations IDE légères sans `brain/` ;
      - à défaut, le dossier `brain/<id>/` lui-même (un `QFileSystemWatcher`
        sait surveiller un dossier : tout ajout de fichier le déclenche).
    """
    paths: list[Path] = []

    for allow_partial in (False, True):
        t = _find_transcript_file(conv_id, allow_partial=allow_partial)
        if t is not None and t.is_file() and t not in paths:
            paths.append(t)

    db = _find_ide_sqlite_db(conv_id)
    if db is not None and db.is_file():
        paths.append(db)
        wal = db.with_name(db.name + "-wal")
        if wal.is_file():
            paths.append(wal)

    if not paths:
        brain = _find_brain_path(conv_id)
        if brain is not None and brain.is_dir():
            logs = brain / ".system_generated" / "logs"
            paths.append(logs if logs.is_dir() else brain)

    return paths


def claude_watch_paths(conv_path: str | Path) -> list[Path]:
    """Fichier(s) à surveiller pour une conversation Claude Code / Desktop :
    le transcript `.jsonl` de la session (un seul fichier)."""
    p = Path(conv_path)
    return [p] if p.is_file() else []
