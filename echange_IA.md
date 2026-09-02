# Échange IA & Spécifications — Antigravity_ProjectManagment

## Statut Courant
- Application autonome de gestion et d'exploration des projets/conversations créés sous Google Antigravity.
- Clone visuel fidèle du panneau latéral et de la vue chat d'Antigravity.
- Support du paramétrage dynamique des dossiers sources via l'icône ⚙️.

## Environnement & Dépendances
- Environnement virtuel local : `.venv` (Python 3.10)
- Fichier de dépendances : `requirements.txt` (`PyQt6>=6.6.0`, `pyinstaller>=6.0.0`)
- Installation : `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

## Compilation & Distribution
- Script de compilation : `build.bat` ou `.\Build-App.ps1`
- Exécutable produit : `dist/AntigravityManager.exe` (~32 Mo, autonome sans console, moteur natif Qt6)

## Déploiement & Run
- Lancement direct : `run.bat` (utilise automatiquement `.venv` s'il existe)
- Lancement binaire : `dist/AntigravityManager.exe`

## Versioning & Git
- Dépôt GitHub : `cracky06/Antigravity_ProjectManagment`
- Branche principale : `main`
- Standard de versioning : `MAJOR.MINOR` (ex: `1.0`, `1.1`, `2.0`)
- Automatisation des tags : `.\scripts\release.ps1 [minor|major]`

## Spécificités Techniques
- `config.py` : gère la persistance des chemins dans `config.json` (auto-détection dynamique `antigravity-ide` et racine projet, compatible `sys.frozen`).
- `data_loader.py` :
  - Découverte multi-dossiers résiliente d'`agyhub_summaries_proto.pb`.
  - Priorisation du format compact `transcript.jsonl` et pré-filtrage des lignes `USER_INPUT`/`PLANNER_RESPONSE` pour une lecture ultra-rapide.
  - Cache en mémoire `_CHAT_CACHE` invalidé par mtime pour affichage instantané des sessions répétées.
  - Extraction du workspace depuis les transcripts si absent du proto (`Active Document:` / URIs).
  - Filtrage des stubs de sous-agents orphelins et fallback sur les artéfacts markdown (`walkthrough.md`, `task.md`, `implementation_plan.md`).
- `antigravity_manager.py` : interface graphique moderne **PyQt6** :
  - Arborescence native `QTreeWidget` (dépliage/repliage natif C++ à 60 FPS, zéro freeze, zéro clignotement).
  - Visionneuse de chat riche `QTextBrowser` avec rendu HTML/CSS pour les bulles de messages et extraits de code.
  - Redimensionnement fluide via `QSplitter`.
  - Menus contextuels complets (suppression en cascade, copie ID, ouverture dossier brain/projet).
- `Build-App.ps1` / `build.bat` : automatise le nettoyage, la fermeture des processus actifs, la détection du `.venv` et le packaging PyInstaller.
- `scripts/release.ps1` : calcul dynamique de la version et création du tag Git annoté.
