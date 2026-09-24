"""data_loader.py — Chargement complet et fidèle des données Antigravity.

Extrait les vrais titres officiels, workspaces, dates de dernière activité
depuis le fichier protobuf agyhub_summaries_proto.pb et les transcripts,
permet la suppression en cascade et le chargement des messages de chat.
"""

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from config import get_projects_root, get_antigravity_root, _get_base_dir

# ---------------------------------------------------------------------------
# Journalisation optionnelle
# ---------------------------------------------------------------------------
# Beaucoup de blocs `except Exception: pass` avalent des transcripts malformés
# ou des écritures protobuf ratées sans laisser de trace. On les remonte dans
# un logger silencieux par défaut : posez la variable d'environnement
# ANTIGRAVITY_MANAGER_DEBUG=1 (ou =debug) pour écrire dans data_loader.log,
# à côté de config.json / de l'exe.
logger = logging.getLogger("antigravity_manager.data_loader")

if not logger.handlers:
    _debug_flag = os.environ.get("ANTIGRAVITY_MANAGER_DEBUG", "").strip().lower()
    if _debug_flag in ("1", "true", "yes", "debug", "on"):
        try:
            _log_file = _get_base_dir() / "data_loader.log"
            _handler = logging.FileHandler(_log_file, encoding="utf-8")
            _handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            )
            logger.addHandler(_handler)
            logger.setLevel(logging.DEBUG)
            logger.debug("Journalisation activée -> %s", _log_file)
        except Exception:
            logger.addHandler(logging.NullHandler())
    else:
        logger.addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# Sauvegarde préventive du fichier de métadonnées protobuf
# ---------------------------------------------------------------------------
_PB_BACKUP_KEEP = 5  # nombre de sauvegardes horodatées conservées par fichier


