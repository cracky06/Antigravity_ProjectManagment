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
    # Priorité à antigravity-ide (Antigravity 2.0 / version actuelle).
    # On renvoie la forme LITTÉRALE (%USERPROFILE%…), comme DEFAULT_CLAUDE_ROOT :
    # c'est ce qui s'affiche/s'enregistre dans les Paramètres, et
    # `get_antigravity_root()` résout la variable à la lecture. Sinon la
    # variable disparaît dès la première sauvegarde de config.json.
    if Path(os.path.expandvars(r"%USERPROFILE%\.gemini\antigravity-ide")).is_dir():
        return r"%USERPROFILE%\.gemini\antigravity-ide"
    return r"%USERPROFILE%\.gemini\antigravity"


DEFAULT_PROJECTS_ROOT = _detect_default_projects_root()
DEFAULT_ANTIGRAVITY_ROOT = _detect_default_antigravity_root()
# Dossier des transcripts Claude Code (partagé par l'extension VS Code et
# l'onglet « Code » de Claude Desktop). Gardé sous forme littérale
# (`%USERPROFILE%`) : c'est ce qui s'affiche dans les Paramètres, et
# `get_claude_root()` résout la variable à la lecture.
DEFAULT_CLAUDE_ROOT = r"%USERPROFILE%\.claude\projects"
DEFAULT_CODEX_ROOT = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")

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
        "claude_root": DEFAULT_CLAUDE_ROOT,
        "codex_root": DEFAULT_CODEX_ROOT,
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


def get_ui_state() -> dict:
    """Retourne l'état d'interface persistant (géométrie fenêtre, splitter, filtre).

    Forme : {"geometry": <str base64>, "splitter": [int, int],
             "project_filter": <str>}. Clés absentes = valeurs par défaut.
    """
    cfg = load_config()
    state = cfg.get("ui_state", {})
    return state if isinstance(state, dict) else {}


def save_ui_state(state: dict) -> None:
    """Fusionne `state` dans la clé `ui_state` de config.json."""
    cfg = load_config()
    current = cfg.get("ui_state", {})
    if not isinstance(current, dict):
        current = {}
    current.update(state)
    cfg["ui_state"] = current
    save_config(cfg)


def get_projects_root() -> Path:
    cfg = load_config()
    return Path(os.path.expandvars(cfg.get("projects_root", DEFAULT_PROJECTS_ROOT)))


def get_antigravity_root() -> Path:
    # `os.path.expandvars` : sinon une valeur saisie avec `%USERPROFILE%\...`
    # dans les Paramètres reste littérale et le dossier est introuvable.
    cfg = load_config()
    return Path(os.path.expandvars(cfg.get("antigravity_root", DEFAULT_ANTIGRAVITY_ROOT)))


def get_claude_root() -> Path:
    """Dossier des transcripts Claude Code, avec `%VAR%` résolues.

    Défaut : `%USERPROFILE%\\.claude\\projects`. La valeur peut être stockée
    littéralement (`%USERPROFILE%\\...`) ou en chemin absolu — les deux
    fonctionnent grâce à `expandvars`.
    """
    cfg = load_config()
    raw = cfg.get("claude_root", DEFAULT_CLAUDE_ROOT)
    return Path(os.path.expandvars(raw))


# ---------------------------------------------------------------------------
# Archivage automatique des conversations (voir archive.py)
# ---------------------------------------------------------------------------
#: modes de récurrence acceptés -> libellé affiché dans les Paramètres
ARCHIVE_FREQUENCIES = {
    "always": "À chaque lancement et avant chaque réindexation",
    "launch": "Au lancement de l'application uniquement",
    "daily": "Une fois par jour maximum",
    "weekly": "Une fois par semaine maximum",
    "manual": "Jamais automatiquement (bouton « Archiver » uniquement)",
}
DEFAULT_ARCHIVE_FREQUENCY = "always"

#: secondes correspondant aux modes throttlés
_ARCHIVE_MIN_INTERVAL = {"daily": 86_400, "weekly": 604_800}


def get_archive_frequency() -> str:
    """Récurrence de l'archivage : une clé de `ARCHIVE_FREQUENCIES`."""
    cfg = load_config()
    val = str(cfg.get("archive_frequency", DEFAULT_ARCHIVE_FREQUENCY)).lower()
    return val if val in ARCHIVE_FREQUENCIES else DEFAULT_ARCHIVE_FREQUENCY


def set_archive_frequency(value: str) -> None:
    cfg = load_config()
    cfg["archive_frequency"] = value if value in ARCHIVE_FREQUENCIES else DEFAULT_ARCHIVE_FREQUENCY
    save_config(cfg)


def get_archive_enabled() -> bool:
    """Vrai si l'archivage automatique doit tourner (mode ≠ 'manual')."""
    return get_archive_frequency() != "manual"


