"""claude_retention.py — Détection des conversations Claude Code proches de la
purge automatique.

Claude Code supprime lui-même ses transcrits inactifs après `cleanupPeriodDays`
jours (clé de `~/.claude/settings.json`, **défaut 30 jours**), sans
notification. Ce module calcule, pour chaque `ClaudeConv`, si elle approche de
ce délai — pour l'afficher en évidence dans l'arbre (section dédiée + couleur)
AVANT qu'elle ne disparaisse silencieusement.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("antigravity_manager.claude_retention")

#: clé dans ~/.claude/settings.json
_RETENTION_KEY = "cleanupPeriodDays"
#: valeur par défaut appliquée par Claude Code si la clé est absente
DEFAULT_RETENTION_DAYS = 30
#: marge d'alerte : nombre de jours avant la purge effective où l'on prévient
WARNING_MARGIN_DAYS = 7


def _claude_settings_path() -> Path:
    home = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())
    return home / ".claude" / "settings.json"


def get_retention_days() -> int:
    """Valeur effective de `cleanupPeriodDays` (défaut 30 si absent/invalide)."""
    path = _claude_settings_path()
    if not path.is_file():
        return DEFAULT_RETENTION_DAYS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        val = data.get(_RETENTION_KEY, DEFAULT_RETENTION_DAYS)
        return int(val) if int(val) > 0 else DEFAULT_RETENTION_DAYS
    except Exception as exc:
        logger.debug("Lecture de %s impossible (%s) : repli sur %d j", path, exc, DEFAULT_RETENTION_DAYS)
        return DEFAULT_RETENTION_DAYS


def days_until_purge(last_dt: datetime | None, retention_days: int, *, now: datetime | None = None) -> int | None:
    """Nombre de jours restants avant la purge de cette conversation.

    None si `last_dt` est inconnu (pas de date -> pas d'alerte possible).
    Peut être négatif (déjà passée la date théorique de purge côté Claude Code,
    mais le fichier existe encore sur cette machine).
    """
    if last_dt is None:
        return None
    now = now or datetime.now()
    purge_at = last_dt + timedelta(days=retention_days)
    remaining = (purge_at - now).total_seconds() / 86400
    return int(remaining) if remaining >= 0 else int(remaining) - 1  # troncature vers -inf


def is_near_expiry(
    last_dt: datetime | None,
    retention_days: int,
    *,
    warning_margin_days: int = WARNING_MARGIN_DAYS,
    now: datetime | None = None,
) -> bool:
    """Vrai si la conversation sera purgée par Claude Code dans moins de
    `warning_margin_days` jours (ou l'est déjà, côté théorique)."""
    remaining = days_until_purge(last_dt, retention_days, now=now)
    return remaining is not None and remaining <= warning_margin_days
