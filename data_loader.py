"""data_loader.py — Chargement complet et fidèle des données Antigravity.

Extrait les vrais titres officiels, workspaces, dates de dernière activité
depuis le fichier protobuf agyhub_summaries_proto.pb et les transcripts,
permet la suppression en cascade et le chargement des messages de chat.
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from config import get_projects_root, get_antigravity_root


def get_paths():
    projects_root = get_projects_root()
    antigravity_root = get_antigravity_root()
    brain_dir = antigravity_root / "brain"
    conversations_dir = antigravity_root / "conversations"
    summaries_pb = antigravity_root / "agyhub_summaries_proto.pb"
    return projects_root, antigravity_root, brain_dir, conversations_dir, summaries_pb


# -----------------------------------------------------------------
# Décodage Protobuf Wire-Format léger
# -----------------------------------------------------------------
def _decode_varint(data: bytes, pos: int):
    res = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        res |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return res, pos


def _parse_proto_fields(data: bytes):
    """Parse les champs protobuf d'un niveau donné {field_num: [(wire_type, val), ...]}"""
    fields = {}
    pos = 0
    n = len(data)
    while pos < n:
        try:
            tag, pos = _decode_varint(data, pos)
        except Exception:
            break
        wire_type = tag & 7
        field_num = tag >> 3

        if wire_type == 0:  # Varint
            val, pos = _decode_varint(data, pos)
        elif wire_type == 1:  # 64-bit
            if pos + 8 > n:
                break
            val = data[pos : pos + 8]
            pos += 8
        elif wire_type == 2:  # Length-delimited (string / embedded message)
            length, pos = _decode_varint(data, pos)
            if pos + length > n:
                break
            val = data[pos : pos + length]
            pos += length
        elif wire_type == 5:  # 32-bit
            if pos + 4 > n:
                break
            val = data[pos : pos + 4]
            pos += 4
        else:
            break

        fields.setdefault(field_num, []).append((wire_type, val))
    return fields


def _extract_proto_metadata():
    """Extrait pour chaque conversation son titre officiel et son workspace
    depuis agyhub_summaries_proto.pb.
    Retourne {conv_id: {'title': str, 'workspace': str}}
    """
    _, _, _, _, summaries_pb = get_paths()
    if not summaries_pb.is_file():
        return {}

    try:
        data = summaries_pb.read_bytes()
    except Exception:
        return {}

    top = _parse_proto_fields(data)
    entries = top.get(1, [])  # Field 1 = repeated conversation entries
    results = {}

    for _, raw_entry in entries:
        f = _parse_proto_fields(raw_entry)
        cid = None
        if 1 in f:
            try:
                cid = f[1][0][1].decode("utf-8", errors="ignore").strip()
            except Exception:
                pass

        if not cid or len(cid) != 36:
            continue

        title = ""
        workspace = ""

        # Field 2 = submessage avec title, workspace, etc.
        if 2 in f:
            sub = _parse_proto_fields(f[2][0][1])
            # Field 1 = Titre officiel
            if 1 in sub:
                try:
                    title = sub[1][0][1].decode("utf-8", errors="ignore").strip()
                except Exception:
                    pass

            # Extraction des chaînes file:///
            for _, val_list in sub.items():
                for wtype, v in val_list:
                    if wtype == 2:
                        try:
                            s = v.decode("utf-8", errors="ignore")
                            if "file:///" in s:
                                for part in s.split("\x00"):
                                    if "file:///" in part:
                                        idx = part.find("file:///")
                                        raw_ws = part[idx:]
                                        clean_ws = unquote(raw_ws.replace("file:///", "")).replace("/", "\\")
                                        if len(clean_ws) >= 2 and clean_ws[1] == ":":
                                            clean_ws = clean_ws[0].upper() + clean_ws[1:]
                                        if not workspace or "DEV" in clean_ws.upper():
                                            workspace = clean_ws
                        except Exception:
                            pass
                        # Sous-message imbriqué
                        try:
                            nested = _parse_proto_fields(v)
                            for _, nval_list in nested.items():
                                for nwtype, nv in nval_list:
                                    if nwtype == 2:
                                        ns = nv.decode("utf-8", errors="ignore")
                                        if "file:///" in ns:
                                            idx = ns.find("file:///")
                                            raw_ws = ns[idx:]
                                            clean_ws = unquote(raw_ws.replace("file:///", "")).replace("/", "\\")
                                            if len(clean_ws) >= 2 and clean_ws[1] == ":":
                                                clean_ws = clean_ws[0].upper() + clean_ws[1:]
                                            if not workspace or "DEV" in clean_ws.upper():
                                                workspace = clean_ws
                        except Exception:
                            pass

        results[cid] = {"title": title, "workspace": workspace}

    return results