def get_last_archive_ts() -> float:
    """Horodatage (epoch) du dernier archivage réussi, 0.0 si jamais."""
    cfg = load_config()
    try:
        return float(cfg.get("last_archive_ts", 0.0))
    except (TypeError, ValueError):
        return 0.0


def set_last_archive_ts(ts: float) -> None:
    cfg = load_config()
    cfg["last_archive_ts"] = float(ts)
    save_config(cfg)


def archive_due(now: float | None = None) -> bool:
    """Décide si un archivage automatique doit avoir lieu maintenant.

    - 'manual'            -> jamais
    - 'always' / 'launch' -> oui (le déclencheur choisit QUAND appeler)
    - 'daily' / 'weekly'  -> seulement si l'intervalle est écoulé
    """
    import time as _time

    freq = get_archive_frequency()
    if freq == "manual":
        return False
    if freq in ("always", "launch"):
        return True
    min_interval = _ARCHIVE_MIN_INTERVAL.get(freq, 0)
    now = _time.time() if now is None else now
    return (now - get_last_archive_ts()) >= min_interval


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
        "v2.9": {
            "🐛 Corrections (fix)": [
                "Déplacement de conversation (move) : une discussion déplacée vers un autre projet apparaissait bien sous son nouveau projet dans AntigravityManager mais restait dans son projet d'origine dans Google Antigravity Desktop. La synchronisation met désormais à jour simultanément la base SQLite officielle d'Antigravity Desktop (conversation_summaries.db avec son project_id UUID, workspace_uris et BLOB raw_summary), le champ 4 du fichier agyhub_summaries_proto.pb, et les métadonnées de trajectoire de l'IDE (trajectory_metadata_blob)",
            ],
        },
        "v2.8": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Nouvelle source de données « Codex » (sélecteur en haut de la barre latérale, aux côtés d'Antigravity et Claude Code) : lit les conversations Codex locales, aussi bien les fichiers rollout JSONL que les bases SQLite en lecture seule",
                "Recherche globale plein texte dédiée aux conversations Codex, avec son propre index (codex_search_index.db)",
                "Archivage automatique et incrémental dédié à la source Codex, séparé des archives Antigravity et Claude Code",
                "Export Markdown/PDF des conversations Codex",
                "Section « ⏳ EXPIRENT BIENTÔT » (source Claude Code) : toujours en tête de l'arbre, même en vue projet filtré, liste les conversations que Claude Code supprimera dans moins de 7 jours — délai calculé sur la vraie valeur de cleanupPeriodDays (~/.claude/settings.json), pas le défaut. Compte à rebours affiché sur chaque entrée",
                "Ces conversations expirantes sont surlignées en rouge partout où elles apparaissent dans l'arbre, avec une infobulle donnant le nombre de jours restants ; le même avertissement apparaît dans l'en-tête de la vue discussion une fois ouverte",
                "Le bandeau de rappel sous l'arbre Claude Code affiche désormais le délai réellement configuré au lieu du défaut 30 jours codé en dur",
            ],
            "🐛 Corrections (fix)": [
                "La fenêtre « Quoi de neuf ? » marquait CHAQUE version listée comme « (Actuelle) » au lieu de la seule version installée — mention retirée",
            ],
        },
        "v2.7": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Archivage automatique et incrémental des conversations : au lancement et avant chaque (ré)indexation, une copie de secours de chaque conversation modifiée est écrite dans <projet>/_archive/ (brut sans images + export Markdown, régénéré en .zip). Seuls les projets ayant une conversation nouvelle ou modifiée sont réécrits ; une conversation archivée n'est jamais supprimée, même si Antigravity ne la connaît plus",
                "Récurrence de l'archivage paramétrable dans les Paramètres (à chaque lancement/réindexation, au lancement seulement, quotidien, hebdomadaire, ou jamais), plus un bouton « Archiver maintenant »",
                "Bouton 🔄 dans la vue discussion : rafraîchit uniquement la conversation ouverte (relit le transcript sur le disque) sans recharger tout l'arbre ni relancer l'indexation",
                "Bouton 🔴 Suivre : suit une discussion en direct, avec réaffichage automatique dès qu'une nouvelle ligne est écrite sur le disque — utile pour observer en direct une conversation pilotée par un orchestrateur (Claude Orchestrator, Antigravity + watcher, mode Multi-IA) dont les échanges n'apparaissent pas au fil de l'eau dans le chat du client",
            ],
            "🐛 Corrections (fix)": [
                "Un déplacement de conversation entre projets pouvait, dans de rares cas, réinitialiser l'index interne d'Antigravity (agyhub_summaries_proto.pb) et faire disparaître toutes les conversations de la liste. La réécriture de cet index est désormais validée avant d'être appliquée (annulée si des entrées seraient perdues) et se fait de façon atomique",
            ],
        },
        "v2.6": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Les conversations Antigravity portent un badge d'origine dans la barre latérale : [App] (application Antigravity) ou [IDE] (Antigravity IDE), avec le logo Antigravity en icône (fond blanc / fond noir) pour les distinguer d'un coup d'œil",
                "Rappel sous la source Claude Code : Claude Code supprime lui-même ses transcrits inactifs (défaut 30 jours, sans notification) — exportez en Markdown/PDF pour conserver une conversation au-delà",
            ],
            "🐛 Corrections (fix)": [
                "Les conversations récentes de l'Antigravity IDE (stockées en base SQLite dans conversations/*.db, sans dossier brain/) s'affichaient vides : titre illisible, aucune date, aucun message. Elles sont désormais lues intégralement — titre, date, projet et dialogue complet",
                "Les vieilles conversations Antigravity au format hérité (fichier .pb opaque, avril/mai 2026) affichaient « Aucun message textuel ». Si Antigravity est ouvert, leur dialogue complet est maintenant reconstruit à la volée via son moteur local ; sinon un aperçu partiel est reconstitué depuis les résumés de session. Un bandeau discret signale la reconstruction",
            ],
        },
        "v2.5": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Nouvelle source de données « Claude Code / Desktop » (sélecteur en haut de la barre latérale) : parcourt les conversations stockées localement par Claude Code (VS Code) et l'application Claude Desktop (~/.claude/projects/)",
                "Même expérience que la vue Antigravity : arbre en 3 sections (PROJETS / CONVERSATIONS HORS PROJET / CONVERSATIONS RÉCENTES), filtre par projet, badge d'origine (VS Code / Desktop) et date, dialogue avec le même rendu visuel riche",
                "Recherche globale plein texte dans les conversations Claude Code (3 modes : contient / mots / regex), index dédié",
                "Recherche locale dans la conversation ouverte (Ctrl+F) : surlignage, navigation entre occurrences",
                "Export d'une conversation ou de tout un projet en Markdown, et export d'un projet entier en PDF — écrits dans le dossier _conversations/ du vrai dossier de code du projet",
                "Suppression et déplacement volontairement absents pour cette source (ce sont des fichiers gérés par Claude Code, pas par l'application)",
                "Nouveau champ « Dossier Claude Code » dans les Paramètres (défaut : %USERPROFILE%\\.claude\\projects) — utile en cas d'installation non standard",
                "Si le dossier Claude Code est absent ou vide, la barre latérale affiche un message d'explication au lieu de sections vides",
            ],
            "🐛 Corrections (fix)": [
                "Les compteurs de conversations manquaient sur les titres de section « PROJETS » et « CONVERSATIONS RÉCENTES » (sur les deux sources) — ajoutés",
                "Une session Claude Code démarrée sur une autre machine ou interface (sans dossier local associé) mais contenant un vrai échange n'était plus visible — elle apparaît maintenant sous « CONVERSATIONS HORS PROJET »",
                "En filtrant sur un projet Claude Code précis, son dossier restait replié — corrigé",
            ],
        },
        "v2.4": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Clic droit sur un projet → « Exporter les N conversation(s) en Markdown » : exporte tout le projet dans son dossier _conversations/",
                "Clic droit sur un projet → « Exporter le projet en PDF » : un seul PDF pour tout le projet (page de garde, table des matières, une section par conversation avec en-tête/pied de page, annexe des images non corrélées à un échange) — généré via Edge/Chrome en mode headless (aucune dépendance ajoutée à l'app)",
                "La page de garde du PDF affiche automatiquement un visuel du projet s'il en trouve un dans ses dossiers assets (background, splash, logo, nom du projet ou icône .ico, dans cet ordre de préférence)",
                "Clic droit sur un projet → « Archiver (ZIP) et supprimer le projet » : crée un ZIP de toutes les conversations (Markdown + images) puis supprime le projet — pour conserver l'historique après suppression",
                "L'emplacement du ZIP est demandé (par défaut à côté du dossier projet) ; garde-fou empêchant de le placer dans le dossier qui va être supprimé",
            ],
            "⚡ Performance / distribution (perf)": [
                "Exécutable allégé de ~37 Mo à ~25 Mo : suppression d'opengl32sw.dll (rasterizer logiciel inutile), de Qt6Pdf.dll (l'export PDF n'utilise plus le moteur PDF de Qt) et des traductions Qt non françaises",
            ],
        },
        "v2.3": {
            "🎨 Identité Visuelle & Ergonomie (ui)": [
                "Nouvelle fenêtre « À propos » (bouton dans les Paramètres) : illustration, version et lien vers le dépôt GitHub",
                "Bandeau d'illustration ajouté au README du dépôt",
            ],
        },
        "v2.2": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Menu contextuel (clic droit) sur les liens de fichiers dans la vue discussion : copier le lien, ouvrir le dossier parent, révéler dans l'Explorateur",
                "Export Markdown : les liens vers des fichiers absolus sont rendus portables — chemin relatif au projet s'ils sont dedans, sinon simple code (le document reste valide même déplacé)",
                "L'index de recherche se met à jour au fil de l'eau lorsqu'une conversation est consultée (plus besoin d'attendre la synchronisation groupée)",
            ],
            "🛡️ Robustesse (fix)": [
                "Capture globale des exceptions non gérées, y compris celles levées dans les gestionnaires d'événements Qt (clics, minuteries) auparavant avalées silencieusement : elles sont ajoutées à crash.log",
                "crash.log est désormais alimenté en mode ajout (les incidents successifs ne s'écrasent plus)",
            ],
        },
        "v2.1": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Export Markdown : les images générées sont désormais placées directement dans l'échange auquel elles correspondent, au lieu d'être toutes reléguées en fin de document",
                "La corrélation image ↔ message se fait via les événements « génération d'image » du journal (horodatage fiable), et non plus via le nom du fichier",
                "Les images non corrélées (téléversées, médias temporaires) restent regroupées dans la section « Images » de fin",
            ],
        },
        "v2.0": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "Export d'une conversation en Markdown (clic droit) : « Exporter en Markdown dans le projet » écrit dans <projet>/_conversations/<date>_<titre>_<id>.md, « Exporter en Markdown… » ouvre un sélecteur d'emplacement",
                "L'export inclut l'en-tête (titre, projet, date, ID), tous les messages, et une annexe avec les artéfacts de session (walkthrough.md, implementation_plan.md, task.md) s'ils existent",
                "Les images de la session sont copiées à côté du .md (dans <nom>_images/) et référencées en liens relatifs : images générées, médias temporaires et images fournies par l'utilisateur — le document exporté est autonome",
            ],
            "🎨 Identité Visuelle & Ergonomie (ui)": [
                "Barre latérale réorganisée en 3 sections : PROJETS, CONVERSATIONS HORS PROJET (nouveau — pour repérer et déplacer les conversations orphelines), CONVERSATIONS RÉCENTES (repliée par défaut)",
                "Les titres de section sont alignés à gauche et les dossiers/conversations indentés d'un cran pour mieux les distinguer",
                "Section HORS PROJET : seules les conversations avec un vrai dialogue sont listées (les sessions techniques vides des sous-agents sont ignorées)",
                "Les conversations sans titre affichent leur identifiant suivi de la première ligne d'un artéfact (task.md / walkthrough.md) quand elle existe",
            ],
        },
        "v1.9": {
            "🎨 Identité Visuelle & Ergonomie (ui)": [
                "Interlignage resserré dans la barre latérale (arborescence plus dense)",
                "Vue discussion compactée : moins d'espace sous « Utilisateur » / « Antigravity », entre les messages et entre les paragraphes",
                "Le curseur est remis en haut du document sans sélection à l'ouverture d'une discussion (plus de bloc pré-sélectionné au chargement)",
            ],
        },
        "v1.8": {
            "🐛 Corrections (fix)": [
                "Barre de recherche locale : le surlignage des occurrences était décalé par rapport au texte réel (positions de la chaîne plate ≠ positions du document Qt)",
                "Regex : le point « . » ne franchit plus une fin de ligne — un motif comme « c.*?\\.py » ne déborde plus sur les lignes suivantes",
                "L'occurrence courante n'est plus recouverte par le fond bleu de sélection : elle apparaît en orange, les autres en jaune",
            ],
        },
        "v1.7": {
            "✨ Nouvelles fonctionnalités (feat)": [
                "La taille et la position de la fenêtre, la répartition du panneau latéral et le dernier filtre projet sont mémorisés d'une session à l'autre",
            ],
            "🛡️ Robustesse & Sécurité des données (fix)": [
                "Sauvegarde horodatée automatique de agyhub_summaries_proto.pb avant toute réécriture lors d'un déplacement de conversation (5 copies conservées par rotation)",
                "Journal de diagnostic optionnel : définir la variable d'environnement ANTIGRAVITY_MANAGER_DEBUG=1 écrit data_loader.log (lectures/écritures échouées auparavant silencieuses)",
            ],
            "🔧 Qualité & Outillage (chore)": [
                "Couverture de tests portée à 71 tests (sauvegarde protobuf + rotation, logger, persistance de l'état d'interface)",
            ],
        },
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




def get_codex_root() -> Path:
    """Dossier Codex configurable, CODEX_HOME respecté par défaut."""
    raw = load_config().get("codex_root") or DEFAULT_CODEX_ROOT
    return Path(os.path.expandvars(raw)).expanduser()
