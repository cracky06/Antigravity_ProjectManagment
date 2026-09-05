"""claude_code_loader.py — Source de données « Claude Code / Claude Desktop ».

Lit les transcripts stockés localement par Claude Code et l'app Claude
Desktop sous `~/.claude/projects/<dossier>/<session>.jsonl` — un format
différent de celui d'Antigravity (protobuf + `transcript.jsonl` propriétaire) :
JSONL avec des lignes typées (`user`, `assistant`, `ai-title`, `attachment`,
`file-history-snapshot`, `queue-operation`, `bridge-session`, …), chaque
message pointant sur son parent via `uuid`/`parentUuid`.

Portée v1 (lecture seule) : parcourir projets/conversations et afficher le
dialogue (texte des blocs `text` des messages `user`/`assistant`). Pas
d'export, pas d'indexation recherche, pas de déplacement/suppression — cf.
`data_loader.py` pour ces fonctionnalités côté Antigravity, non répliquées
ici pour l'instant.

Un « projet » = un dossier sous `~/.claude/projects/` ; son nom affiché est
le dernier segment du `cwd` le plus fréquent parmi ses sessions (le nom de
dossier lui-même est un slug illisible, ex. `e--Dev-Naturalchimie2`).
Une « conversation » = un fichier `.jsonl` (une session) ; son titre est le
dernier événement `ai-title` rencontré, à défaut le début du premier message
utilisateur.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("antigravity_manager.claude_code_loader")

_ENTRYPOINT_LABELS = {
    "claude-vscode": "VS Code",
    "claude-desktop": "Desktop",
}


def get_claude_projects_root() -> Path:
    """Racine des transcripts Claude Code/Desktop : `~/.claude/projects/`."""
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())
    return home / ".claude" / "projects"


def _decode_folder_name(folder: str) -> str:
    """Repli d'affichage quand aucune ligne de la session n'a de `cwd`
    (ex. session « teleported-from » démarrée ailleurs) : le nom du dossier
    encode le chemin d'origine avec des tirets à la place des séparateurs
    (ex. `e--Dev-MCP-Multi-AI`), un décodage exact est ambigu (le nom du
    projet peut lui-même contenir des tirets). On ne fait qu'un nettoyage
    approximatif pour rester lisible, avec un préfixe explicite."""
    cleaned = folder.lstrip("-") or folder
    return f"(sans dossier local) {cleaned}"


@dataclass
class ClaudeConv:
    """Une session (un fichier `.jsonl`)."""

    conv_id: str            # nom de fichier sans extension (uuid de session)
    project: str            # nom du projet affiché (dernier segment du cwd)
    path: Path               # chemin du .jsonl
    title: str = ""
    last_dt: datetime | None = None
    entrypoints: set[str] = field(default_factory=set)
    project_root: Path | None = None   # cwd réel (racine du dossier de code)

    @property
    def origin_label(self) -> str:
        labels = sorted(_ENTRYPOINT_LABELS.get(e, e) for e in self.entrypoints)
        return " + ".join(labels) if labels else ""


def _iter_jsonl(path: Path):
    """Lit un .jsonl ligne à ligne, ignore les lignes corrompues sans planter."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError as exc:
        logger.warning("Lecture impossible de %s : %s", path, exc)


def _first_user_text(entries: list[dict]) -> str:
    for d in entries:
        if d.get("type") != "user" or d.get("isSidechain"):
            continue
        msg = d.get("message") or {}
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = (block.get("text") or "").strip()
                # Filtre les blocs système injectés (ex. <ide_opened_file>...)
                if text and not text.startswith("<"):
                    return text
        # content peut aussi être une simple chaîne
        if isinstance(msg.get("content"), str) and msg["content"].strip():
            return msg["content"].strip()
    return ""


