# Échange IA & Spécifications — Antigravity_ProjectManagment

## Statut Courant
- Application autonome de gestion et d'exploration des projets/conversations créés sous Google Antigravity.
- Clone visuel fidèle du panneau latéral et de la vue chat d'Antigravity.
- Support du paramétrage dynamique des dossiers sources via l'icône ⚙️.

## Compilation & Build
- Prérequis : Python 3.10+, `customtkinter`
- Installation dépendance : `pip install customtkinter`

## Déploiement & Run
- Lancement direct : `run.bat` ou `python antigravity_manager.py`

## Versioning & Git
- Dépôt GitHub : `cracky06/Antigravity_ProjectManagment`
- Branche principale : `main`

## Spécificités Techniques
- `config.py` : gère la persistance des chemins dans `config.json`.
- `data_loader.py` : décode le wire-format protobuf de `%USERPROFILE%\\.gemini\\antigravity\\agyhub_summaries_proto.pb` pour obtenir les vrais titres officiels et lier chaque conversation à son workspace.
- `antigravity_manager.py` : interface graphique CustomTkinter avec arborescence dépliable, suppression en cascade (projet + conversations), et visionneuse de chat.
