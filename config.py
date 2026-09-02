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
        "theme": "system",
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


def detect_system_theme() -> str:
    """Détecte le thème du système d'exploitation Windows ('dark' ou 'light')."""
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if val == 1 else "dark"
        except Exception:
            pass
    return "dark"


def get_active_theme() -> str:
    """Retourne le thème effectif à appliquer ('dark' ou 'light')."""
    cfg = load_config()
    theme_choice = cfg.get("theme", "system").lower()
    if theme_choice in ("dark", "light"):
        return theme_choice
    return detect_system_theme()


# -----------------------------------------------------------------
# Gestion des Versions & Changelog
# -----------------------------------------------------------------
def get_app_version() -> str:
    """Lit le numéro de version depuis le fichier VERSION ou fallback sur 1.0."""
    version_file = _get_base_dir() / "VERSION"
    if version_file.is_file():
        try:
            v = version_file.read_text(encoding="utf-8").strip()
            if v:
                return v
        except Exception:
            pass
    return "1.0"


def get_last_seen_version() -> str:
    """Retourne la dernière version enregistrée lors d'un lancement précédent."""
    cfg = load_config()
    return cfg.get("last_seen_version", "")


def set_last_seen_version(version: str) -> None:
    """Enregistre la version actuelle comme ayant été vue."""
    cfg = load_config()
    cfg["last_seen_version"] = version
    save_config(cfg)


def get_changelog_data() -> dict[str, dict[str, list[str]]]:
    """Retourne l'historique structuré des versions."""
    return {
        "v1.0": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Migration complète de l'interface vers PyQt6 (zéro scintillement, dépliage natif C++ fluide)",
                "Déplacement officiel de conversations vers un projet (mise à jour binaire protobuf pour synchronisation directe avec Antigravity IDE)",
                "Filtre par projet dans la barre latérale (Tous les projets, Sans projet, projet individuel)",
                "Badge du projet associé dans la liste des conversations récentes",
                "Bascule d'affichage entre Vue Riche HTML et Source Markdown brute (<>)",
                "Prise en charge intégrale des thèmes Système (par défaut), Sombre et Clair avec bascule à chaud",
                "Gestion formelle des numéros de version (fichier VERSION et affichage dans le titre)",
                "Fenêtre de changelog modeless automatique lors de nouvelles versions",
            ],
            "🐛 Corrections & Robustesse (fix)": [
                "Élimination définitive des faux projets 'n' et 'nLast' (assainissement des sauts de ligne dans les logs)",
                "Correction du contraste du texte en thème clair (remplacement du texte blanc par un gris foncé lisible)",
                "Dépliage intelligent des dossiers (repliés en vue globale, dépliés en vue filtrée)",
                "Navigation fluide au clavier avec les flèches haut/bas dans l'arborescence",
                "Gestion robuste des sessions de sous-agents techniques (affichage d'artéfacts et résumé des actions)",
            ],
            "🎨 Identité Visuelle & Ergonomie (ui)": [
                "Intégration de l'icône officielle Antigravity Manager (vecteur 2D colorisé sur fond noir)",
                "Enregistrement de l'AppUserModelID Windows pour un affichage parfait dans la barre des tâches",
                "Logo d'application affiché dans la barre latérale et la barre de titre",
            ],
        }
    }


