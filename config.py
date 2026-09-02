"""config.py — Gestion de la configuration persistante d'Antigravity Manager."""

import json
import os
from pathlib import Path

import sys

# Détection dynamique des chemins par défaut
def _detect_default_projects_root() -> str:
    for candidate in [r"E:\Dev", r"D:\DEV", r"C:\DEV"]:
        if Path(candidate).is_dir():
            return candidate
    return r"D:\DEV"


def _detect_default_antigravity_root() -> str:
    # Priorité à antigravity-ide (Antigravity 2.0 / version actuelle)
    ide_path = Path(os.path.expandvars(r"%USERPROFILE%\.gemini\antigravity-ide"))
    if ide_path.is_dir():
        return str(ide_path)
    return os.path.expandvars(r"%USERPROFILE%\.gemini\antigravity")


DEFAULT_PROJECTS_ROOT = _detect_default_projects_root()
DEFAULT_ANTIGRAVITY_ROOT = _detect_default_antigravity_root()

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

CONFIG_FILE = _get_base_dir() / "config.json"


def load_config() -> dict:
    """Charge la configuration depuis le fichier config.json ou initialise avec les valeurs par défaut."""
    config = {
        "projects_root": DEFAULT_PROJECTS_ROOT,
        "antigravity_root": DEFAULT_ANTIGRAVITY_ROOT,
        "theme": "light",
    }
    if CONFIG_FILE.is_file():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                saved = json.load(f)
                config.update(saved)
        except Exception:
            pass
    return config


def save_config(config: dict) -> None:
    """Sauvegarde la configuration dans config.json."""
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la configuration : {e}")


def get_projects_root() -> Path:
    cfg = load_config()
    return Path(cfg.get("projects_root", DEFAULT_PROJECTS_ROOT))


def get_antigravity_root() -> Path:
    cfg = load_config()
    return Path(cfg.get("antigravity_root", DEFAULT_ANTIGRAVITY_ROOT))
