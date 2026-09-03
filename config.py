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
    """Lit le numéro de version depuis le fichier VERSION.

    En mode PyInstaller --onefile, VERSION est embarqué dans sys._MEIPASS.
    En mode développement ou --onedir, il est à côté de l'exécutable.
    """
    candidates: list[Path] = []
    # 1. Dossier temporaire PyInstaller (_MEIPASS) — prioritaire en mode --onefile
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(getattr(sys, "_MEIPASS")) / "VERSION")
    # 2. Répertoire de l'exécutable (mode --onedir ou développement)
    candidates.append(_get_base_dir() / "VERSION")

    for version_file in candidates:
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
        "v1.6": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Barre de recherche locale : boutons [.*] (expression régulière) et [Aa] (respect de la casse), indépendants de la recherche globale",
                "Surlignage et navigation des occurrences en mode regex, avec correspondances de longueur variable correctement mises en évidence",
                "Le mode regex de la find bar s'aligne automatiquement sur celui de la recherche globale lors du pré-remplissage (modifiable ensuite)",
            ],
            "🐛 Corrections (fix)": [
                "Un motif regex invalide dans la find bar affiche une bordure rouge et 0 résultat au lieu de rester silencieux",
                "Les correspondances vides (motifs type « a* ») sont ignorées pour éviter tout blocage",
            ],
        },
        "v1.5": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Index de recherche plein-texte SQLite FTS5 : la recherche globale est désormais instantanée (plus de parsing des transcripts à chaque frappe)",
                "Trois modes de recherche via les boutons [.*] et [Ab] du champ : « contient » (défaut), « mots » (index FTS, tolérant aux accents et aux préfixes) et « regex » (expression régulière, bordure rouge si le motif est invalide)",
                "Recherche exécutée en tâche de fond : l'interface ne se fige plus, même au premier lancement sur « Tous les projets »",
                "Barre de recherche locale : compteur d'occurrences « n / total », surlignage de toutes les occurrences, navigation ▲/▼ (et F3 / Maj+F3) avec wrap-around",
                "Bouton « Réindexer » dans les Paramètres + affichage de l'état de l'index (prêt / absent / corrompu)",
            ],
            "🐛 Corrections & Robustesse (fix)": [
                "Reconstruction automatique de l'index s'il est détecté corrompu, avec repli sur la recherche à la volée le temps de l'indexation",
                "Suppression d'un QApplication.processEvents() réentrant dans le rechargement des données (source de plantages rares)",
            ],
            "🔧 Qualité & Outillage (chore)": [
                "Couverture de tests portée à 54 tests (module d'index, modes de recherche, compteur de la find bar, isolation de l'index en test)",
            ],
        },
        "v1.4": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Raccourcis clavier : Ctrl+K / Ctrl+L (recherche globale), F3 / Maj+F3 (occurrence suivante / précédente), Échap (ferme la barre de recherche locale ou efface la recherche globale)",
            ],
            "🔧 Qualité & Outillage (chore)": [
                "Couverture de tests étendue à 33 tests (aperçu de fichier, navigation ←, pile d'historique, raccourcis clavier)",
                "Build-App.ps1 : suppression de build/ et dist/ avec réessais (contourne les verrous transitoires de l'Explorateur / de l'IDE)",
                "Ajout d'un .gitattributes (fins de ligne normalisées, fin des avertissements « LF will be replaced by CRLF »)",
            ],
        },
        "v1.3": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Aperçu du contenu des fichiers référencés : un clic sur un lien fichier affiche son contenu directement dans la vue discussion (jamais d'exécution), avec coloration syntaxique Pygments (.py, .bat, .ps1, .json, .yaml…)",
                "Bouton ← Retour repensé : revient à la conversation précédente, ou depuis un aperçu de fichier à la conversation d'origine (un seul niveau)",
            ],
            "🐛 Corrections (fix)": [
                "Les liens de fichiers (.py, .bat, .ps1, .json…) ne sont plus ouverts avec leur application associée — fin des exécutions accidentelles (ex. un clic sur build.bat lançait le build de l'app depuis une conversation)",
                "Fix du bouton ← qui, à cause de la navigation interne de QTextBrowser sur les liens file:///, renvoyait au dernier lien ouvert au lieu de la conversation, puis disparaissait en laissant une page vide",
                "Fix word-wrap dans la vue discussion : les blocs de code et commandes longues (.bat/.ps1/.json) s'enroulent au lieu de déborder horizontalement (pre, pre code, code inline)",
            ],
        },
        "v1.2": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Recherche globale dans le contenu de toutes les discussions (barre de recherche au-dessus du filtre projet)",
                "Filtrage des résultats de recherche selon le projet sélectionné dans le combo",
                "Barre de recherche locale (Find Bar) dans la vue discussion avec navigation ▲/▼ et wrap-around",
                "Pré-remplissage automatique de la find bar depuis la recherche globale",
                "Bouton 🔍 dans le header pour ouvrir ou fermer la barre de recherche locale",
            ],
            "🐛 Corrections (fix)": [
                "Fix word-wrap des liens file:/// dans la vue discussion (débordements horizontaux éliminés)",
                "Fix lecture du fichier VERSION en mode --onefile PyInstaller (détection via sys._MEIPASS)",
            ],
        },
        "v1.1": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Intégration du parseur Markdown officiel avec prise en charge complète de la syntaxe (# titres, **gras**, listes, code)",
                "Support des tableaux Markdown, citations et retours à la ligne automatiques",
            ],
            "🎨 Identité Visuelle & Ergonomie (ui)": [
                "Mise en page typographique soignée avec bordures et contrastes adaptés aux thèmes clair et sombre",
                "Mode <> Source pour inspecter le code source brut à tout moment",
            ],
        },
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