# -----------------------------------------------------------------
# Timestamp relatif
# -----------------------------------------------------------------
def relative_time(dt: datetime | None) -> str:
    """Convertit un datetime UTC en chaîne relative (ex. 3h, 9d, 15d)."""
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "now"
    if seconds < 60:
        return "now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = seconds // 3600
    if hours < 24:
        return f"{hours}h"
    days = delta.days
    if days < 30:
        return f"{days}d"
    months = days // 30
    if months < 12:
        return f"{months}mo"
    years = days // 365
    return f"{years}y"


# -----------------------------------------------------------------
# Mappage Workspace vers Projet
# -----------------------------------------------------------------
def workspace_to_project(workspace_path: str) -> str:
    """Mappe un chemin workspace vers le nom du sous-dossier projet."""
    if not workspace_path:
        return ""
    ws = workspace_path.rstrip("\\/")
    projects_root, _, _, _, _ = get_paths()
    dev = str(projects_root).replace("/", "\\")
    if ws.upper().startswith(dev.upper()):
        remainder = ws[len(dev) :].lstrip("\\/")
        if remainder:
            return remainder.split("\\")[0].split("/")[0]
    return Path(ws).name


# -----------------------------------------------------------------
# Date & Titre de repli depuis transcript
# -----------------------------------------------------------------
def get_transcript_info(conv_id: str):
    """Retourne (fallback_title, last_datetime)."""
    _, _, brain_dir, _, _ = get_paths()
    transcript = brain_dir / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
    if not transcript.is_file():
        transcript = brain_dir / conv_id / ".system_generated" / "logs" / "transcript_full.jsonl"
    if not transcript.is_file():
        return conv_id[:12], None

    first_user_title = ""
    last_ts_str = None

    try:
        with transcript.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                stype = obj.get("type")
                source = obj.get("source")
                ts = obj.get("created_at")
                if ts:
                    last_ts_str = ts

                if not first_user_title and stype == "USER_INPUT" and source == "USER_EXPLICIT":
                    raw = obj.get("content", "").strip()
                    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.DOTALL)
                    txt = m.group(1).strip() if m else raw
                    txt = re.sub(r"<[^>]+>", "", txt).strip()
                    if txt and not txt.startswith("The following is a summary"):
                        first_line = txt.splitlines()[0].strip()
                        first_user_title = first_line[:80]
    except Exception:
        pass

    dt = None
    if last_ts_str:
        try:
            dt = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
        except Exception:
            pass

    return first_user_title or conv_id[:12], dt


# -----------------------------------------------------------------
# Structure ConversationInfo
# -----------------------------------------------------------------
class ConversationInfo:
    __slots__ = (
        "conv_id",
        "title",
        "project",
        "workspace",
        "last_activity",
        "rel_time",
    )

    def __init__(
        self,
        conv_id: str,
        title: str,
        project: str,
        workspace: str,
        last_activity: datetime | None,
    ):
        self.conv_id = conv_id
        self.title = title
        self.project = project
        self.workspace = workspace
        self.last_activity = last_activity
        self.rel_time = relative_time(last_activity)


