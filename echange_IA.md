# Échange IA & Spécifications — Antigravity_ProjectManagment

## Statut Courant
- Application autonome de gestion et d'exploration des projets/conversations créés sous Google Antigravity.
- Clone visuel fidèle du panneau latéral et de la vue chat d'Antigravity.
- Support du paramétrage dynamique des dossiers sources via l'icône ⚙️.

## Environnement & Dépendances
- Environnement virtuel local : `.venv` (Python 3.10)
- Fichier de dépendances : `requirements.txt` (`PyQt6>=6.6.0`, `pytest>=7.0.0`, `pyinstaller>=6.0.0`)
- Installation : `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

## Tests Unitaires & Assurance Qualité
- Framework : `pytest`
- Emplacement : `tests/` (`test_config.py`, `test_data_loader.py`, `test_ui_sanity.py`)
- Exécution manuelle : `.\.venv\Scripts\pytest.exe -v`
- Intégration Build : Exécution systématique à l'étape `[3/4]` de `Build-App.ps1` (annulation immédiate du build en cas d'échec).

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
- `VERSION` : fichier unique définissant la version officielle (`1.1`).
- `config.py` : gère la persistance des chemins, du thème, de la version et du changelog structuré dans `config.json`.
- `data_loader.py` :
  - Découverte multi-dossiers résiliente d'`agyhub_summaries_proto.pb`.
  - Fonction `move_conversation(conv_id, target_project)` : réassignation officielle avec ré-encodage binaire protobuf wire-format pour compatibilité totale avec Google Antigravity IDE.
  - Priorisation du format compact `transcript.jsonl` et pré-filtrage des lignes `USER_INPUT`/`PLANNER_RESPONSE` pour une lecture ultra-rapide.
  - Cache en mémoire `_CHAT_CACHE` invalidé par mtime pour affichage instantané des sessions répétées.
  - Extraction du workspace sécurisée : dé-échappement des sauts de ligne, exclusion des chemins internes (.gemini, brain, Temp), détection des `SearchPath` / `Cwd` et élimination des faux projets (`n`, `nLast`).
  - Rendu riche de fallback pour les sessions de sous-agents : affichage automatique des artéfacts markdown, des médias/images générés et du résumé des opérations techniques.
- `antigravity_manager.py` : interface graphique moderne **PyQt6** (v1.2) :
  - Barre de titre avec numéro de version lu dynamiquement depuis `VERSION` via `get_app_version()` (jamais hard-codé).
  - **[v1.2] Champ de recherche globale** au-dessus du filtre projet dans la sidebar : filtre projets et conversations en cherchant dans le contenu de toutes les discussions du périmètre actif. Debounce 400ms, affichage du nombre de résultats dans la status bar.
  - **[v1.2] Respect du filtre projet dans la recherche** : si un projet est sélectionné dans le combo, la recherche ne porte que sur ses conversations.
  - **[v1.2] Barre de recherche locale (Find Bar)** sous le header du chat : pré-remplie automatiquement depuis la recherche globale, navigation ▲/▼ avec wrap-around, raccourci `Ctrl+F` pour ouvrir, `Échap` pour fermer.
  - **[v1.2] Bouton ← Retour** dans le header du chat : utilise l'historique natif `QTextBrowser.backward()`, visible seulement quand un historique existe.
  - **[v1.2] Fix word-wrap des liens** `file:///` : ajout de `word-break: break-all` dans le CSS HTML embarqué pour éviter les débordements horizontaux.
  - Intégration de l'icône officielle de l'application (`assets/icon.png` / `assets/icon.ico`) dans la barre latérale, la barre de titre et la barre des tâches Windows via `SetCurrentProcessExplicitAppUserModelID`.
  - Boîte déroulante de filtre par projet en haut de la barre latérale : *Tous les projets*, *Sans projet (orphelines)*, ou *Projet individuel*.
  - Dépliage intelligent : dossiers repliés par défaut en vue globale (« Tous les projets »), dépliés automatiquement en vue filtrée.
  - Navigation fluide au clavier (flèches haut/bas) avec actualisation instantanée de la discussion affichée.
  - Correction intégrale du contraste en thème clair (textes noirs/gris foncé lisibles).
  - Bascule double affichage : Vue Riche HTML ou Source Markdown brute (`<>`).
  - Fenêtre modeless de Changelog sous forme de TreeView compacte au premier lancement d'une mise à jour (et accessible dans Paramètres ⚙️).
  - Support complet des thèmes **Système (Par défaut)**, **Clair (Light)** et **Sombre (Dark)** avec bascule à chaud.
  - Arborescence native `QTreeWidget` (dépliage/repliage natif C++ à 60 FPS, zéro freeze, zéro clignotement).
  - Visionneuse de chat riche `QTextBrowser` avec rendu HTML/CSS adaptatif selon le thème sélectionné.
  - Menus contextuels complets (déplacement / réassignation vers un autre projet, suppression en cascade, copie ID, ouverture dossier brain/projet).
- `assets/` : icône officielle du gestionnaire (`icon.png` 1024x1024 transparent, `icon.ico` multi-résolution).
- `Build-App.ps1` / `build.bat` : automatise le nettoyage, la fermeture des processus actifs, la vérification du `.venv`, l'exécution des tests unitaires (16 tests) et le packaging PyInstaller avec l'icône intégrée (`--icon assets/icon.ico`) et le fichier `VERSION`.
- `scripts/release.ps1` : calcul dynamique de la version et création du tag Git annoté.
