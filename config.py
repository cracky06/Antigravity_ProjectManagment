"""config.py — Gestion de la configuration persistante d'Antigravity Manager."""

import json
import os
from pathlib import Path

import sys

# Chemins par défaut
DEFAULT_PROJECTS_ROOT = r"D:\DEV"
DEFAULT_ANTIGRAVITY_ROOT = os.path.expandvars(r"%USERPROFILE%\.gemini\antigravity")

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