def _backup_pb_file(pb_path: Path) -> Path | None:
    """Copie `pb_path` en `<nom>.bak-YYYYmmdd-HHMMSS` avant toute réécriture.

    Fait une rotation : ne garde que les `_PB_BACKUP_KEEP` sauvegardes les plus
    récentes. Retourne le chemin de la copie créée, ou None si rien n'a été fait.
    """
    try:
        if not pb_path.is_file():
            return None
        # Horodatage à la milliseconde : deux réécritures rapprochées gardent
        # chacune leur sauvegarde.
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
        backup = pb_path.with_name(f"{pb_path.name}.bak-{stamp}")
        if not backup.exists():
            shutil.copy2(pb_path, backup)
            logger.debug("Sauvegarde protobuf créée : %s", backup)

        # Rotation des anciennes sauvegardes.
        pattern = f"{pb_path.name}.bak-*"
        backups = sorted(
            pb_path.parent.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[_PB_BACKUP_KEEP:]:
            try:
                old.unlink()
                logger.debug("Ancienne sauvegarde supprimée : %s", old)
            except OSError as exc:
                logger.warning("Impossible de supprimer %s : %s", old, exc)
        return backup
    except Exception as exc:  # pragma: no cover - la sauvegarde ne doit jamais bloquer
        logger.warning("Échec de la sauvegarde de %s : %s", pb_path, exc)
        return None


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


def _encode_varint(val: int) -> bytes:
    res = bytearray()
    while True:
        b = val & 0x7F
        val >>= 7
        if val:
            res.append(b | 0x80)
        else:
            res.append(b)
            break
    return bytes(res)


def _encode_proto_field(field_num: int, wire_type: int, val: bytes | int) -> bytes:
    tag = (field_num << 3) | wire_type
    header = _encode_varint(tag)
    if wire_type == 0:
        return header + _encode_varint(val)
    elif wire_type == 2:
        return header + _encode_varint(len(val)) + val
    elif wire_type in (1, 5):
        return header + val
    return b""


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


def _clean_path_string(raw: str) -> str:
    """Nettoie et normalise une URL file:/// ou un chemin pour éliminer les délimiteurs protobuf et caractères non imprimables."""
    if not raw:
        return ""
    if "file:///" in raw:
        idx = raw.find("file:///")
        raw = raw[idx + 8 :]

    # Nettoyer les caractères de contrôle, délimiteurs protobuf, etc.
    cleaned = []
    for ch in raw:
        code = ord(ch)
        if code < 32 or code == 127:
            break
        if ch in ('"', "<", ">", "|", "?", "*", "\x00", "\x12", "\x1a"):
            break
        cleaned.append(ch)

    res = "".join(cleaned).strip()
    res = unquote(res).replace("/", "\\")
    # Normalisation lettre de lecteur Windows
    if len(res) >= 2 and res[1] == ":":
        res = res[0].upper() + res[1:]
    return res


def _find_summaries_pb() -> Path | None:
    """Localise agyhub_summaries_proto.pb dans le répertoire configuré ou les dossiers .gemini frères."""
    _, antigravity_root, _, _, summaries_pb = get_paths()
    if summaries_pb.is_file():
        return summaries_pb
    gemini_parent = antigravity_root.parent
    for sibling in ("antigravity", "antigravity-ide", "antigravity-backup"):
        cand = gemini_parent / sibling / "agyhub_summaries_proto.pb"
        if cand.is_file():
            return cand
    return None


def _extract_proto_metadata():
    """Extrait pour chaque conversation son titre officiel et son workspace
    depuis agyhub_summaries_proto.pb.
    Retourne {conv_id: {'title': str, 'workspace': str}}
    """
    summaries_pb = _find_summaries_pb()
    if not summaries_pb or not summaries_pb.is_file():
        return {}

    try:
        data = summaries_pb.read_bytes()
    except Exception as exc:
        logger.warning("Lecture de %s impossible : %s", summaries_pb, exc)
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

            # Extraction prioritaire depuis sub[9] (métadonnées structurées du workspace)
            if 9 in sub:
                for _, v in sub[9]:
                    if isinstance(v, bytes):
                        nested = _parse_proto_fields(v)
                        for k in (1, 2, 7):
                            if k in nested:
                                for _, nv in nested[k]:
                                    if isinstance(nv, bytes):
                                        c = _clean_path_string(nv.decode("utf-8", errors="ignore"))
                                        if c and (not workspace or "DEV" in c.upper()):
                                            workspace = c
                                            break
                            if workspace:
                                break
                    if workspace:
                        break

            # Extraction secondaire depuis sub[17]
            if not workspace and 17 in sub:
                for _, v in sub[17]:
                    if isinstance(v, bytes):
                        nested = _parse_proto_fields(v)
                        for k in (7, 1):
                            if k in nested:
                                for _, nv in nested[k]:
                                    if isinstance(nv, bytes):
                                        c = _clean_path_string(nv.decode("utf-8", errors="ignore"))
                                        if c and (not workspace or "DEV" in c.upper()):
                                            workspace = c
                                            break
                            if workspace:
                                break
                    if workspace:
                        break

            # Repli générique sécurisé sur tous les champs
            if not workspace:
                for _, val_list in sub.items():
                    for wtype, v in val_list:
                        if wtype == 2 and isinstance(v, bytes) and b"file:///" in v:
                            try:
                                s = v.decode("utf-8", errors="ignore")
                                c = _clean_path_string(s)
                                if c:
                                    workspace = c
                                    break
                            except Exception:
                                pass
                    if workspace:
                        break

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
    ws = _clean_path_string(workspace_path).rstrip("\\/`'\",.:; ").strip()
    if not ws:
        return ""

    projects_root, _, _, _, _ = get_paths()
    dev = str(projects_root).replace("/", "\\")
    if ws.upper().startswith(dev.upper()):
        remainder = ws[len(dev) :].lstrip("\\/")
        if remainder:
            candidate = remainder.split("\\")[0].split("/")[0].strip()
            if candidate and candidate.lower() not in ("n", "nlast", "temp", "tmp", "logs", "cache"):
                return candidate

    # Gestion des chemins génériques avec segments reconnus
    parts = Path(ws).parts
    if len(parts) >= 2:
        for i, p in enumerate(parts):
            if p.lower() in ("dev", "projets", "projects", "codemaison", "antigravity", "scripts") and i + 1 < len(parts):
                cand = parts[i + 1].strip().rstrip("`'\",.:; ")
                if cand and cand.lower() not in ("n", "nlast", "temp", "tmp", "logs", "cache"):
                    return cand

    name = Path(ws).name.strip().rstrip("`'\",.:; ")
    if name and name.lower() not in ("n", "nlast", "temp", "tmp", "logs", "cache"):
        return name
    return ""


def _find_brain_path(conv_id: str) -> Path | None:
    """Trouve le dossier brain de la conversation dans le répertoire configuré ou les répertoires frères."""
    _, antigravity_root, brain_dir, _, _ = get_paths()
    candidate = brain_dir / conv_id
    if candidate.is_dir():
        return candidate

    # Recherche dans les autres répertoires .gemini (antigravity-ide, antigravity, antigravity-backup)
    gemini_parent = antigravity_root.parent
    for sibling in ("antigravity-ide", "antigravity", "antigravity-backup"):
        sib_candidate = gemini_parent / sibling / "brain" / conv_id
        if sib_candidate.is_dir():
            return sib_candidate
    return None


#: sous-dossiers de .gemini/ considérés comme des sources « vivantes »
#: (antigravity-backup est une sauvegarde passive : voir _detect_origin)
_LIVE_SUBS = ("antigravity-ide", "antigravity")


def _conv_richness_in(sub: str, gemini_parent: Path, conv_id: str) -> int:
    """Niveau de présence de la conversation dans `.gemini/<sub>/` :
    2 = dossier brain/ (données complètes : transcript, artéfacts),
    1 = seulement un fichier conversations/<cid>.{db,pb} (reliquat / base légère),
    0 = absente.
    """
    base = gemini_parent / sub
    if (base / "brain" / conv_id).is_dir():
        return 2
    conv_dir = base / "conversations"
    if (conv_dir / f"{conv_id}.db").is_file() or (conv_dir / f"{conv_id}.pb").is_file():
        return 1
    return 0


def _detect_origin(conv_id: str) -> str:
    """Origine d'une conversation Antigravity : "ide", "app", "ide+app" ou "".

    Aucune métadonnée de provenance n'existe dans les fichiers (confirmé avec
    l'agent Antigravity) : la seule information fiable est le dossier `.gemini/`
    où résident les données. Règles :
      - le dossier `brain/` (présence de niveau 2) fait autorité : s'il n'est
        que d'un côté, c'est cette origine, même si un `.pb` orphelin traîne
        de l'autre (cas des 3 conversations historiques recopiées) ;
      - "ide+app" seulement si les deux côtés ont le même niveau de présence ;
      - `antigravity-backup` est une sauvegarde passive, jamais une origine à
        lui seul — rattachée à l'app dont elle est l'instantané.
    """
    _, antigravity_root, _, _, _ = get_paths()
    gemini_parent = antigravity_root.parent
    r_ide = _conv_richness_in("antigravity-ide", gemini_parent, conv_id)
    r_app = _conv_richness_in("antigravity", gemini_parent, conv_id)

    if r_ide and r_app:
        if r_ide == r_app:
            return "ide+app"
        return "ide" if r_ide > r_app else "app"
    if r_ide:
        return "ide"
    if r_app:
        return "app"
    if _conv_richness_in("antigravity-backup", gemini_parent, conv_id):
        return "app"
    return ""


def _find_ide_sqlite_db(conv_id: str):
    """Localise `conversations/<conv_id>.db` (Antigravity IDE) si présent.

    Utilisé en repli quand aucun `transcript.jsonl` n'existe : les sessions
    IDE légères n'ont pas de dossier `brain/` mais gardent tout dans SQLite.
    Renvoie un `Path` ou `None`.
    """
    try:
        from antigravity_ide_sqlite import find_ide_db

        return find_ide_db(conv_id)
    except Exception as exc:  # module absent (tests isolés) ou erreur FS
        logger.debug("_find_ide_sqlite_db(%s) : %s", conv_id, exc)
        return None


def _transcript_is_complete(path: Path) -> bool:
    """Vrai si le transcript couvre la conversation depuis le début.

    Quand on rouvre une vieille conversation `.pb` dans Antigravity, l'app crée
    un `transcript.jsonl` ne contenant QUE les nouvelles étapes (la 1re ligne
    a un `step_index` > 0). Un tel transcript est trompeusement court : le vrai
    dialogue est ailleurs (passerelle `language_server`). Un transcript complet
    commence au `step_index` 0.
    """
    try:
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    return int(json.loads(line).get("step_index", 0)) == 0
                except Exception:
                    return True  # pas de step_index : format ancien, on fait confiance
    except OSError:
        pass
    return True


def _find_transcript_file(conv_id: str, *, allow_partial: bool = False) -> Path | None:
    """Trouve le fichier transcript d'une conversation.

    `allow_partial=False` (défaut) : ignore un transcript rétro-créé partiel
    (`step_index` initial > 0) — la passerelle donnera le dialogue complet.
    `allow_partial=True` : accepte n'importe quel transcript (repli de dernier
    recours quand la passerelle est indisponible).
    """
    _, antigravity_root, brain_dir, _, _ = get_paths()
    dirs_to_check = [brain_dir / conv_id]
    gemini_parent = antigravity_root.parent
    for sibling in ("antigravity-ide", "antigravity", "antigravity-backup"):
        alt = gemini_parent / sibling / "brain" / conv_id
        if alt not in dirs_to_check:
            dirs_to_check.append(alt)

    for b_dir in dirs_to_check:
        if not b_dir.is_dir():
            continue
        for name in ("transcript.jsonl", "transcript_full.jsonl"):
            cand = b_dir / ".system_generated" / "logs" / name
            if cand.is_file() and (allow_partial or _transcript_is_complete(cand)):
                return cand
    return None


def _find_overview_file(conv_id: str) -> Path | None:
    """Localise `.system_generated/logs/overview.txt` — un EXTRAIT partiel du
    transcript (mêmes lignes JSONL `USER_INPUT`/`PLANNER_RESPONSE`, mais pas
    toutes les étapes). Certaines sessions historiques n'ont que ce fichier.
    À n'utiliser qu'en repli, après le transcript complet et la passerelle.
    """
    _, antigravity_root, brain_dir, _, _ = get_paths()
    gemini_parent = antigravity_root.parent
    dirs = [brain_dir / conv_id]
    for sibling in ("antigravity-ide", "antigravity", "antigravity-backup"):
        alt = gemini_parent / sibling / "brain" / conv_id
        if alt not in dirs:
            dirs.append(alt)
    for b_dir in dirs:
        ov = b_dir / ".system_generated" / "logs" / "overview.txt"
        if ov.is_file():
            return ov
    return None


def _bridge_app_data_dir(conv_id: str) -> str:
    """`app_data_dir` à passer au language_server pour cette conversation :
    `antigravity-ide` si ses données vivent côté IDE, sinon `antigravity`."""
    try:
        return "antigravity-ide" if _detect_origin(conv_id) == "ide" else "antigravity"
    except Exception:
        return "antigravity"


def _has_legacy_pb(conv_id: str) -> bool:
    """Vrai s'il existe un fichier `conversations/<cid>.pb` — condition
    nécessaire pour que la passerelle `language_server` ait quelque chose à
    convertir. Évite de lancer PowerShell pour des `conv_id` sans `.pb`.
    """
    _, antigravity_root, _, _, _ = get_paths()
    gemini_parent = antigravity_root.parent
    for sub in ("antigravity", "antigravity-ide", "antigravity-backup"):
        if (gemini_parent / sub / "conversations" / f"{conv_id}.pb").is_file():
            return True
    return False


def _load_bridge_messages(conv_id: str) -> list[dict]:
    """Dialogue via la passerelle `language_server` (conversations `.pb`
    legacy opaques), `[]` si le serveur Antigravity n'est pas joignable ou
    si la conversation n'a pas de fichier `.pb`."""
    if not _has_legacy_pb(conv_id):
        return []
    try:
        from antigravity_ls_bridge import load_bridge_messages

        return load_bridge_messages(conv_id, _bridge_app_data_dir(conv_id))
    except Exception as exc:
        logger.debug("_load_bridge_messages(%s) : %s", conv_id, exc)
        return []


# Cache mémoire pour chargement instantané des messages déjà consultés
_CHAT_CACHE: dict[str, tuple[float, list[dict]]] = {}

# Cache : conv_id -> a un vrai dialogue (bool). Invalidé par mtime du transcript.
_DIALOGUE_CACHE: dict[str, tuple[float, bool]] = {}


def conversation_has_dialogue(conv_id: str) -> bool:
    """Vrai si la session contient au moins un échange utilisateur/modèle.

    Test rapide : on scanne le transcript à la recherche d'une ligne
    `USER_INPUT` ou `PLANNER_RESPONSE`, sans tout parser. Les sous-tâches
    techniques (exécution d'outils, sous-agents) n'en ont pas.
    """
    transcript = _find_transcript_file(conv_id)
    if not transcript or not transcript.is_file():
        # Repli : conversation IDE stockée en SQLite (pas de dossier brain/).
        db = _find_ide_sqlite_db(conv_id)
        if db is not None:
            try:
                from antigravity_ide_sqlite import ide_sqlite_has_dialogue

                return ide_sqlite_has_dialogue(db)
            except Exception as exc:
                logger.debug("conversation_has_dialogue(%s) SQLite : %s", conv_id, exc)
        # Repli : extrait overview.txt (au moins un échange visible).
        overview = _find_overview_file(conv_id)
        if overview is not None:
            cached = _DIALOGUE_CACHE.get(conv_id)
            try:
                mtime = overview.stat().st_mtime
            except OSError:
                mtime = 0.0
            if cached and cached[0] == mtime:
                return cached[1]
            hd = False
            try:
                with overview.open(encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if '"USER_INPUT"' in line or '"PLANNER_RESPONSE"' in line:
                            hd = True
                            break
            except OSError:
                pass
            _DIALOGUE_CACHE[conv_id] = (mtime, hd)
            if hd:
                return True
        # Repli : passerelle language_server (conversations .pb legacy).
        # Seulement s'il existe un .pb — sinon inutile de solliciter le serveur.
        if _has_legacy_pb(conv_id):
            cached = _DIALOGUE_CACHE.get(conv_id)
            if cached is not None and cached[0] == 0.0:
                return cached[1]
            hd = bool(_load_bridge_messages(conv_id))
            _DIALOGUE_CACHE[conv_id] = (0.0, hd)
            return hd
        return False
    try:
        mtime = transcript.stat().st_mtime
    except OSError:
        mtime = 0.0
    cached = _DIALOGUE_CACHE.get(conv_id)
    if cached and cached[0] == mtime:
        return cached[1]

    has_dialogue = False
    try:
        with transcript.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"USER_INPUT"' in line or '"PLANNER_RESPONSE"' in line:
                    has_dialogue = True
                    break
    except OSError as exc:
        logger.debug("conversation_has_dialogue(%s) : %s", conv_id, exc)

    _DIALOGUE_CACHE[conv_id] = (mtime, has_dialogue)
    return has_dialogue


def _first_line_of_artifact(brain_path: Path) -> str:
    """1re ligne utile de task.md puis walkthrough.md (titre Markdown nettoyé)."""
    for fname in ("task.md", "walkthrough.md", "implementation_plan.md"):
        f = brain_path / fname
        if not f.is_file():
            continue
        try:
            for raw in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                s = raw.strip().lstrip("#").strip()
                if s:
                    return s[:80]
        except OSError:
            continue
    return ""


def derive_conv_label(conv_id: str, title: str = "") -> str:
    """Libellé d'affichage d'une conversation.

    - titre officiel s'il existe ;
    - sinon `<id8> — <1re ligne d'un artéfact>` si un artéfact est présent ;
    - sinon `<id8>` seul.
    """
    if title:
        return title
    short = conv_id[:12]
    brain_p = _find_brain_path(conv_id)
    if brain_p and brain_p.is_dir():
        line = _first_line_of_artifact(brain_p)
        if line:
            return f"{short} — {line}"
    return short


# -----------------------------------------------------------------
# Chargement des messages d'une conversation pour le Chat Viewer
# -----------------------------------------------------------------
def load_chat_messages(conv_id: str) -> list[dict]:
    """Extrait tous les messages du chat ordonnés pour l'affichage (avec cache haute performance)."""
    transcript = _find_transcript_file(conv_id)

    if transcript and transcript.is_file():
        try:
            mtime = transcript.stat().st_mtime
            if conv_id in _CHAT_CACHE and _CHAT_CACHE[conv_id][0] == mtime:
                return _CHAT_CACHE[conv_id][1]
        except Exception:
            pass

    messages = []

    if transcript and transcript.is_file():
        try:
            with transcript.open(encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    # Pré-filtrage ultra-rapide avant json.loads
                    if '"USER_INPUT"' not in line and '"PLANNER_RESPONSE"' not in line:
                        continue

                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue

                    stype = obj.get("type")
                    source = obj.get("source")
                    content = obj.get("content", "")
                    ts = obj.get("created_at", "")
                    time_display = ""
                    epoch = 0.0
                    if ts:
                        try:
                            pdt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            time_display = pdt.strftime("%d/%m %H:%M")
                            epoch = pdt.timestamp()
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
                                "epoch": epoch,
                            })

                    # Réponse visible du modèle
                    elif stype == "PLANNER_RESPONSE" and source == "MODEL":
                        text = content.strip()
                        if text:
                            messages.append({
                                "role": "model",
                                "text": text,
                                "timestamp": time_display,
                                "epoch": epoch,
                            })

            try:
                _CHAT_CACHE[conv_id] = (transcript.stat().st_mtime, messages)
            except Exception as exc:
                logger.debug("Cache non mis à jour pour %s : %s", conv_id, exc)

        except Exception as exc:
            logger.warning("Lecture du transcript %s échouée : %s", transcript, exc)

    # Repli SQLite : conversation IDE légère sans dossier brain/ ni transcript.
    if not messages and not (transcript and transcript.is_file()):
        db = _find_ide_sqlite_db(conv_id)
        if db is not None:
            try:
                from antigravity_ide_sqlite import load_ide_sqlite_conversation

                data = load_ide_sqlite_conversation(db)
                for m in data.get("messages", []):
                    messages.append(
                        {
                            "role": m["role"],
                            "text": m["text"],
                            "timestamp": m.get("timestamp", ""),
                            "epoch": m.get("epoch", 0.0),
                        }
                    )
                if messages:
                    try:
                        _CHAT_CACHE[conv_id] = (db.stat().st_mtime, messages)
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("Lecture SQLite %s échouée : %s", db, exc)

    # Repli passerelle : conversation legacy .pb opaque (ni transcript, ni
    # SQLite). On interroge le language_server d'Antigravity s'il tourne.
    if not messages and not (transcript and transcript.is_file()):
        bridge_msgs = _load_bridge_messages(conv_id)
        for m in bridge_msgs:
            messages.append(
                {
                    "role": m["role"],
                    "text": m["text"],
                    "timestamp": m.get("timestamp", ""),
                    "epoch": 0.0,
                    "partial_source": "bridge",
                }
            )
        # dialogue reconstruit : pas de mise en cache disque (le .pb n'a pas
        # de mtime pertinent ici et le serveur peut renvoyer mieux plus tard).

    # Repli transcript PARTIEL : Antigravity a rouvert la conversation et créé
    # un transcript ne couvrant que les étapes récentes. Mieux que rien si la
    # passerelle est indisponible.
    if not messages:
        partial = _find_transcript_file(conv_id, allow_partial=True)
        if partial is not None:
            try:
                with partial.open(encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if '"USER_INPUT"' not in line and '"PLANNER_RESPONSE"' not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        stype = obj.get("type")
                        source = obj.get("source")
                        content = obj.get("content", "")
                        ts = obj.get("created_at", "")
                        time_display = ""
                        epoch = 0.0
                        if ts:
                            try:
                                pdt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                time_display = pdt.strftime("%d/%m %H:%M")
                                epoch = pdt.timestamp()
                            except Exception:
                                time_display = ts[:16]
                        if stype == "USER_INPUT" and source == "USER_EXPLICIT":
                            raw = content.strip()
                            m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.DOTALL)
                            text = m.group(1).strip() if m else raw
                            text = re.sub(r"<[^>]+>", "", text).strip()
                            if text and not text.startswith("The following is a summary"):
                                messages.append({
                                    "role": "user", "text": text,
                                    "timestamp": time_display, "epoch": epoch,
                                    "partial_source": "transcript_partial",
                                })
                        elif stype == "PLANNER_RESPONSE" and source == "MODEL":
                            text = content.strip()
                            if text:
                                messages.append({
                                    "role": "model", "text": text,
                                    "timestamp": time_display, "epoch": epoch,
                                    "partial_source": "transcript_partial",
                                })
            except Exception as exc:
                logger.debug("Lecture transcript partiel %s échouée : %s", partial, exc)

    # Repli overview.txt : EXTRAIT partiel du transcript (sessions historiques
    # sans transcript complet ni serveur Antigravity disponible).
    if not messages:
        overview = _find_overview_file(conv_id)
        if overview is not None:
            try:
                with overview.open(encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if '"USER_INPUT"' not in line and '"PLANNER_RESPONSE"' not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        stype = obj.get("type")
                        source = obj.get("source")
                        content = obj.get("content", "")
                        ts = obj.get("created_at", "")
                        time_display = ""
                        epoch = 0.0
                        if ts:
                            try:
                                pdt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                time_display = pdt.strftime("%d/%m %H:%M")
                                epoch = pdt.timestamp()
                            except Exception:
                                time_display = ts[:16]
                        if stype == "USER_INPUT" and source == "USER_EXPLICIT":
                            raw = content.strip()
                            m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.DOTALL)
                            text = m.group(1).strip() if m else raw
                            text = re.sub(r"<[^>]+>", "", text).strip()
                            if text and not text.startswith("The following is a summary"):
                                messages.append({
                                    "role": "user", "text": text,
                                    "timestamp": time_display, "epoch": epoch,
                                    "partial_source": "overview",
                                })
                        elif stype == "PLANNER_RESPONSE" and source == "MODEL":
                            text = content.strip()
                            if text:
                                messages.append({
                                    "role": "model", "text": text,
                                    "timestamp": time_display, "epoch": epoch,
                                    "partial_source": "overview",
                                })
            except Exception as exc:
                logger.debug("Lecture overview.txt %s échouée : %s", overview, exc)

    # Si aucun message de log mais des artéfacts sont présents sur disque
    if not messages:
        brain_path = _find_brain_path(conv_id)
        if brain_path and brain_path.is_dir():
            for doc_name, label in [
                ("walkthrough.md", "📝 Walkthrough & Synthèse"),
                ("implementation_plan.md", "📋 Plan d'implémentation"),
                ("task.md", "📌 Tâche"),
            ]:
                doc_file = brain_path / doc_name
                if doc_file.is_file():
                    try:
                        doc_content = doc_file.read_text(encoding="utf-8", errors="ignore").strip()
                        if doc_content:
                            display_doc = doc_content[:4000] + ("\n\n[...suite tronquée...]" if len(doc_content) > 4000 else "")
                            messages.append({
                                "role": "model",
                                "text": f"### {label} (extrait de session)\n\n{display_doc}",
                                "timestamp": "",
                            })
                            break
                    except Exception:
                        pass

            if not messages:
                # Vérifier présence d'images générées dans le brain
                try:
                    images = [f.name for f in brain_path.iterdir() if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg")]
                    if images:
                        img_list = "\n".join([f"- 🖼️ `{img}`" for img in images[:10]])
                        messages.append({
                            "role": "model",
                            "text": f"### 🎨 Médias générés dans cette tâche\n\nCette session a produit les artéfacts visuels suivants :\n\n{img_list}",
                            "timestamp": "",
                        })
                except Exception:
                    pass

            if not messages:
                transcript = _find_transcript_file(conv_id)
                if transcript and transcript.is_file():
                    actions = []
                    try:
                        with transcript.open(encoding="utf-8", errors="ignore") as fh:
                            for line in fh:
                                for m_act in re.finditer(r'"(?:toolAction|toolSummary)"\s*:\s*"([^"\\]+)"', line):
                                    act_text = m_act.group(1).strip()
                                    if act_text and act_text not in actions:
                                        actions.append(act_text)
                                    if len(actions) >= 12:
                                        break
                                if len(actions) >= 12:
                                    break
                        if actions:
                            action_list = "\n".join([f"- ⚙️ {a}" for a in actions])
                            messages.append({
                                "role": "model",
                                "text": f"### 🛠️ Opérations techniques du sous-agent\n\nCette session automatisée a exécuté les opérations suivantes :\n\n{action_list}",
                                "timestamp": "",
                            })
                    except Exception:
                        pass

    return messages


# -----------------------------------------------------------------
# Date & Titre de repli depuis transcript
# -----------------------------------------------------------------
def get_transcript_info(conv_id: str):
    """Retourne (fallback_title, last_datetime)."""
    transcript = _find_transcript_file(conv_id)
    if not transcript or not transcript.is_file():
        # Repli SQLite : session IDE légère sans dossier brain/.
        db = _find_ide_sqlite_db(conv_id)
        if db is not None:
            try:
                from antigravity_ide_sqlite import load_ide_sqlite_conversation

                data = load_ide_sqlite_conversation(db)
                title = data.get("title") or conv_id[:12]
                return title, data.get("last_dt")
            except Exception as exc:
                logger.debug("get_transcript_info(%s) SQLite : %s", conv_id, exc)

        brain_path = _find_brain_path(conv_id)
        last_dt = None
        if brain_path and brain_path.is_dir():
            try:
                mtime = brain_path.stat().st_mtime
                last_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
            except Exception:
                pass

        # Repli overview.txt : titre + date depuis l'extrait JSONL.
        overview = _find_overview_file(conv_id)
        if overview is not None:
            try:
                ov_title, ov_last = "", None
                with overview.open(encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except Exception:
                            continue
                        ts = obj.get("created_at")
                        if ts:
                            ov_last = ts
                        if not ov_title and obj.get("type") == "USER_INPUT" \
                                and obj.get("source") == "USER_EXPLICIT":
                            raw = obj.get("content", "").strip()
                            m = re.search(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", raw, re.DOTALL)
                            txt = m.group(1).strip() if m else raw
                            txt = re.sub(r"<[^>]+>", "", txt).strip()
                            if txt and not txt.startswith("The following is a summary"):
                                ov_title = txt.splitlines()[0].strip()[:80]
                if ov_title:
                    dt = None
                    if ov_last:
                        try:
                            dt = datetime.fromisoformat(ov_last.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    return ov_title, dt or last_dt
            except Exception as exc:
                logger.debug("get_transcript_info(%s) overview : %s", conv_id, exc)

        # Repli passerelle : titre depuis le language_server (date indisponible
        # dans ce rendu -> on garde le mtime du brain/). Seulement si un .pb existe.
        if _has_legacy_pb(conv_id):
            try:
                from antigravity_ls_bridge import bridge_first_user_title

                bt = bridge_first_user_title(conv_id, _bridge_app_data_dir(conv_id))
                if bt:
                    return bt, last_dt
            except Exception as exc:
                logger.debug("get_transcript_info(%s) bridge : %s", conv_id, exc)

        return conv_id[:12], last_dt

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
        "origin",
    )

    #: origine -> libellé de badge affiché dans l'arbre
    _ORIGIN_LABELS = {"ide": "IDE", "app": "App", "ide+app": "IDE+App"}

    def __init__(
        self,
        conv_id: str,
        title: str,
        project: str,
        workspace: str,
        last_activity: datetime | None,
        origin: str = "",
    ):
        self.conv_id = conv_id
        self.title = title
        self.project = project
        self.workspace = workspace
        self.last_activity = last_activity
        self.rel_time = relative_time(last_activity)
        #: "ide" (Antigravity IDE), "app" (application Antigravity),
        #: "ide+app" (présente dans les deux) ou "" (indéterminé)
        self.origin = origin

    @property
    def origin_label(self) -> str:
        """Libellé court pour le badge d'origine, "" si indéterminé."""
        return self._ORIGIN_LABELS.get(self.origin, "")


def _extract_workspace_from_transcript(conv_id: str) -> str:
    """Extrait le chemin du workspace depuis le journal de session transcript si absent du proto."""
    transcript = _find_transcript_file(conv_id)
    if not transcript or not transcript.is_file():
        # Repli SQLite : workspace stocké dans la base IDE.
        db = _find_ide_sqlite_db(conv_id)
        if db is not None:
            try:
                from antigravity_ide_sqlite import extract_workspace

                return extract_workspace(db)
            except Exception as exc:
                logger.debug("_extract_workspace_from_transcript(%s) SQLite : %s", conv_id, exc)
        return ""
    try:
        with transcript.open(encoding="utf-8", errors="ignore") as fh:
            for raw_line in fh:
                # Dé-échapper les sauts de ligne de chaînes JSON pour éviter les captures corrompues
                line = raw_line.replace("\\r", " ").replace("\\n", " ")

                # 1. Active Document (ignorer les fichiers internes .gemini/brain/Temp)
                m = re.search(r"Active Document:\s*([a-zA-Z]:\\[^\s\(\)\"\'<>]+)", line)
                if m:
                    doc_path = Path(m.group(1).strip())
                    parts_lower = [p.lower() for p in doc_path.parts]
                    if not any(k in parts_lower for k in (".gemini", "antigravity", "antigravity-ide", "temp", "tmp")):
                        if len(doc_path.parts) >= 3:
                            return str(doc_path.parent)

                # 2. [URI] -> [CorpusName]
                m2 = re.search(r"\[URI\]\s*->\s*\[CorpusName\]:\s*([^\s\"\'<>]+)", line)
                if m2:
                    val = _clean_path_string(m2.group(1)).rstrip("`'\",.:; ")
                    if val and not any(k in val.lower() for k in (".gemini", "temp", "tmp")):
                        return val

                # 3. SearchPath ou Cwd dans les tool_calls
                m_sp = re.search(r'"(?:SearchPath|Cwd)"\s*:\s*"([a-zA-Z]:(?:\\\\|/)[^"\\r\\n]+)"', line)
                if m_sp:
                    val = _clean_path_string(m_sp.group(1).replace("\\\\", "\\")).rstrip("`'\",.:; ")
                    if val and not any(k in val.lower() for k in (".gemini", "temp", "tmp")):
                        return val

                # 4. file:///
                if "file:///" in line:
                    m3 = re.search(r"file:///([a-zA-Z]:/[^\s\>\)\"]+)", line)
                    if m3:
                        val = _clean_path_string(m3.group(0)).rstrip("`'\",.:; ")
                        if val and not any(k in val.lower() for k in (".gemini", "temp", "tmp")):
                            return val
    except Exception as exc:
        logger.debug("Extraction workspace échouée pour %s : %s", conv_id, exc)
    return ""


# -----------------------------------------------------------------
# Construction de la carte des projets & conversations
# -----------------------------------------------------------------
def build_project_map():
    """Retourne (project_convs, all_sorted).
    project_convs: {nom_projet: [ConversationInfo, ...]}
    all_sorted: [ConversationInfo, ...] triées par date décroissante
    """
    projects_root, antigravity_root, brain_dir, conversations_dir, _ = get_paths()
    proto_meta = _extract_proto_metadata()

    # Lister les projets reconnus (projets officiels Antigravity ou dossiers avec marqueurs Antigravity)
    projects = set()
    cfg_projects_dir = antigravity_root.parent / "config" / "projects"
    if cfg_projects_dir.is_dir():
        for f in cfg_projects_dir.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                n = d.get("name", "").strip()
                if n and n.lower() != "outside of project":
                    projects.add(n)
            except Exception:
                pass

    if projects_root.is_dir():
        for p in projects_root.iterdir():
            if p.is_dir():
                # Un dossier sur disque est retenu s'il contient des marqueurs spécifiques Antigravity
                if (
                    (p / ".agent").is_dir()
                    or (p / ".gemini").is_dir()
                    or (p / ".antigravityrules").is_file()
                    or (p / "agy.json").is_file()
                ):
                    projects.add(p.name)

    # Récupérer toutes les conversations réelles (dans le dossier configuré et les dossiers frères)
    actual_convs = set()
    gemini_parent = antigravity_root.parent
    for sub in ("antigravity-ide", "antigravity", "antigravity-backup"):
        b_candidate = gemini_parent / sub / "brain"
        if b_candidate.is_dir():
            for d in b_candidate.iterdir():
                if d.is_dir() and len(d.name) == 36:
                    actual_convs.add(d.name)
        c_candidate = gemini_parent / sub / "conversations"
        if c_candidate.is_dir():
            for f in c_candidate.iterdir():
                if f.suffix == ".db" and len(f.stem) == 36:
                    actual_convs.add(f.stem)

    project_convs = {p: [] for p in sorted(projects, key=str.lower)}
    all_convs = []

    for cid in actual_convs:
        meta = proto_meta.get(cid, {})
        title = meta.get("title", "").strip()
        workspace = meta.get("workspace", "").strip()

        if not workspace:
            workspace = _extract_workspace_from_transcript(cid)

        fallback_title, last_dt = get_transcript_info(cid)
        if not title:
            title = fallback_title

        # Filtrage : ignorer les stubs de sous-agents orphelins sans logs ni artéfacts
        if not title or title == cid[:12]:
            brain_p = _find_brain_path(cid)
            if brain_p and not (brain_p / ".system_generated" / "logs").is_dir() and not (brain_p / "task.md").is_file() and not (brain_p / "walkthrough.md").is_file():
                continue

        # Vérifier override echange_IA.md si présent
        brain_p = _find_brain_path(cid)
        override_proj = None
        if brain_p:
            echange = brain_p / "echange_IA.md"
            if echange.is_file():
                try:
                    for line in echange.read_text(encoding="utf-8").splitlines():
                        if line.lower().startswith("project:"):
                            override_proj = line.split(":", 1)[1].strip()
                            break
                except Exception:
                    pass

        proj = override_proj if override_proj else workspace_to_project(workspace)

        info = ConversationInfo(cid, title, proj, workspace, last_dt, _detect_origin(cid))
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


def delete_conversation(conv_id: str) -> tuple[bool, str]:
    """Supprime définitivement une conversation unique (brain + sqlite db) sur tous les dossiers .gemini."""
    _, antigravity_root, _, _, _ = get_paths()
    errors = []
    gemini_parent = antigravity_root.parent

    for sub in ("antigravity-ide", "antigravity", "antigravity-backup"):
        b_dir = gemini_parent / sub / "brain" / conv_id
        if b_dir.is_dir():
            try:
                shutil.rmtree(b_dir)
            except Exception as e:
                errors.append(f"Brain {sub}: {e}")

        c_dir = gemini_parent / sub / "conversations"
        if c_dir.is_dir():
            for ext in ("", "-wal", "-shm"):
                f = c_dir / f"{conv_id}.db{ext}"
                if f.is_file():
                    try:
                        f.unlink()
                    except Exception as e:
                        errors.append(f"DB {sub}{ext}: {e}")

    # Suppression dans conversation_summaries.db (index Desktop et IDE)
    for db_path in _find_all_summaries_db():
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?", (conv_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            errors.append(f"Summaries DB {db_path.name}: {e}")

    # Invalider le cache mémoire
    if conv_id in _CHAT_CACHE:
        del _CHAT_CACHE[conv_id]

    if errors:
        return False, "\n".join(errors)
    return True, "Conversation supprimée avec succès."


def _find_all_summaries_db() -> list[Path]:
    """Localise tous les fichiers conversation_summaries.db existants dans .gemini/."""
    _, antigravity_root, _, _, _ = get_paths()
    dbs = []
    direct = antigravity_root / "conversation_summaries.db"
    if direct.is_file():
        dbs.append(direct)
    gemini_parent = antigravity_root.parent
    for sub in ("antigravity", "antigravity-ide", "antigravity-backup"):
        cand = gemini_parent / sub / "conversation_summaries.db"
        if cand.is_file() and cand not in dbs:
            dbs.append(cand)
    return dbs


def _resolve_target_project_id_and_uris(
    target_project_name: str, target_project_dir: Path
) -> tuple[str, str, bytes, bytes, str]:
    """Résout le project_id existant pour le projet cible, l'URI canonique encodée (%3A),
    l'URI standard et le json de l'URI.
    Si aucun project_id n'existe pour ce projet, un nouvel UUID est généré.
    Retourne:
      (project_id, canonical_uri, uri_standard_bytes, uri_encoded_bytes, workspace_uris_json)
    """
    found_pid = None
    found_uri = None
    target_clean = target_project_name.lower().strip("/\\")

    # 0. Chercher prioritairement dans les fichiers officiels config/projects/*.json
    _, antigravity_root, _, _, _ = get_paths()
    cfg_projects = antigravity_root.parent / "config" / "projects"
    if cfg_projects.is_dir():
        for pjson in cfg_projects.glob("*.json"):
            try:
                pdata = json.loads(pjson.read_text(encoding="utf-8"))
                p_name = pdata.get("name", "").strip().lower()
                p_id = pdata.get("id", "")
                if p_name == target_clean or (p_id and target_clean == p_id.lower()):
                    found_pid = p_id
                    res_list = pdata.get("projectResources", {}).get("resources", [])
                    if res_list and isinstance(res_list, list):
                        gf = res_list[0].get("gitFolder", {})
                        f_uri = gf.get("folderUri")
                        if f_uri:
                            found_uri = f_uri
                    break
            except Exception:
                pass

    # 1. Chercher dans les conversation_summaries.db existants si pas encore trouvé
    if not found_pid:
        for db_path in _find_all_summaries_db():
            try:
                conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                rows = conn.execute(
                    "SELECT project_id, workspace_uris FROM conversation_summaries "
                    "WHERE project_id != '' AND project_id != 'outside-of-project'"
                ).fetchall()
                conn.close()
                for pid, uris_str in rows:
                    if not pid or not uris_str:
                        continue
                    uris_lower = uris_str.lower().replace("\\", "/").replace("%3a", ":")
                    if f"/{target_clean}" in uris_lower or target_clean == uris_lower.rstrip("/").split("/")[-1]:
                        found_pid = pid
                        try:
                            parsed_list = json.loads(uris_str)
                            if parsed_list and isinstance(parsed_list, list):
                                found_uri = parsed_list[0]
                        except Exception:
                            pass
                        break
                if found_pid:
                    break
            except Exception as exc:
                logger.debug("Erreur lecture %s pour resolve PID : %s", db_path, exc)

    # 2. Chercher dans agyhub_summaries_proto.pb par scan binaire si pas encore trouvé
    if not found_pid:
        summaries_pb = _find_summaries_pb()
        if summaries_pb and summaries_pb.is_file():
            try:
                raw_bytes = summaries_pb.read_bytes()
                for m in re.finditer(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", raw_bytes):
                    start = max(0, m.start() - 200)
                    end = min(len(raw_bytes), m.end() + 200)
                    chunk = raw_bytes[start:end].lower()
                    if target_clean.encode() in chunk:
                        found_pid = m.group(0).decode("ascii")
                        break
            except Exception as exc:
                logger.debug("Erreur scan pb pour resolve PID : %s", exc)

    project_id = found_pid if found_pid else str(uuid.uuid4())

    dir_str = str(target_project_dir).replace("\\", "/")
    uri_standard = f"file:///{dir_str.lstrip('/')}"
    if len(dir_str) >= 2 and dir_str[1] == ":":
        drive = dir_str[0].lower()
        rest = dir_str[2:].lstrip("/")
        canonical_uri = f"file:///{drive}%3A/{rest}"
    else:
        canonical_uri = uri_standard

    if found_uri:
        canonical_uri = found_uri
        uri_standard = re.sub(r"%3a", ":", found_uri, flags=re.IGNORECASE)

    uri_standard_bytes = uri_standard.encode("utf-8")
    uri_encoded_bytes = canonical_uri.encode("utf-8")
    workspace_uris_json = json.dumps([canonical_uri])

    return project_id, canonical_uri, uri_standard_bytes, uri_encoded_bytes, workspace_uris_json


def _update_proto_submessage(
    raw_sub: bytes,
    new_project_id: str,
    uri_standard_bytes: bytes,
    uri_encoded_bytes: bytes,
    title: str = "",
) -> bytes:
    """Met à jour les métadonnées de summary pour Antigravity Desktop (titre, workspace, project_id).
    - sub_f[1] : Titre officiel
    - sub_f[4] : ID de session (conservé si présent)
    - sub_f[9] : Sous-message workspace (champs 1 et 2 avec uri_standard_bytes)
    - sub_f[17] : Sous-message projet & workspace :
        * champ 1 : sous-message workspace (champs 1 et 2 avec uri_standard_bytes)
        * champ 3 : uuid du workspace
        * champ 7 : uri_encoded_bytes (avec %3A)
        * champ 18 : new_project_id (project_id reconnu par Antigravity Desktop)
    """
    sub_f = _parse_proto_fields(raw_sub) if raw_sub else {}

    # Titre
    if title and (1 not in sub_f or not sub_f[1]):
        sub_f[1] = [(2, title.encode("utf-8"))]

    # project_id dans champ 4 (rétrocompatibilité) ET dans sous-message 17 champ 18 (Desktop)
    sub_f[4] = [(2, new_project_id.encode("utf-8"))]

    # Workspace dans champ 9
    ws_sub = {
        1: [(2, uri_standard_bytes)],
        2: [(2, uri_standard_bytes)],
    }
    if 9 in sub_f and sub_f[9] and isinstance(sub_f[9][0][1], bytes):
        old_ws = _parse_proto_fields(sub_f[9][0][1])
        if 3 in old_ws:
            ws_sub[3] = old_ws[3]
    rb_ws = bytearray()
    for wf, witems in ws_sub.items():
        for ww, wv in witems:
            rb_ws.extend(_encode_proto_field(wf, ww, wv))
    sub_f[9] = [(2, bytes(rb_ws))]

    # Association projet dans champ 17
    f17 = {}
    if 17 in sub_f and sub_f[17] and isinstance(sub_f[17][0][1], bytes):
        f17 = _parse_proto_fields(sub_f[17][0][1])

    f17[1] = [(2, bytes(rb_ws))]
    if 2 not in f17:
        f17[2] = [(2, b"\x08\x80\x01\x10\x80\x01")]
    if 3 not in f17:
        f17[3] = [(2, str(uuid.uuid4()).encode("utf-8"))]
    f17[7] = [(2, uri_encoded_bytes)]
    f17[18] = [(2, new_project_id.encode("utf-8"))]

    rb17 = bytearray()
    for sf, sitems in f17.items():
        for sw, sv in sitems:
            rb17.extend(_encode_proto_field(sf, sw, sv))
    sub_f[17] = [(2, bytes(rb17))]

    rb_top = bytearray()
    for sf, sitems in sub_f.items():
        for sw, sv in sitems:
            rb_top.extend(_encode_proto_field(sf, sw, sv))
    return bytes(rb_top)


def _update_conversation_summaries_db(
    conv_id: str,
    project_id: str,
    workspace_uris_json: str,
    uri_standard_bytes: bytes,
    uri_encoded_bytes: bytes,
    sub_raw_bytes: bytes | None = None,
    title: str = "",
) -> bool:
    """Met à jour ou insère la conversation dans conversation_summaries.db."""
    dbs = _find_all_summaries_db()
    updated_any = False
    for db_path in dbs:
        try:
            _backup_pb_file(db_path)
            conn = sqlite3.connect(db_path, timeout=10.0)
            cur = conn.cursor()
            row = cur.execute(
                "SELECT raw_summary, title FROM conversation_summaries WHERE conversation_id = ?",
                (conv_id,),
            ).fetchone()

            if row is not None:
                raw_db = row[0]
                db_title = row[1] or title
                if raw_db and isinstance(raw_db, (bytes, bytearray)):
                    new_raw = _update_proto_submessage(
                        bytes(raw_db), project_id, uri_standard_bytes, uri_encoded_bytes, db_title
                    )
                elif sub_raw_bytes:
                    new_raw = _update_proto_submessage(
                        sub_raw_bytes, project_id, uri_standard_bytes, uri_encoded_bytes, db_title
                    )
                else:
                    new_raw = _update_proto_submessage(
                        b"", project_id, uri_standard_bytes, uri_encoded_bytes, db_title
                    )

                cur.execute(
                    "UPDATE conversation_summaries SET project_id = ?, workspace_uris = ?, raw_summary = ? "
                    "WHERE conversation_id = ?",
                    (project_id, workspace_uris_json, new_raw, conv_id),
                )
            else:
                eff_title = title or conv_id[:12]
                new_raw = sub_raw_bytes if sub_raw_bytes else _update_proto_submessage(
                    b"", project_id, uri_standard_bytes, uri_encoded_bytes, eff_title
                )
                cur.execute(
                    """INSERT INTO conversation_summaries (
                        conversation_id, title, preview, step_count, last_modified_time,
                        workspace_uris, status, source, project_id, agent_name,
                        parent_conversation_id, nesting_depth, battle_id, winning_conversation_id,
                        not_fully_idle, killed, last_user_input_time, last_user_input_step_index,
                        app_data_dir, raw_summary, group_id
                    ) VALUES (?, ?, '', 0, datetime('now'), ?, '', '', ?, '', '', 0, '', '', 0, 0, datetime('now'), 0, 'antigravity', ?, '')""",
                    (conv_id, eff_title, workspace_uris_json, project_id, new_raw),
                )
            conn.commit()
            conn.close()
            updated_any = True
            logger.debug(
                "conversation_summaries.db (%s) synchronisé pour conv %s -> project_id %s",
                db_path,
                conv_id,
                project_id,
            )
        except Exception as exc:
            logger.warning("Échec mise à jour %s pour %s : %s", db_path, conv_id, exc)
    return updated_any


def _update_ide_sqlite_db_workspace(
    conv_id: str,
    uri_standard_bytes: bytes,
    uri_encoded_bytes: bytes,
    project_id: str = "",
) -> bool:
    """Met à jour trajectory_metadata_blob dans conversations/<conv_id>.db si présent."""
    _, antigravity_root, _, _, _ = get_paths()
    gemini_parent = antigravity_root.parent
    updated = False
    candidates = [antigravity_root / "conversations" / f"{conv_id}.db"]
    for sub in ("antigravity-ide", "antigravity", "antigravity-backup"):
        p = gemini_parent / sub / "conversations" / f"{conv_id}.db"
        if p not in candidates:
            candidates.append(p)

    for db_path in candidates:
        if not db_path.is_file():
            continue
        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            row = conn.execute("SELECT data FROM trajectory_metadata_blob WHERE id='main'").fetchone()
            if row and row[0]:
                top = _parse_proto_fields(row[0])
                sub1 = {}
                if 1 in top and top[1] and isinstance(top[1][0][1], bytes):
                    sub1 = _parse_proto_fields(top[1][0][1])
                sub1[1] = [(2, uri_standard_bytes)]
                sub1[2] = [(2, uri_standard_bytes)]
                if 3 not in sub1:
                    sub1[3] = [(2, b"")]
                rb_sub1 = bytearray()
                for sf, sitems in sub1.items():
                    for sw, sv in sitems:
                        rb_sub1.extend(_encode_proto_field(sf, sw, sv))
                top[1] = [(2, bytes(rb_sub1))]

                top[7] = [(2, uri_encoded_bytes)]
                if project_id:
                    top[18] = [(2, project_id.encode("utf-8"))]

                rb_top = bytearray()
                for tf, titems in top.items():
                    for tw, tv in titems:
                        rb_top.extend(_encode_proto_field(tf, tw, tv))
                conn.execute("UPDATE trajectory_metadata_blob SET data = ? WHERE id='main'", (bytes(rb_top),))
                conn.commit()
                updated = True
                logger.debug("trajectory_metadata_blob mis à jour pour %s dans %s", conv_id, db_path)
            conn.close()
        except Exception as exc:
            logger.warning("Échec mise à jour trajectory_metadata_blob %s : %s", db_path, exc)
    return updated


def _notify_language_server_refresh(conv_id: str = "") -> bool:
    """Tente de notifier les language_servers locaux pour synchroniser leur état."""
    try:
        from antigravity_ls_bridge import _discover, _discovery_cache
        _discovery_cache.clear()
        import ssl
        import urllib.request
        notified = False
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        # 1. Pour antigravity-ide : recharger la trajectoire déplacée via LoadTrajectory
        # Ne PAS appeler RefreshContextForIdeAction qui vide le cache mémoire des trajectoires
        if conv_id:
            disc_ide = _discover("antigravity-ide")
            if disc_ide:
                token, ports = disc_ide
                headers = {"Content-Type": "application/json", "x-codeium-csrf-token": token}
                payload = json.dumps({"cascadeId": conv_id}).encode("utf-8")
                for port in ports:
                    url = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/LoadTrajectory"
                    try:
                        req = urllib.request.Request(url, data=payload, headers=headers)
                        with urllib.request.urlopen(req, context=ssl_ctx, timeout=1.5):
                            notified = True
                    except Exception:
                        pass

        # 2. Pour antigravity (Desktop standalone) : recharger la trajectoire déplacée via LoadTrajectory
        disc_desk = _discover("antigravity")
        if disc_desk:
            token, ports = disc_desk
            headers = {"Content-Type": "application/json", "x-codeium-csrf-token": token}
            for port in ports:
                if conv_id:
                    url_load = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/LoadTrajectory"
                    try:
                        req = urllib.request.Request(url_load, data=json.dumps({"cascadeId": conv_id}).encode("utf-8"), headers=headers)
                        with urllib.request.urlopen(req, context=ssl_ctx, timeout=1.5):
                            notified = True
                    except Exception:
                        pass

        return notified
    except Exception as exc:
        logger.debug("_notify_language_server_refresh exception : %s", exc)
        return False


def is_antigravity_desktop_running() -> bool:
    """Vérifie si le processus Antigravity Desktop (Antigravity.exe) est actif."""
    try:
        res = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Antigravity.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "Antigravity.exe" in (res.stdout or "")
    except Exception:
        return False


def restart_antigravity_desktop_if_running() -> bool:
    """Si Antigravity Desktop est lancé, le ferme puis le relance pour recharger les trajectoires."""
    if not is_antigravity_desktop_running():
        return False
    try:
        local_app = os.environ.get("LOCALAPPDATA", "")
        exe_path = Path(local_app) / "Programs" / "Antigravity" / "Antigravity.exe"
        if not exe_path.is_file():
            prog_files = os.environ.get("ProgramFiles", "")
            alt_path = Path(prog_files) / "Antigravity" / "Antigravity.exe"
            if alt_path.is_file():
                exe_path = alt_path
            else:
                logger.warning("Antigravity.exe introuvable pour redémarrage.")
                return False

        subprocess.run(
            ["taskkill", "/F", "/IM", "Antigravity.exe"],
            capture_output=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        subprocess.run(
            ["taskkill", "/F", "/IM", "language_server.exe"],
            capture_output=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        time.sleep(1.0)
        os.startfile(str(exe_path))
        logger.info("Antigravity Desktop redémarré avec succès : %s", exe_path)
        return True
    except Exception as exc:
        logger.warning("Erreur redémarrage Antigravity Desktop : %s", exc)
        return False


def move_conversation(
    conv_id: str, target_project_name: str, restart_desktop: bool = False
) -> tuple[bool, str]:
    """Déplace et réassigne officiellement une conversation vers un projet cible.
    Met à jour echange_IA.md, les transcripts, agyhub_summaries_proto.pb,
    conversation_summaries.db et les bases conversations/<cid>.db pour qu'Antigravity
    Desktop et IDE reconnaissent la conversation sous le nouveau projet.
    """
    projects_root, antigravity_root, _, _, _ = get_paths()
    target_project_dir = projects_root / target_project_name
    (
        project_id,
        canonical_uri,
        uri_standard_bytes,
        uri_encoded_bytes,
        workspace_uris_json,
    ) = _resolve_target_project_id_and_uris(target_project_name, target_project_dir)
    gemini_parent = antigravity_root.parent

    # Récupérer titre existant officiel en priorité
    existing_title = ""
    for sdb in _find_all_summaries_db():
        try:
            conn = sqlite3.connect(sdb, timeout=2.0)
            r = conn.execute(
                "SELECT title FROM conversation_summaries WHERE conversation_id = ?",
                (conv_id,),
            ).fetchone()
            conn.close()
            if r and r[0] and r[0].strip() and r[0].strip() != conv_id[:12]:
                existing_title = r[0].strip()
                break
        except Exception:
            pass

    if not existing_title:
        fallback_title, _ = get_transcript_info(conv_id)
        existing_title = fallback_title or conv_id[:12]

    conv_title = existing_title

    # 1. Mise à jour de brain/conv_id/echange_IA.md
    brain_p = _find_brain_path(conv_id)
    if brain_p and brain_p.is_dir():
        echange = brain_p / "echange_IA.md"
        try:
            lines = []
            if echange.is_file():
                lines = [l for l in echange.read_text(encoding="utf-8").splitlines() if not l.lower().startswith("project:")]
            lines.insert(0, f"project: {target_project_name}")
            echange.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception as exc:
            logger.warning("Échec MAJ echange_IA.md %s : %s", echange, exc)

    # 2. Mise à jour des transcripts
    for sub in ("antigravity-ide", "antigravity", "antigravity-backup"):
        b_dir = gemini_parent / sub / "brain" / conv_id
        for tname in ("transcript.jsonl", "transcript_full.jsonl"):
            t_file = b_dir / ".system_generated" / "logs" / tname
            if t_file.is_file():
                try:
                    content = t_file.read_text(encoding="utf-8", errors="ignore")
                    updated = re.sub(r"(\[URI\]\s*->\s*\[CorpusName\]:\s*\n?\s*)([^\s\n\r]+)", rf"\g<1>{canonical_uri}", content)
                    t_file.write_text(updated, encoding="utf-8")
                except Exception as exc:
                    logger.warning("Échec MAJ transcript %s : %s", t_file, exc)

    # 3. Mise à jour dans agyhub_summaries_proto.pb
    last_sub2_bytes = None
    for sub in ("antigravity-ide", "antigravity", "antigravity-backup"):
        pb_path = gemini_parent / sub / "agyhub_summaries_proto.pb"
        if not pb_path.is_file():
            continue
        try:
            data = pb_path.read_bytes()
            top = _parse_proto_fields(data)
            entries = top.get(1, [])
            new_top = {}
            new_entries = []
            found_in_pb = False

            for wt, raw_entry in entries:
                f = _parse_proto_fields(raw_entry)
                cid = f.get(1, [('', b'')])[0][1].decode('utf-8', errors='ignore').strip()
                if cid == conv_id:
                    found_in_pb = True
                    old_sub2 = f.get(2, [(2, b'')])[0][1]
                    eff_title = conv_title
                    if old_sub2:
                        old_sub_f = _parse_proto_fields(old_sub2)
                        if 1 in old_sub_f and old_sub_f[1]:
                            try:
                                pb_t = old_sub_f[1][0][1].decode('utf-8', errors='ignore').strip()
                                if pb_t and pb_t != conv_id[:12]:
                                    eff_title = pb_t
                            except Exception:
                                pass
                    new_sub2 = _update_proto_submessage(
                        old_sub2, project_id, uri_standard_bytes, uri_encoded_bytes, eff_title
                    )
                    f[2] = [(2, new_sub2)]
                    last_sub2_bytes = new_sub2

                    rb_entry = bytearray()
                    for ef, eitems in f.items():
                        for ew, ev in eitems:
                            rb_entry.extend(_encode_proto_field(ef, ew, ev))
                    new_entries.append((wt, bytes(rb_entry)))
                else:
                    new_entries.append((wt, raw_entry))

            if not found_in_pb:
                # Ajout de l'entrée dans le .pb officiel s'il ne la contenait pas
                new_sub2 = _update_proto_submessage(
                    b"", project_id, uri_standard_bytes, uri_encoded_bytes, conv_title
                )
                last_sub2_bytes = new_sub2
                new_f = {
                    1: [(2, conv_id.encode('utf-8'))],
                    2: [(2, new_sub2)],
                }
                rb_entry = bytearray()
                for ef, eitems in new_f.items():
                    for ew, ev in eitems:
                        rb_entry.extend(_encode_proto_field(ef, ew, ev))
                new_entries.append((2, bytes(rb_entry)))

            new_top[1] = new_entries
            for top_f, top_items in top.items():
                if top_f != 1:
                    new_top[top_f] = top_items

            rebuilt_file = bytes(
                b"".join(
                    _encode_proto_field(tf, tw, tv)
                    for tf, titems in new_top.items()
                    for tw, tv in titems
                )
            )

            check = _parse_proto_fields(rebuilt_file)
            n_before = len(entries)
            n_after = len(check.get(1, []))
            if n_after < n_before:
                logger.error(
                    "Réécriture de %s ANNULÉE : %d entrées -> %d (perte). "
                    "Fichier officiel laissé intact.",
                    pb_path, n_before, n_after,
                )
                continue

            _backup_pb_file(pb_path)
            tmp_path = pb_path.with_name(pb_path.name + ".tmp")
            tmp_path.write_bytes(rebuilt_file)
            os.replace(tmp_path, pb_path)
            logger.debug(
                "agyhub_summaries_proto.pb réécrit (%s) pour move %s -> %s (%d entrées)",
                sub, conv_id, target_project_name, n_after,
            )
        except Exception as exc:
            logger.warning(
                "Échec de la réécriture protobuf %s pour %s : %s", pb_path, conv_id, exc
            )
            try:
                tmp_path = pb_path.with_name(pb_path.name + ".tmp")
                if tmp_path.is_file():
                    tmp_path.unlink()
            except OSError:
                pass

    # 4. Mise à jour dans conversation_summaries.db (avec INSERT si absent)
    _update_conversation_summaries_db(
        conv_id,
        project_id,
        workspace_uris_json,
        uri_standard_bytes,
        uri_encoded_bytes,
        sub_raw_bytes=last_sub2_bytes,
        title=conv_title,
    )

    # 5. Mise à jour dans conversations/<cid>.db (format SQLite IDE et Desktop)
    _update_ide_sqlite_db_workspace(
        conv_id, uri_standard_bytes, uri_encoded_bytes, project_id=project_id
    )

    # 6. Notification language_server en tâche de fond
    _notify_language_server_refresh(conv_id=conv_id)

    # 7. Invalider le cache mémoire
    if conv_id in _CHAT_CACHE:
        del _CHAT_CACHE[conv_id]

    # 8. Redémarrage automatique d'Antigravity Desktop si actif
    msg = f"Conversation déplacée vers « {target_project_name} » avec succès."
    if restart_desktop and "PYTEST_CURRENT_TEST" not in os.environ:
        if restart_antigravity_desktop_if_running():
            msg += "\n\n🔄 Google Antigravity Desktop a été redémarré automatiquement pour appliquer le changement."

    return True, msg


# ---------------------------------------------------------------------------
# Export Markdown d'une conversation
# ---------------------------------------------------------------------------
_MD_SLUG_RE = re.compile(r"[^\w\-]+", re.UNICODE)

# Artéfacts du dossier brain joints en annexe de l'export.
_EXPORT_ARTIFACTS = (
    ("walkthrough.md", "Walkthrough & Synthèse"),
    ("implementation_plan.md", "Plan d'implémentation"),
    ("task.md", "Tâche"),
)

# Images d'une session : où chercher, et sous quel intitulé.
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg")
_IMAGE_SOURCES = (
    ("", "Images générées"),
    (".tempmediaStorage", "Médias temporaires"),
    (".user_uploaded", "Images fournies par l'utilisateur"),
)
# Epoch (10 à 13 chiffres) inclus dans un nom de fichier : media_1788373607544.png


def _image_generation_times(conv_id: str) -> dict[str, float]:
    """Corrèle chaque image à l'instant où elle a été générée, d'après le
    transcript.

    Les lignes `type == "GENERATE_IMAGE"` du transcript portent un `created_at`
    dans le MÊME référentiel que les messages, et leur `content` cite le nom du
    fichier produit. L'epoch inscrit dans le nom du fichier
    (`..._1788371000315.jpg`), lui, est sur un autre référentiel décalé et ne
    doit pas servir à la corrélation.

    Retour : { "nom_de_fichier.jpg": epoch_secondes }.
    """
    transcript = _find_transcript_file(conv_id)
    if not transcript or not transcript.is_file():
        return {}
    out: dict[str, float] = {}
    name_re = re.compile(r"[\w.\-]+\.(?:png|jpe?g|webp|gif|bmp|svg)", re.IGNORECASE)
    try:
        with transcript.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"GENERATE_IMAGE"' not in line and "GENERATE_IMAGE" not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") != "GENERATE_IMAGE":
                    continue
                ts = obj.get("created_at", "")
                if not ts:
                    continue
                try:
                    epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
                blob = obj.get("content", "") or json.dumps(obj, ensure_ascii=False)
                for m in name_re.finditer(blob):
                    fname = m.group(0).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                    # Garde la 1re occurrence (l'instant de génération).
                    out.setdefault(fname, epoch)
    except OSError as exc:
        logger.debug("_image_generation_times(%s) : %s", conv_id, exc)
    return out


def _collect_session_images(brain_path: Path) -> list[tuple[str, Path]]:
    """Retourne [(label_de_section, chemin_fichier), …] pour toutes les images
    d'une session, dans l'ordre : générées, temporaires, uploadées."""
    out: list[tuple[str, Path]] = []
    for sub, label in _IMAGE_SOURCES:
        d = brain_path / sub if sub else brain_path
        if not d.is_dir():
            continue
        try:
            files = sorted(
                p for p in d.iterdir()
                if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
            )
        except OSError as exc:
            logger.warning("Lecture du dossier images %s échouée : %s", d, exc)
            continue
        for p in files:
            out.append((label, p))
    return out




def _slugify(text: str, max_len: int = 60) -> str:
    """Transforme un titre en fragment de nom de fichier sûr."""
    s = _MD_SLUG_RE.sub("-", (text or "").strip()).strip("-")
    return (s[:max_len].strip("-") or "conversation")


# Liens Markdown pointant vers un fichier local absolu : [texte](file:///…)
# ou [texte](C:/… / C:\…). On les neutralise dans l'export (chemin qui casse
# si le projet est déplacé).
_MD_FILE_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(\s*(?:file:///)?([A-Za-z]:[\\/][^)\s]+)\s*\)"
)


def _sanitize_message_text(text: str, project_root: Path | None) -> str:
    """Rend le texte d'un message portable pour un export archivé.

    Un lien `[config.py](file:///E:/Dev/Projet/config.py)` devient :
      - `[config.py](config.py)` si le chemin est SOUS `project_root` ;
      - `` `config.py` `` (code inline) sinon.
    """
    if not text or "](" not in text:
        return text

    root_str = ""
    if project_root is not None:
        try:
            root_str = str(project_root.resolve()).replace("\\", "/").rstrip("/").lower()
        except OSError:
            root_str = str(project_root).replace("\\", "/").rstrip("/").lower()

    def _repl(m: "re.Match[str]") -> str:
        label, raw_path = m.group(1), m.group(2)
        norm = raw_path.replace("\\", "/")
        if root_str and norm.lower().startswith(root_str + "/"):
            rel = norm[len(root_str) + 1:]
            return f"[{label}]({rel})"
        return f"`{label}`"

    return _MD_FILE_LINK_RE.sub(_repl, text)


def build_conversation_markdown(
    conv_id: str,
    title: str = "",
    project: str = "",
    images: list[tuple] | None = None,
) -> str:
    """Construit le document Markdown complet d'une conversation.

    En-tête (titre / projet / date / ID) + messages (### 👤 Utilisateur /
    ### ✨ Antigravity), avec les images HORODATÉES intercalées juste après le
    message correspondant, + annexe des artéfacts + section « Images » de fin
    pour les images sans horodatage.

    `images` : liste de (label_section, chemin_relatif, nom_source) résolue par
    l'appelant (`_copy_session_images`). `nom_source` sert à retrouver l'instant
    de génération dans le transcript. Tolère aussi les 2-tuples
    (label, chemin) — l'image ira alors en section « Images » de fin. Si None,
    la section Images liste simplement les noms présents dans le brain.
    """
    fallback_title, last_dt = get_transcript_info(conv_id)
    disp_title = title or fallback_title or conv_id[:12]
    date_str = last_dt.strftime("%Y-%m-%d %H:%M") if last_dt else "date inconnue"

    lines: list[str] = [
        f"# {disp_title}",
        "",
        f"- **Projet :** {project or '(aucun)'}",
        f"- **Dernière activité :** {date_str}",
        f"- **ID de session :** `{conv_id}`",
        f"- **Exporté le :** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
    ]

    def _img_md(rel: str) -> str:
        return f"![{Path(rel).name}]({rel})"

    messages = load_chat_messages(conv_id)

    # Note de provenance si le dialogue ne vient pas d'un transcript complet
    # (parité avec le bandeau de l'interface).
    _psrc = next((m.get("partial_source") for m in messages if m.get("partial_source")), None)
    if _psrc:
        _note = {
            "bridge": "> ℹ️ Dialogue reconstruit via Antigravity (session au format hérité). "
                      "Pas d'horodatage par message.",
            "transcript_partial": "> ℹ️ Aperçu partiel : seules les dernières étapes de cette session "
                                  "ont un journal complet.",
            "overview": "> ℹ️ Aperçu partiel reconstitué depuis un résumé de session.",
        }.get(_psrc)
        if _note:
            lines.extend([_note, ""])

    # Racine du projet cible (pour rendre les liens fichiers portables).
    project_root: Path | None = None
    if project:
        try:
            project_root = get_projects_root() / project
        except Exception:
            project_root = None

    # Corrélation image -> instant de génération (via les lignes GENERATE_IMAGE
    # du transcript, même référentiel que les messages).
    gen_times = _image_generation_times(conv_id) if images else {}

    # Ventilation : image datée (placement inline) vs non datée (section fin).
    dated_images: list[tuple[str, str, float]] = []
    undated_images: list[tuple[str, str]] = []
    if images:
        for entry in images:
            label, rel = entry[0], entry[1]
            src_name = entry[2] if len(entry) >= 3 else Path(rel).name
            epoch = gen_times.get(src_name) or gen_times.get(Path(rel).name)
            if epoch is not None:
                dated_images.append((label, rel, epoch))
            else:
                undated_images.append((label, rel))
    dated_images.sort(key=lambda e: e[2])

    if messages:
        # Epoch de chaque message (0.0 si absent) ; on garde les indices des
        # messages RÉELLEMENT horodatés pour trouver le bon point d'insertion.
        msg_epochs = [float(m.get("epoch") or 0.0) for m in messages]
        img_idx = 0

        for i, msg in enumerate(messages):
            role = "👤 Utilisateur" if msg.get("role") == "user" else "✨ Antigravity"
            ts = msg.get("timestamp", "")
            head = f"### {role}" + (f"  ·  {ts}" if ts else "")
            lines.append(head)
            lines.append("")
            lines.append(
                _sanitize_message_text(
                    (msg.get("text", "") or "").rstrip(), project_root
                )
            )
            lines.append("")

            # Prochain message horodaté après celui-ci -> borne haute.
            next_epoch = float("inf")
            for j in range(i + 1, len(messages)):
                if msg_epochs[j] > 0:
                    next_epoch = msg_epochs[j]
                    break

            emitted = False
            while img_idx < len(dated_images) and dated_images[img_idx][2] < next_epoch:
                _lbl, rel, _ep = dated_images[img_idx]
                if not emitted:
                    lines.append("**Images de cet échange :**")
                    lines.append("")
                    emitted = True
                lines.append(_img_md(rel))
                lines.append("")
                img_idx += 1

            lines.append("---")
            lines.append("")

        # Images datées postérieures au dernier message.
        if img_idx < len(dated_images):
            lines.append("### ✨ Antigravity  ·  (images finales)")
            lines.append("")
            while img_idx < len(dated_images):
                _lbl, rel, _ep = dated_images[img_idx]
                lines.append(_img_md(rel))
                lines.append("")
                img_idx += 1
            lines.append("---")
            lines.append("")
    else:
        lines.append("_Aucun message textuel dans les journaux de cette session._")
        lines.append("")
        # Sans messages : toutes les images vont en section de fin.
        undated_images = [(e[0], e[1]) for e in images] if images else []
        dated_images = []

    # Annexe : artéfacts du dossier brain.
    brain_p = _find_brain_path(conv_id)
    appended_any = False
    if brain_p and brain_p.is_dir():
        for fname, label in _EXPORT_ARTIFACTS:
            fpath = brain_p / fname
            if fpath.is_file():
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore").strip()
                except OSError as exc:
                    logger.warning("Lecture artéfact %s échouée : %s", fpath, exc)
                    continue
                if not content:
                    continue
                if not appended_any:
                    lines.append("## Annexe — Artéfacts de session")
                    lines.append("")
                    appended_any = True
                lines.append(f"### {label} (`{fname}`)")
                lines.append("")
                lines.append(content)
                lines.append("")
                lines.append("---")
                lines.append("")

    # Section « Images » de fin : uniquement les images NON horodatées
    # (les horodatées ont été placées inline après leur message).
    if images:
        if undated_images:
            note = (
                " (horodatées placées ci-dessus dans leur échange)"
                if dated_images else ""
            )
            lines.append(f"## Images{note}")
            lines.append("")
            current_label = None
            for label, rel_path in undated_images:
                if label != current_label:
                    lines.append(f"### {label}")
                    lines.append("")
                    current_label = label
                lines.append(f"![{Path(rel_path).name}]({rel_path})")
                lines.append("")
            lines.append("---")
            lines.append("")
    elif brain_p and brain_p.is_dir():
        # Pas de copie demandée : on liste au moins les noms trouvés.
        found = _collect_session_images(brain_p)
        if found:
            lines.append("## Images")
            lines.append("")
            current_label = None
            for label, fpath in found:
                if label != current_label:
                    lines.append(f"### {label}")
                    lines.append("")
                    current_label = label
                lines.append(f"- 🖼️ `{fpath.name}`")
            lines.append("")
            lines.append("_(images non copiées — export texte seul)_")
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _copy_session_images(brain_path: Path, dest_dir: Path) -> list[tuple[str, str, str]]:
    """Copie toutes les images de la session dans `dest_dir` et retourne
    [(label_section, chemin_relatif "<dir>/<nom_dest>", nom_source), …].

    `nom_source` (le nom d'origine, avant désambiguïsation) sert à corréler
    l'image avec les messages via `_image_generation_times`. Les collisions de
    noms (même nom dans deux sous-dossiers) sont résolues par suffixe numérique.
    """
    found = _collect_session_images(brain_path)
    if not found:
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    result: list[tuple[str, str, str]] = []
    for label, src in found:
        name = src.name
        if name in used:
            stem, suf = src.stem, src.suffix
            i = 2
            while f"{stem}_{i}{suf}" in used:
                i += 1
            name = f"{stem}_{i}{suf}"
        used.add(name)
        try:
            shutil.copy2(src, dest_dir / name)
        except OSError as exc:
            logger.warning("Copie image %s échouée : %s", src, exc)
            continue
        result.append((label, f"{dest_dir.name}/{name}", src.name))
    return result


def default_export_filename(conv_id: str, title: str = "") -> str:
    """Nom de fichier proposé : <date>_<titre-slug>_<id8>.md."""
    fallback_title, last_dt = get_transcript_info(conv_id)
    date_part = last_dt.strftime("%Y%m%d") if last_dt else "nodate"
    slug = _slugify(title or fallback_title or conv_id[:12])
    return f"{date_part}_{slug}_{conv_id[:8]}.md"


def _write_export(conv_id: str, out_path: Path, title: str, project: str) -> tuple[bool, str]:
    """Écrit le .md à `out_path` en copiant d'abord les images de la session
    dans `<nom_du_md_sans_extension>_images/` à côté du fichier."""
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        brain_p = _find_brain_path(conv_id)
        images: list[tuple[str, str]] = []
        if brain_p and brain_p.is_dir():
            img_dir = out_path.parent / f"{out_path.stem}_images"
            # `_copy_session_images` renvoie déjà des chemins relatifs
            # « <img_dir.name>/<nom> », directement utilisables depuis le .md.
            images = _copy_session_images(brain_p, img_dir)
        md = build_conversation_markdown(
            conv_id, title=title, project=project, images=images or None
        )
        out_path.write_text(md, encoding="utf-8")
        logger.debug(
            "Conversation %s exportée -> %s (%d image(s))", conv_id, out_path, len(images)
        )
        n_img = len(images)
        suffix = f" (+{n_img} image{'s' if n_img > 1 else ''})" if n_img else ""
        return True, f"{out_path}{suffix}"
    except Exception as exc:
        logger.warning("Échec export vers %s pour %s : %s", out_path, conv_id, exc)
        return False, f"Échec de l'export : {exc}"


def export_conversation_to_project(
    conv_id: str, project_name: str, title: str = ""
) -> tuple[bool, str]:
    """Écrit l'export dans `<racine projets>/<project_name>/_conversations/`."""
    projects_root = get_projects_root()
    out_path = (
        projects_root / project_name / "_conversations"
        / default_export_filename(conv_id, title)
    )
    return _write_export(conv_id, out_path, title, project_name)


def export_conversation_to_path(
    conv_id: str, out_path: str | Path, title: str = "", project: str = ""
) -> tuple[bool, str]:
    """Écrit l'export Markdown à l'emplacement `out_path` choisi par l'utilisateur."""
    return _write_export(conv_id, Path(out_path), title, project)


# ---------------------------------------------------------------------------
# Export / archivage au niveau d'un PROJET
# ---------------------------------------------------------------------------
ProgressCB = "Callable[[int, int, str], None] | None"


def export_project_conversations(
    project_name: str, convs, dest_dir: "Path | None" = None, progress_cb=None
) -> tuple[int, int, Path]:
    """Exporte toutes les conversations `convs` en Markdown dans `dest_dir`.

    `dest_dir` par défaut : `<racine projets>/<project_name>/_conversations/`.
    `convs` : itérable d'objets ayant .conv_id / .title.
    Retourne (nb_ok, nb_echecs, dest_dir).
    """
    if dest_dir is None:
        dest_dir = get_projects_root() / project_name / "_conversations"
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    conv_list = list(convs)
    ok = 0
    fail = 0
    for i, c in enumerate(conv_list):
        title = getattr(c, "title", "") or ""
        out_path = dest_dir / default_export_filename(c.conv_id, title)
        success, _msg = _write_export(c.conv_id, out_path, title, project_name)
        if success:
            ok += 1
        else:
            fail += 1
        if progress_cb:
            progress_cb(i + 1, len(conv_list), c.conv_id)
    logger.debug(
        "export_project_conversations(%s) : %d ok / %d échecs -> %s",
        project_name, ok, fail, dest_dir,
    )
    return ok, fail, dest_dir


def archive_project(
    project_name: str, convs, zip_path: "str | Path", progress_cb=None
) -> tuple[bool, str]:
    """Crée un ZIP contenant l'export Markdown (+ images) de toutes les
    conversations du projet.

    Le ZIP est écrit à `zip_path` (l'appelant s'assure qu'il est HORS du dossier
    projet). Retourne (ok, message | chemin du zip).
    """
    zip_path = Path(zip_path)
    try:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="agm_archive_") as tmp:
            staging = Path(tmp) / project_name
            ok, fail, _ = export_project_conversations(
                project_name, convs, dest_dir=staging, progress_cb=progress_cb
            )
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(staging.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(staging.parent))
        logger.debug(
            "archive_project(%s) : %d conv(s), %d échec(s) -> %s",
            project_name, ok, fail, zip_path,
        )
        note = f" ({fail} échec(s))" if fail else ""
        return True, f"{zip_path}{note}"
    except Exception as exc:
        logger.warning("Échec archivage %s : %s", project_name, exc)
        return False, f"Échec de l'archivage : {exc}"



