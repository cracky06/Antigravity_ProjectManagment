"""antigravity_ls_bridge.py — Passerelle vers le `language_server` d'Antigravity.

Les 6 conversations « legacy » (avril/mai 2026) ne sont stockées que sous forme
de fichier binaire `conversations/<cid>.pb` au format « ProtoStore » Jetski,
compressé/opaque : pas de `transcript.jsonl`, pas de base SQLite, `brain/`
souvent vide. L'application Antigravity elle-même les lit en mémoire sans jamais
les réécrire sur disque.

Ce module interroge le `language_server.exe` d'Antigravity (qui tourne déjà en
tâche de fond quand l'app est ouverte) via son RPC Connect local pour convertir
une conversation en Markdown, puis le redécoupe en tours user/model.

Contraintes assumées :
  - dépend d'un binaire tiers (Google) et d'un process actif → utilisé
    UNIQUEMENT en dernier repli, après transcript.jsonl et le lecteur SQLite ;
  - dégradation silencieuse : si le serveur n'est pas là, tout renvoie None /
    liste vide, jamais d'exception ;
  - lecture pure : `ConvertTrajectoryToMarkdown` ne modifie rien sur disque
    (vérifié : mtime du .pb inchangé avant/après appel) ;
  - le Markdown rendu n'a PAS d'horodatage par message.

Découverte du serveur (spec établie avec l'agent Antigravity) :
  - process `language_server.exe` / `language_server_windows_x64.exe` dont la
    ligne de commande contient `--app_data_dir antigravity` (app standalone) ou
    `--app_data_dir antigravity-ide` (IDE) et `--csrf_token <uuid>` ;
  - `--https_server_port 0` => le port est attribué dynamiquement : on lit les
    ports en écoute du PID (il y en a 2, un seul parle HTTPS/RPC, on les essaie
    tous les deux) ;
  - le token CSRF n'est écrit nulle part sur disque : seule source = la ligne
    de commande du process.
"""

from __future__ import annotations

import json
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.request

_RPC_PATH = "/exa.language_server_pb.LanguageServerService/ConvertTrajectoryToMarkdown"

# Cache mémoire de la découverte : app_data_dir -> (expires_epoch, (token, ports))
# ou (expires_epoch, None) pour mémoriser une absence et ne pas relancer
# PowerShell à chaque conversation.
_DISCOVERY_TTL_OK = 120.0   # serveur trouvé : re-vérifie au bout de 2 min
_DISCOVERY_TTL_MISS = 15.0  # serveur absent : re-tente après 15 s
_discovery_cache: dict[str, tuple[float, tuple[str, list[int]] | None]] = {}

_PS_TEMPLATE = (
    "$procs = Get-CimInstance Win32_Process -Filter \"Name LIKE 'language_server%'\" "
    "-ErrorAction SilentlyContinue; "
    "foreach ($p in $procs) {{ "
    "  $cmd = $p.CommandLine; "
    "  if ($cmd -match '--app_data_dir\\s+{adir}(\\s|$)' "
    "      -and $cmd -match '--csrf_token\\s+([0-9a-fA-F-]+)') {{ "
    "    $token = $matches[1]; "
    "    $conns = Get-NetTCPConnection -OwningProcess $p.ProcessId -State Listen "
    "      -LocalAddress '127.0.0.1' -ErrorAction SilentlyContinue; "
    "    $ports = ($conns | Select-Object -ExpandProperty LocalPort) -join ','; "
    "    [PSCustomObject]@{{ Token = $token; Ports = $ports }} | ConvertTo-Json -Compress; "
    "    break; "
    "  }} "
    "}}"
)

_VALID_ADIR = re.compile(r"^[A-Za-z0-9_-]+$")


