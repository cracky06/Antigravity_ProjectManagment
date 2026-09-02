# Échange IA & Spécifications — Antigravity_ProjectManagment

## Statut Courant
- Application autonome de gestion et d'exploration des projets/conversations créés sous Google Antigravity.
- Clone visuel fidèle du panneau latéral et de la vue chat d'Antigravity.
- Support du paramétrage dynamique des dossiers sources via l'icône ⚙️.

## Environnement & Dépendances
- Environnement virtuel local : `.venv` (Python 3.10)
- Fichier de dépendances : `requirements.txt` (`customtkinter>=5.2.0`, `pyinstaller>=6.0.0`)
- Installation : `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

## Compilation & Distribution
- Script de compilation : `build.bat` ou `.\Build-App.ps1`
- Exécutable produit : `dist/AntigravityManager.exe` (~8.7 Mo, autonome sans console)

## Déploiement & Run
- Lancement direct : `run.bat` (utilise automatiquement `.venv` s'il existe)
- Lancement binaire : `dist/AntigravityManager.exe`

## Versioning & Git
- Dépôt GitHub : `cracky06/Antigravity_ProjectManagment`
- Branche principale : `main`
- Standard de versioning : `MAJOR.MINOR` (ex: `1.0`, `1.1`, `2.0`)
- Automatisation des tags : `.\scripts\release.ps1 [minor|major]`

## Spécificités Techniques
- `config.py` : gère la persistance des chemins dans `config.json` (compatible `sys.frozen` pour l'exécutable).
- `data_loader.py` : décode le wire-format protobuf de `%USERPROFILE%\.gemini\antigravity\agyhub_summaries_proto.pb` pour obtenir les vrais titres officiels et lier chaque conversation à son workspace.
- `antigravity_manager.py` : interface graphique CustomTkinter avec arborescence dépliable, suppression en cascade (projet + conversations), et visionneuse de chat.
- `Build-App.ps1` / `build.bat` : automatise le nettoyage, la détection du `.venv` et le packaging PyInstaller.
- `scripts/release.ps1` : calcul dynamique de la version et création du tag Git annoté.