# -----------------------------------------------------------------
# Construction de la carte des projets & conversations
# -----------------------------------------------------------------
def build_project_map():
    """Retourne (project_convs, all_sorted).
    project_convs: {nom_projet: [ConversationInfo, ...]}
    all_sorted: [ConversationInfo, ...] triées par date décroissante
    """
    projects_root, _, brain_dir, conversations_dir, _ = get_paths()
    proto_meta = _extract_proto_metadata()

    # Lister les dossiers existants dans le répertoire des projets
    projects = set()
    if projects_root.is_dir():
        for p in projects_root.iterdir():
            if p.is_dir():
                projects.add(p.name)

    # Récupérer toutes les conversations réelles
    actual_convs = set()
    if brain_dir.is_dir():
        for d in brain_dir.iterdir():
            if d.is_dir() and len(d.name) == 36:
                actual_convs.add(d.name)
    if conversations_dir.is_dir():
        for f in conversations_dir.iterdir():
            if f.suffix == ".db" and len(f.stem) == 36:
                actual_convs.add(f.stem)

    project_convs = {p: [] for p in sorted(projects, key=str.lower)}
    all_convs = []

    for cid in actual_convs:
        meta = proto_meta.get(cid, {})
        title = meta.get("title", "").strip()
        workspace = meta.get("workspace", "").strip()

        fallback_title, last_dt = get_transcript_info(cid)
        if not title:
            title = fallback_title

        # Vérifier override echange_IA.md si présent
        echange = brain_dir / cid / "echange_IA.md"
        override_proj = None
        if echange.is_file():
            try:
                for line in echange.read_text(encoding="utf-8").splitlines():
                    if line.lower().startswith("project:"):
                        override_proj = line.split(":", 1)[1].strip()
                        break
            except Exception:
                pass

        proj = override_proj if override_proj else workspace_to_project(workspace)

        info = ConversationInfo(cid, title, proj, workspace, last_dt)
        all_convs.append(info)

        if proj:
            if proj not in project_convs:
                project_convs[proj] = []
            project_convs[proj].append(info)

    # Trier par dernière activité
    def sort_key(c: ConversationInfo):
        return c.last_activity or datetime.min.replace(tzinfo=timezone.utc)

    for lst in project_convs.values():
        lst.sort(key=sort_key, reverse=True)

    all_sorted = sorted(all_convs, key=sort_key, reverse=True)

    return project_convs, all_sorted


# -----------------------------------------------------------------
# Suppression en cascade (Projet + toutes ses conversations)
# -----------------------------------------------------------------
def delete_project_cascade(project_name: str, convs_to_delete: list[str]) -> tuple[bool, str]:
    """Supprime le dossier du projet ET toutes les conversations associées."""
    projects_root, _, brain_dir, conversations_dir, _ = get_paths()
    errors = []

    # 1. Supprimer les conversations associées
    for cid in convs_to_delete:
        brain_path = brain_dir / cid
        if brain_path.is_dir():
            try:
                shutil.rmtree(brain_path)
            except Exception as e:
                errors.append(f"Brain {cid[:8]}: {e}")

        db_path = conversations_dir / f"{cid}.db"
        if db_path.is_file():
            try:
                db_path.unlink()
            except Exception as e:
                errors.append(f"DB {cid[:8]}: {e}")

        for ext in (".db-wal", ".db-shm"):
            extra = conversations_dir / f"{cid}{ext}"
            if extra.is_file():
                try:
                    extra.unlink()
                except Exception:
                    pass

    # 2. Supprimer le dossier projet sur disque
    proj_path = projects_root / project_name
    if proj_path.is_dir():
        try:
            shutil.rmtree(proj_path)
        except Exception as e:
            errors.append(f"Dossier projet: {e}")

    if errors:
        return False, "\n".join(errors)
    return True, "Suppression effectuée avec succès."


# -----------------------------------------------------------------
# Chargement des messages d'une conversation pour le Chat Viewer
# -----------------------------------------------------------------
def load_chat_messages(conv_id: str) -> list[dict]:
    """Extrait tous les messages du chat ordonnés pour l'affichage."""
    _, _, brain_dir, _, _ = get_paths()
    transcript = brain_dir / conv_id / ".system_generated" / "logs" / "transcript_full.jsonl"
    if not transcript.is_file():
        transcript = brain_dir / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
    if not transcript.is_file():
        return []

    messages = []

    try:
        with transcript.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                stype = obj.get("type")
                source = obj.get("source")
                content = obj.get("content", "")
                ts = obj.get("created_at", "")
                time_display = ""
                if ts:
                    try:
                        pdt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        time_display = pdt.strftime("%d/%m %H:%M")
                    except Exception:
                        time_display = ts[:16]

                # Message utilisateur
                if stype == "USER_INPUT" and source == "USER_EXPLICIT":
                    raw = content.strip()
                    m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.DOTALL)
                    text = m.group(1).strip() if m else raw
                    text = re.sub(r"<[^>]+>", "", text).strip()
                    if text and not text.startswith("The following is a summary"):
                        messages.append({
                            "role": "user",
                            "text": text,
                            "timestamp": time_display,
                        })

                # Réponse visible du modèle
                elif stype == "PLANNER_RESPONSE" and source == "MODEL":
                    text = content.strip()
                    if text:
                        messages.append({
                            "role": "model",
                            "text": text,
                            "timestamp": time_display,
                        })

    except Exception:
        pass

    return messages