def _discover(app_data_dir: str) -> tuple[str, list[int]] | None:
    """(token, ports) du language_server pour cet `app_data_dir`, ou None.

    Résultat mis en cache (succès comme échec) pour éviter de relancer
    PowerShell à chaque conversation consultée.
    """
    now = time.time()
    cached = _discovery_cache.get(app_data_dir)
    if cached and cached[0] > now:
        return cached[1]

    result: tuple[str, list[int]] | None = None
    if _VALID_ADIR.match(app_data_dir):
        ps = _PS_TEMPLATE.format(adir=re.escape(app_data_dir))
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            out = (proc.stdout or "").strip()
            if out:
                info = json.loads(out)
                token = info.get("Token") or ""
                ports = [
                    int(p) for p in str(info.get("Ports", "")).split(",") if p.isdigit()
                ]
                if token and ports:
                    result = (token, ports)
        except Exception:
            result = None

    ttl = _DISCOVERY_TTL_OK if result else _DISCOVERY_TTL_MISS
    _discovery_cache[app_data_dir] = (now + ttl, result)
    return result


def _invalidate(app_data_dir: str) -> None:
    _discovery_cache.pop(app_data_dir, None)


def is_server_available(app_data_dir: str = "antigravity") -> bool:
    """Vrai si un language_server exploitable est détecté (avec cache)."""
    return _discover(app_data_dir) is not None


def bridge_convert_trajectory(
    conv_id: str, app_data_dir: str = "antigravity"
) -> str | None:
    """Markdown complet d'une conversation via le language_server local, ou None.

    None si : serveur absent, conversation inconnue du serveur, erreur réseau.
    Jamais d'exception propagée.
    """
    disc = _discover(app_data_dir)
    if disc is None:
        return None
    token, ports = disc

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    payload = json.dumps({"conversationId": conv_id}).encode("utf-8")
    headers = {"Content-Type": "application/json", "x-codeium-csrf-token": token}

    saw_connection = False
    for port in ports:
        url = f"https://127.0.0.1:{port}{_RPC_PATH}"
        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
                saw_connection = True
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    md = data.get("markdown")
                    if md:
                        return md
        except urllib.error.HTTPError as exc:
            # 200 impossible ici ; 500 "trajectory not found" => conv inconnue,
            # inutile d'essayer l'autre port.
            saw_connection = True
            if exc.code == 500:
                return None
        except (urllib.error.URLError, TimeoutError, OSError):
            # port fermé / mauvais protocole : on tente le suivant
            continue

    if not saw_connection:
        # Aucun port n'a répondu : le process a peut-être disparu depuis la
        # découverte -> on purge le cache pour re-scanner au prochain appel.
        _invalidate(app_data_dir)
    return None


_HEADER_RE = re.compile(r"^###\s+(User Input|Planner Response)\s*$", re.MULTILINE)
_INTRO_NOTE_RE = re.compile(
    r"^\s*#\s*Chat Conversation\s*\n+"
    r"(?:Note:.*?\n+)?",
    re.DOTALL,
)


def parse_trajectory_markdown(md: str) -> list[dict]:
    """Redécoupe le Markdown `ConvertTrajectoryToMarkdown` en tours de dialogue.

    Retourne `[{role: 'user'|'model', text: str, timestamp: ''}]` — pas
    d'horodatage disponible dans ce rendu.
    """
    if not md:
        return []

    body = _INTRO_NOTE_RE.sub("", md, count=1)

    parts: list[dict] = []
    matches = list(_HEADER_RE.finditer(body))
    for i, m in enumerate(matches):
        label = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        text = body[start:end].strip()
        if not text:
            continue
        role = "user" if label == "User Input" else "model"
        parts.append({"role": role, "text": text, "timestamp": ""})
    return parts


def load_bridge_messages(conv_id: str, app_data_dir: str = "antigravity") -> list[dict]:
    """Dialogue d'une conversation legacy via le bridge, `[]` si indisponible."""
    md = bridge_convert_trajectory(conv_id, app_data_dir)
    return parse_trajectory_markdown(md) if md else []


def bridge_first_user_title(
    conv_id: str, app_data_dir: str = "antigravity"
) -> str:
    """Titre de repli = 1re ligne non vide du 1er message utilisateur, ou ''."""
    for msg in load_bridge_messages(conv_id, app_data_dir):
        if msg["role"] == "user":
            for line in msg["text"].splitlines():
                line = line.strip()
                if line:
                    return line[:80]
    return ""
