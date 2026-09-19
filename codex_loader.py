"""Lecteur local Codex : métadonnées SQLite, état Desktop et rollouts JSONL.

Les bases sources sont ouvertes en mode ro. Aucun appel réseau ni lecture
d'auth.json. Les formats internes sont tolérés par introspection du schéma.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("antigravity_manager.codex_loader")


@dataclass
class CodexConv:
    conv_id: str
    project: str
    path: Path | None
    title: str = ""
    last_dt: datetime | None = None
    project_root: Path | None = None
    cwd: str = ""
    origin_label: str = "Codex"
    archived: bool = False
    history_path: Path | None = None
    project_id: str = ""


def get_codex_root() -> Path:
    from config import get_codex_root as configured_root
    return configured_root()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _iter_jsonl(path: Path | None):
    if path is None:
        return
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        yield value
                except ValueError:
                    continue  # fichier actif : dernière ligne parfois incomplète
    except OSError as exc:
        logger.debug("Lecture Codex %s : %s", path, exc)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _databases(root: Path, stem: str) -> list[Path]:
    def version(p: Path) -> int:
        match = re.search(r"_(\d+)\.sqlite$", p.name)
        return int(match[1]) if match else 0
    candidates = list(root.glob(f"{stem}_*.sqlite"))
    candidates += list((root / "sqlite").glob(f"{stem}_*.sqlite"))
    return sorted(candidates, key=version, reverse=True)


def _clean_path(value: str) -> str:
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    return value[4:] if value.startswith("\\\\?\\") else value


def _path_key(value: str) -> str:
    return _clean_path(value).replace("\\", "/").rstrip("/").casefold()


def _local_date(value) -> datetime | None:
    try:
        if isinstance(value, (int, float)):
            if value > 1e11:
                value /= 1000
            return datetime.fromtimestamp(value)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _message(role: str, text: str, timestamp, item_id: str = "", phase: str = "") -> dict:
    dt = _local_date(timestamp)
    return {"role": role, "text": text.strip(), "timestamp": dt.strftime("%H:%M") if dt else "",
            "epoch": dt.timestamp() if dt else 0.0, "id": item_id, "phase": phase}


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = str(block.get("type", "")).lower()
        if kind in ("text", "input_text", "output_text"):
            texts.append(str(block.get("text", "")))
        elif kind in ("image", "input_image", "localimage", "local_image"):
            # Ne pas injecter des mégaoctets de base64 dans l'index ou l'export.
            path = block.get("path") or block.get("image_url") or block.get("url")
            if isinstance(path, str) and path and not path.startswith(("data:", "http:" , "https:")):
                texts.append(f"[Image jointe : {path}]")
            else:
                texts.append("[Image jointe]")
        elif kind in ("file", "input_file"):
            texts.append(f"[Fichier joint : {block.get('filename') or block.get('path') or 'fichier'}]")
    return "\n\n".join(texts).strip()


def _from_item(item: dict, timestamp) -> dict | None:
    kind = str(item.get("type", "")).replace("_", "").lower()
    if kind == "usermessage":
        text = _content_text(item.get("content", []))
        role = "user"
    elif kind == "agentmessage":
        text = item.get("text", "")
        role = "assistant"
    else:
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    return _message(role, text, timestamp, str(item.get("id", "")), item.get("phase") or "")


def _load_rollout(path: Path | None) -> list[dict]:
    # Chaque tour choisit une seule représentation : items UI > events > réponses.
    # Cela conserve aussi les anciens tours quand le format évolue en cours de session.
    groups: list[dict] = []
    group = {"items": [], "events": [], "responses": []}
    groups.append(group)
    for ordinal, entry in enumerate(_iter_jsonl(path)):
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        typ = entry.get("type")
        kind = payload.get("type")
        timestamp = entry.get("timestamp", "")
        if typ == "event_msg" and kind == "task_started":
            group = {"items": [], "events": [], "responses": []}
            groups.append(group)
        elif typ == "event_msg" and kind == "item_completed":
            item = payload.get("item")
            msg = _from_item(item, timestamp) if isinstance(item, dict) else None
            if msg:
                group["items"].append(msg)
        elif typ == "event_msg" and kind in ("user_message", "agent_message"):
            text = payload.get("message", "")
            if isinstance(text, str) and text.strip():
                group["events"].append(_message("user" if kind == "user_message" else "assistant", text, timestamp))
        elif typ == "response_item" and kind == "message":
            role = payload.get("role")
            if role not in ("user", "assistant") or payload.get("channel") in ("analysis", "summary"):
                continue
            text = _content_text(payload.get("content", []))
            if role == "user":
                # Ancien format : contexte injecté sous le rôle user.
                for tag in ("environment_context", "permissions", "skills_instructions", "instructions", "system-reminder"):
                    text = re.sub(rf"<{tag}(?:\s[^>]*)?>.*?</{tag}>", "", text, flags=re.S)
                if text.lstrip().startswith(("# AGENTS.md instructions", "<environment_context>", "<turn_aborted>")):
                    continue
            if text.strip():
                group["responses"].append(_message(role, text, timestamp, str(payload.get("id") or ""), payload.get("phase") or ""))
        for values in group.values():
            if values and "_order" not in values[-1]:
                values[-1]["_order"] = ordinal
    result: list[dict] = []
    for group in groups:
        # Choix par rôle : certains anciens tours n'ont que agent_message en events.
        chosen = {role: next((source for source in ("items", "events", "responses")
                             if any(m["role"] == role for m in group[source])), "")
                  for role in ("user", "assistant")}
        messages = [m for source, values in group.items() for m in values if chosen[m["role"]] == source]
        messages.sort(key=lambda m: m["_order"])
        for message in messages:
            message.pop("_order", None)
        result.extend(messages)
    # Les mises à jour d'un item gardent son identifiant : conserver sa dernière
    # version à sa position initiale, sans dédupliquer les vrais messages répétés.
    unique = []
    positions = {}
    for message in result:
        ident = message.get("id")
        if ident and ident in positions:
            unique[positions[ident]] = message
        else:
            if ident: positions[ident] = len(unique)
            unique.append(message)
    return unique


def load_codex_messages(conv: CodexConv) -> list[dict]:
    """Historique visible, sans raisonnement privé ni sorties d'outils.

    Le rollout contient aussi la fin d'un tour encore absent de la projection
    SQLite. S'il existe, il est lu directement ; SQLite sert de repli.
    """
    messages = _load_rollout(conv.path)
    if messages or not conv.history_path:
        return messages
    try:
        conn = _connect_readonly(conv.history_path)
        try:
            rows = conn.execute("SELECT item_json,created_at_ms FROM thread_items WHERE thread_id=? ORDER BY rollout_ordinal", (conv.conv_id,))
            for row in rows:
                try:
                    item = json.loads(row["item_json"])
                    msg = _from_item(item, row["created_at_ms"]) if isinstance(item, dict) else None
                    if msg:
                        messages.append(msg)
                except ValueError:
                    continue
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning("Historique Codex %s : %s", conv.conv_id, exc)
    return messages


def _state_rows(root: Path) -> tuple[list[dict], dict]:
    for db in _databases(root, "state"):
        try:
            conn = _connect_readonly(db)
            try:
                threads = [dict(r) for r in conn.execute("SELECT * FROM threads")]
                projects = {}
                try:
                    for row in conn.execute("SELECT p.id,p.name,r.path FROM projects p LEFT JOIN project_roots r ON p.id=r.project_id ORDER BY r.position"):
                        projects.setdefault(row["id"], {"name": row["name"], "root": row["path"]})
                except sqlite3.Error:
                    pass  # anciennes versions sans tables projects/project_roots
                return threads, projects
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.warning("Métadonnées Codex %s : %s", db, exc)
    return [], {}


def build_codex_project_map(root: Path | None = None) -> dict[str, list[CodexConv]]:
    root = Path(root or get_codex_root())
    if not root.is_dir():
        return {}
    state = _read_json(root / ".codex-global-state.json")
    rows, projects = _state_rows(root)
    local_projects = state.get("local-projects", {})
    if not isinstance(local_projects, dict): local_projects = {}
    for pid, value in local_projects.items():
        if isinstance(value, dict):
            roots = value.get("rootPaths") or []
            projects.setdefault(pid, {"name": value.get("name", ""), "root": roots[0] if roots else None})
    assignments = state.get("thread-project-assignments", {})
    if not isinstance(assignments, dict): assignments = {}
    projectless = set(state.get("projectless-thread-ids") or [])
    histories = _databases(root, "thread_history")
    history = histories[0] if histories else None
    titles = {}
    for entry in _iter_jsonl(root / "session_index.jsonl"):
        titles[entry.get("id")] = entry.get("thread_name") or entry.get("title")
    rollouts = {}
    for folder in ("sessions", "archived_sessions"):
        for path in (root / folder).rglob("*.jsonl"):
            match = re.search(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\.jsonl$", path.name)
            if match:
                rollouts[match[1]] = path
    by_id = {r["id"]: r for r in rows if r.get("id")}
    for cid, path in rollouts.items():
        if cid in by_id:
            continue
        meta = next((e.get("payload", {}) for e in _iter_jsonl(path) if e.get("type") == "session_meta"), {})
        by_id[cid] = {**meta, "id": cid, "rollout_path": str(path), "archived": "archived_sessions" in path.parts}
    result = []
    for cid, row in by_id.items():
        source = row.get("source", "")
        # Les sous-agents techniques ne sont pas des conversations principales.
        if row.get("agent_role") or row.get("agent_path") not in (None, "", "/root") or "subagent" in str(source).lower():
            continue
        raw_path = _clean_path(str(row.get("rollout_path") or ""))
        path = Path(raw_path) if raw_path else None
        if path and not path.is_absolute():
            path = root / path
        if not path or not path.is_file():
            path = rollouts.get(cid)
        cwd = _clean_path(str(row.get("cwd") or ""))
        pid = row.get("project_id") or ""
        assignment = assignments.get(cid)
        # Lors de la migration Desktop, l'affectation legacy peut précéder SQLite.
        if not pid and isinstance(assignment, dict) and assignment.get("projectKind") == "local":
            pid = assignment.get("projectId") or pid
        proj = projects.get(pid) if cid not in projectless else None
        project_root = None
        project_name = ""
        if proj:
            project_name = proj.get("name") or ""
            if proj.get("root"):
                project_root = Path(_clean_path(proj["root"]))
        elif cid not in projectless and cwd:
            matches = [p for p in projects.values() if p.get("root") and
                       (_path_key(cwd) == _path_key(p["root"]) or _path_key(cwd).startswith(_path_key(p["root"]) + "/"))]
            if matches:
                proj = max(matches, key=lambda p: len(p["root"]))
                project_name, project_root = proj["name"], Path(_clean_path(proj["root"]))
            elif cid not in state.get("thread-projectless-output-directories", {}):
                project_root = Path(cwd)
                project_name = cwd.replace("\\", "/").rstrip("/").split("/")[-1]
        label = row.get("originator") or ("Codex IDE" if source == "vscode" else "Codex CLI" if source == "cli" else "Codex")
        dt = _local_date(row.get("updated_at_ms") or row.get("updated_at") or row.get("timestamp"))
        if not dt and path:
            try: dt = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError: pass
        conv = CodexConv(cid, project_name, path, row.get("name") or titles.get(cid) or row.get("title") or "",
                         dt, project_root, cwd, label, bool(row.get("archived")), history, str(pid))
        if not conv.title:
            messages = load_codex_messages(conv)
            if not messages:
                continue
            conv.title = next((m["text"][:100] for m in messages if m["role"] == "user"), cid[:12])
        result.append(conv)
    # Deux dossiers homonymes restent deux projets distincts.
    names: dict[str, set[str]] = {}
    for c in result:
        if c.project:
            names.setdefault(c.project, set()).add(_path_key(str(c.project_root or c.project_id)))
    grouped: dict[str, list[CodexConv]] = {}
    for conv in result:
        if conv.project and len(names[conv.project]) > 1:
            conv.project = f"{conv.project} ({conv.project_root or conv.project_id})"
        grouped.setdefault(conv.project, []).append(conv)
    for values in grouped.values():
        values.sort(key=lambda c: c.last_dt or datetime.min, reverse=True)
    return grouped


def codex_watch_paths(conv: CodexConv) -> list[Path]:
    paths = [conv.path] if conv.path else []
    if conv.history_path:
        paths += [conv.history_path, Path(str(conv.history_path) + "-wal")]
    return paths


def conversation_signature(conv: CodexConv) -> str:
    parts = [conv.title, conv.project]
    for path in codex_watch_paths(conv):
        try:
            st = path.stat()
            parts.append(f"{path}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{path}:absent")
    return "|".join(parts)


def default_codex_export_filename(conv: CodexConv) -> str:
    from data_loader import _slugify
    date = conv.last_dt.strftime("%Y%m%d") if conv.last_dt else "nodate"
    return f"{date}_{_slugify(conv.title or conv.conv_id[:12])}_{conv.conv_id}.md"


def build_codex_conversation_markdown(conv: CodexConv) -> str:
    from data_loader import _sanitize_message_text
    lines = [f"# {conv.title or conv.conv_id}", "", f"- **Source :** {conv.origin_label}",
             f"- **Projet :** {conv.project or '(sans projet)'}", f"- **ID :** `{conv.conv_id}`",
             f"- **Archivée dans Codex :** {'oui' if conv.archived else 'non'}", "", "---", ""]
    for msg in load_codex_messages(conv):
        name = "👤 Utilisateur" if msg["role"] == "user" else "◉ Codex"
        date = datetime.fromtimestamp(msg["epoch"]).strftime("%Y-%m-%d %H:%M") if msg["epoch"] else ""
        lines += [f"### {name} — {date}", "", _sanitize_message_text(msg["text"], conv.project_root), ""]
    return "\n".join(lines)


def export_codex_conversation_to_path(conv: CodexConv, out_path: str | Path) -> tuple[bool, str]:
    path = Path(out_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_codex_conversation_markdown(conv), encoding="utf-8")
        return True, str(path)
    except (OSError, ValueError) as exc:
        return False, f"Échec de l'export : {exc}"


def export_codex_conversation_to_project(conv: CodexConv) -> tuple[bool, str]:
    if not conv.project_root:
        return False, "Racine de projet inconnue pour cette conversation."
    return export_codex_conversation_to_path(conv, conv.project_root / "_conversations" / default_codex_export_filename(conv))


def export_codex_project_conversations(convs, dest_dir: Path | None = None, progress_cb=None) -> tuple[int, int, Path]:
    convs = list(convs)
    if dest_dir is None:
        root = convs[0].project_root if convs else None
        if not root:
            raise ValueError("Racine de projet inconnue et aucun dest_dir fourni.")
        dest_dir = root / "_conversations"
    ok = fail = 0
    for i, conv in enumerate(convs):
        success, _ = export_codex_conversation_to_path(conv, Path(dest_dir) / default_codex_export_filename(conv))
        ok += int(success)
        fail += int(not success)
        if progress_cb:
            progress_cb(i + 1, len(convs), conv.conv_id)
    return ok, fail, Path(dest_dir)