def _scan_session(path: Path) -> ClaudeConv | None:
    """Parse un fichier .jsonl et en extrait les métadonnées de session."""
    entries = list(_iter_jsonl(path))
    if not entries:
        return None

    cwds = Counter()
    entrypoints: set[str] = set()
    ai_title = ""
    last_ts: str | None = None

    for d in entries:
        cwd = d.get("cwd")
        if cwd:
            cwds[cwd] += 1
        ep = d.get("entrypoint")
        if ep:
            entrypoints.add(ep)
        if d.get("type") == "ai-title" and d.get("aiTitle"):
            ai_title = d["aiTitle"]
        ts = d.get("timestamp")
        if ts and (last_ts is None or ts > last_ts):
            last_ts = ts

    if not cwds:
        # Aucun `cwd` dans les métadonnées (ex. session « teleported-from »,
        # démarrée sur une autre machine/interface) : on ne la jette plus
        # silencieusement — si elle a un vrai dialogue, on la rattache au nom
        # du dossier parent (repli imparfait mais visible plutôt que perdue).
        if not _first_user_text(entries):
            return None  # vraiment vide (queue-operation seule, etc.)
        project_name = _decode_folder_name(path.parent.name)
        project_path = None
    else:
        project_path = cwds.most_common(1)[0][0]
        project_name = Path(project_path.replace("\\", "/")).name

    title = ai_title or _first_user_text(entries)[:80]

    last_dt = None
    if last_ts:
        try:
            last_dt = datetime.strptime(last_ts[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            last_dt = None

    return ClaudeConv(
        conv_id=path.stem,
        project=project_name,
        path=path,
        title=title,
        last_dt=last_dt,
        entrypoints=entrypoints,
        project_root=Path(project_path) if project_path else None,
    )


def build_claude_project_map(root: Path | None = None) -> dict[str, list[ClaudeConv]]:
    """Scanne `~/.claude/projects/` et regroupe les sessions par projet.

    Retourne {nom_projet: [ClaudeConv, ...]}, trié par date de dernière
    activité décroissante au sein de chaque projet. Les dossiers/fichiers
    illisibles ou vides sont ignorés silencieusement (ne bloquent pas le
    scan des autres).
    """
    root = root or get_claude_projects_root()
    result: dict[str, list[ClaudeConv]] = {}
    if not root.is_dir():
        return result

    try:
        project_dirs = [d for d in root.iterdir() if d.is_dir()]
    except OSError as exc:
        logger.warning("Scan impossible de %s : %s", root, exc)
        return result

    for d in project_dirs:
        try:
            jsonl_files = sorted(d.glob("*.jsonl"))
        except OSError:
            continue
        for f in jsonl_files:
            conv = _scan_session(f)
            if conv is None:
                continue
            result.setdefault(conv.project, []).append(conv)

    for convs in result.values():
        convs.sort(key=lambda c: c.last_dt or datetime.min, reverse=True)

    return result


def load_claude_messages(conv_path: Path) -> list[dict]:
    """Extrait le dialogue exploitable d'une session : liste de
    {"role": "user"|"assistant", "text": str, "timestamp": str, "epoch": float}.

    Ne garde que les blocs `text` (le `thinking` et les `tool_use`/
    `tool_result` sont du bruit pour une lecture — cf. portée v1 dans le
    docstring du module). Les messages du fil latéral (`isSidechain`) sont
    exclus ; l'ordre suit le timestamp (fiable et monotone, contrairement au
    chaînage `parentUuid` qui peut avoir des trous).
    """
    entries = list(_iter_jsonl(conv_path))
    messages: list[dict] = []

    for d in entries:
        if d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
            continue
        msg = d.get("message") or {}
        role = msg.get("role") or d.get("type")
        content = msg.get("content")

        texts: list[str] = []
        if isinstance(content, str):
            if content.strip():
                texts.append(content.strip())
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = (block.get("text") or "").strip()
                    if t and not t.startswith("<ide_"):
                        texts.append(t)
        if not texts:
            continue

        ts = d.get("timestamp", "")
        epoch = 0.0
        if ts:
            try:
                epoch = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
            except ValueError:
                epoch = 0.0

        messages.append({
            "role": role,
            "text": "\n\n".join(texts),
            "timestamp": ts[11:16] if len(ts) >= 16 else ts,  # HH:MM
            "epoch": epoch,
        })

    # Le docstring promet un ordre par timestamp — les lignes du .jsonl sont
    # normalement déjà chronologiques, mais on ne s'y fie pas aveuglément
    # (fichier reconstruit, session fusionnée, etc.).
    messages.sort(key=lambda m: m["epoch"])
    return messages


# --- Export Markdown (v2.5) --------------------------------------------------
# Parité avec l'export Antigravity (data_loader.build_conversation_markdown /
# export_conversation_to_project / export_conversation_to_path), en plus
# simple : pas d'images à corréler ici (Claude Code ne génère pas d'images
# dans ces transcripts). Réutilise `_slugify` / `_sanitize_message_text` de
# data_loader plutôt que de les dupliquer.
def default_claude_export_filename(conv: "ClaudeConv") -> str:
    """Nom de fichier proposé : <date>_<titre-slug>_<id8>.md."""
    from data_loader import _slugify

    date_part = conv.last_dt.strftime("%Y%m%d") if conv.last_dt else "nodate"
    slug = _slugify(conv.title or conv.conv_id[:12])
    return f"{date_part}_{slug}_{conv.conv_id[:8]}.md"


def build_claude_conversation_markdown(conv: "ClaudeConv") -> str:
    """Construit le document Markdown complet d'une conversation Claude Code.

    En-tête (titre / projet / origine / date / ID) + messages
    (### 👤 Utilisateur / ### ✳️ Claude).
    """
    from data_loader import _sanitize_message_text

    date_str = conv.last_dt.strftime("%Y-%m-%d %H:%M") if conv.last_dt else "date inconnue"
    lines: list[str] = [
        f"# {conv.title or conv.conv_id[:12]}",
        "",
        f"- **Projet :** {conv.project or '(aucun)'}",
        f"- **Origine :** {conv.origin_label or 'inconnue'}",
        f"- **Dernière activité :** {date_str}",
        f"- **ID de session :** `{conv.conv_id}`",
        f"- **Exporté le :** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
    ]

    messages = load_claude_messages(conv.path)
    if not messages:
        lines.append("*Aucun message textuel dans cette session.*")
        return "\n".join(lines)

    for m in messages:
        is_user = m.get("role") == "user"
        heading = "### 👤 Utilisateur" if is_user else "### ✳️ Claude"
        ep = m.get("epoch") or 0.0
        ts_full = datetime.fromtimestamp(ep).strftime("%Y-%m-%d %H:%M") if ep else ""
        text = _sanitize_message_text((m.get("text", "") or "").rstrip(), conv.project_root)
        lines.append(f"{heading}{f' — {ts_full}' if ts_full else ''}")
        lines.append("")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def _write_claude_export(conv: "ClaudeConv", out_path: Path) -> tuple[bool, str]:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        md = build_claude_conversation_markdown(conv)
        out_path.write_text(md, encoding="utf-8")
        logger.debug("Conversation Claude Code %s exportée -> %s", conv.conv_id, out_path)
        return True, str(out_path)
    except Exception as exc:
        logger.warning("Échec export vers %s pour %s : %s", out_path, conv.conv_id, exc)
        return False, f"Échec de l'export : {exc}"


def export_claude_conversation_to_project(conv: "ClaudeConv") -> tuple[bool, str]:
    """Écrit l'export dans `<project_root>/_conversations/` (le vrai dossier
    de code du projet, puisqu'un projet Claude Code n'a pas de « racine des
    projets » centralisée comme Antigravity)."""
    if not conv.project_root:
        return False, "Racine de projet inconnue pour cette conversation."
    out_path = conv.project_root / "_conversations" / default_claude_export_filename(conv)
    return _write_claude_export(conv, out_path)


def export_claude_conversation_to_path(conv: "ClaudeConv", out_path: str | Path) -> tuple[bool, str]:
    """Écrit l'export Markdown à l'emplacement choisi par l'utilisateur."""
    return _write_claude_export(conv, Path(out_path))
