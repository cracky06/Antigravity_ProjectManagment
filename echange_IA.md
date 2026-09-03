# Échange IA & Spécifications — Antigravity_ProjectManagment

## Statut Courant
- Application autonome de gestion et d'exploration des projets/conversations créés sous Google Antigravity.
- Clone visuel fidèle du panneau latéral et de la vue chat d'Antigravity.
- Support du paramétrage dynamique des dossiers sources via l'icône ⚙️.

## Environnement & Dépendances
- Environnement virtuel local : `.venv` (Python 3.10)
- Fichier de dépendances : `requirements.txt` (`PyQt6>=6.6.0`, `pytest>=7.0.0`, `pyinstaller>=6.0.0`, `markdown>=3.6.0`, `pygments>=2.17.0`)
- Installation : `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`

## Tests Unitaires & Assurance Qualité
- Framework : `pytest`
- Emplacement : `tests/` (`test_config.py`, `test_data_loader.py`, `test_ui_sanity.py`, `test_file_preview_nav.py`, `test_search_index.py`, `test_search_ui.py`) — 71 tests
- `tests/conftest.py` : fixture `isolated_search_index` (autouse) redirigeant l'index vers un fichier jetable et drainant `QThreadPool` avant/après chaque test
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
- `VERSION` : fichier unique définissant la version officielle (`1.7`).
- `config.py` : gère la persistance des chemins, du thème, de la version et du changelog structuré dans `config.json`. **[v1.7]** `get_ui_state()` / `save_ui_state()` : clé `ui_state` de `config.json` (`geometry` en base64, `splitter` `[int,int]`, `project_filter`), fusion partielle à l'écriture.
- **[v1.5]** `search_index.py` : index de recherche plein-texte **SQLite FTS5**, stocké dans `search_index.db` à côté de `config.json` (gitignoré, reconstructible).
  - Schéma : table `docs(conv_id, mtime, project, title, body)` + table virtuelle `docs_fts` (`tokenize='unicode61 remove_diacritics 2'`) synchronisée par triggers.
  - `sync_index(convs)` : incrémental — ne réindexe que les conversations absentes ou dont le `mtime` du transcript a changé, supprime les orphelines. `rebuild_index()` : reconstruction complète.
  - `search(query, mode)` avec `mode ∈ {substring, words, regex}` : `LIKE` échappé / FTS5 `MATCH` (préfixes `terme*`, ET logique) / `re.search` sur le corps stocké. `check_status()` renvoie ok / absent / corrompu ; `drop_index()` supprime le fichier + WAL/SHM.
  - Connexion sqlite par thread (`threading.local`), fermée en fin de tâche worker.
- `data_loader.py` :
  - **[v1.7]** `_backup_pb_file(pb_path)` : copie horodatée à la ms (`.bak-YYYYmmdd-HHMMSS-fff`) avant toute réécriture de `agyhub_summaries_proto.pb` dans `move_conversation`, rotation sur `_PB_BACKUP_KEEP` (5).
  - **[v1.7]** Logger `antigravity_manager.data_loader` : `NullHandler` par défaut ; `ANTIGRAVITY_MANAGER_DEBUG=1` (ou `true`/`debug`/…) → `FileHandler` vers `data_loader.log` à côté de `config.json`. Les `except` critiques (lecture transcript, réécriture protobuf, MAJ echange_IA.md) loggent au lieu de `pass`.
  - Découverte multi-dossiers résiliente d'`agyhub_summaries_proto.pb`.
  - Fonction `move_conversation(conv_id, target_project)` : réassignation officielle avec ré-encodage binaire protobuf wire-format pour compatibilité totale avec Google Antigravity IDE.
  - Priorisation du format compact `transcript.jsonl` et pré-filtrage des lignes `USER_INPUT`/`PLANNER_RESPONSE` pour une lecture ultra-rapide.
  - Cache en mémoire `_CHAT_CACHE` invalidé par mtime pour affichage instantané des sessions répétées.
  - Extraction du workspace sécurisée : dé-échappement des sauts de ligne, exclusion des chemins internes (.gemini, brain, Temp), détection des `SearchPath` / `Cwd` et élimination des faux projets (`n`, `nLast`).
  - Rendu riche de fallback pour les sessions de sous-agents : affichage automatique des artéfacts markdown, des médias/images générés et du résumé des opérations techniques.
- `antigravity_manager.py` : interface graphique moderne **PyQt6** (v1.7) :
  - Barre de titre avec numéro de version lu dynamiquement depuis `VERSION` via `get_app_version()` (jamais hard-codé).
  - **[v1.7] Persistance de l'état d'interface** : `__init__` restaure `restoreGeometry(base64)` (fallback `resize(1260, 840)`), les tailles du `splitter` (si `[int>0, int>0]`) et le dernier `project_filter` (au 1er `reload_data`, quand aucune sélection courante). `closeEvent` → `_persist_ui_state()` écrit `saveGeometry()` + `splitter.sizes()` + filtre courant dans `ui_state` avant de drainer le pool.
  - **[v1.5] Recherche globale asynchrone & multi-modes** : `_SearchRunnable` (QRunnable) exécute `search_index.search()` sur `QThreadPool.globalInstance()` et émet `finished(generation, set[conv_id])` ; un compteur `_search_generation` fait ignorer les résultats périmés. Boutons `[.*]` (regex) et `[Ab]` (mots) mutuellement exclusifs dans le champ (`searchModeBtn`, `_current_search_mode()`). Motif regex invalide → propriété `queryError=true` (bordure rouge) + message. `_IndexSyncRunnable` synchronise l'index en tâche de fond au démarrage et après chaque `reload_data()` ; repli `_fallback_search` (parsing à la volée) tant que l'index n'est pas prêt. `closeEvent` draine le pool (`waitForDone`) et invalide les recherches en vol. Bouton « Réindexer » dans `SettingsDialog` → `rebuild_search_index()`.
  - **[v1.6] Find bar — modes regex & casse** : toggles autonomes `[.*]` (`btn_find_regex`) et `[Aa]` (`btn_find_case`) dans la find bar. `_iter_find_matches(text)` génère les `(start, length)` — `re.finditer` (avec `re.IGNORECASE`/`re.MULTILINE` selon toggles, correspondances vides ignorées) ou `str.find` en boucle. `_find_positions` stocke désormais des tuples `(start, length)` (longueur variable en regex). Motif invalide → `queryError` sur `find_input` (bordure rouge) + 0 résultat. `_prefill_find_from_search` aligne `btn_find_regex` sur `btn_mode_regex` global.
  - **[v1.5] Find bar — compteur & surlignage** : `_recompute_find_matches()` recense toutes les occurrences, les surligne toutes via `setExtraSelections`, `_goto_find_match(i)` navigue avec wrap et met à jour le label `n / total` (`_update_find_label`). `F3`/`Maj+F3` = suivant/précédent.
  - **[v1.4] Raccourcis clavier** : liste `_shortcuts` d'objets `QShortcut` conservés en attribut d'instance (anti-GC). `Ctrl+F` (find bar), `Ctrl+K`/`Ctrl+L` (`_focus_global_search`), `F3`/`Shift+F3` (`_find_next`/`_find_prev`), `Escape` (`_on_escape` : ferme la find bar via `isVisibleTo(self)` — plus fiable que `isVisible()` — sinon efface la recherche globale). Échap DANS le champ de la find bar reste géré par `_FindLineEdit`.
  - **[v1.3] Aperçu du contenu des fichiers référencés** : `chat_browser` avec `setOpenLinks(False)` + `setOpenExternalLinks(False)`, tous les clics passent par `_on_anchor_clicked`. Un lien fichier local est LU et affiché dans la vue discussion via `_show_file_content` (jamais ouvert avec l'application associée → aucune exécution de `.py`/`.bat`/`.ps1`). Coloration syntaxique par **Pygments** (`_render_file_body`, style `monokai`/`default` selon thème, lexer déduit du nom de fichier, repli `<pre>` échappé). Garde-fous : refus au-delà de 512 Ko, détection binaire (octets NUL / extension non listée dans `_TEXT_FILE_SUFFIXES`), message discret en status bar si introuvable. Liens web/mailto → application système ; dossiers → Explorateur.
  - **[v1.3] Bouton ← Retour** dans le header du chat : pile d'historique maison `_nav_history` (liste de `ConversationInfo`) — l'historique natif `QTextBrowser` était pollué par les clics de liens `file:///` (navigation interne via `setSource`). Depuis un aperçu de fichier (`_file_view_active`), `_navigate_back` restaure la conversation d'origine (`_file_view_return_conv`) ; sinon il dépile `_nav_history`. La navigation clavier ↑↓ n'empile pas (`display_chat(record_history=False)`), seuls un clic dans l'arbre / un résultat de recherche / un lien empilent.
  - **[v1.3] Fix word-wrap dans la vue discussion** : `white-space: pre-wrap` + `word-wrap: break-word` sur `pre`, `pre code` et `code` inline (le moteur de `QTextBrowser` ne scrolle pas horizontalement un bloc → une commande `.bat`/`.ps1` longue débordait) ; `a` passe de `word-break: break-all` à `word-wrap: break-word`.
  - **[v1.2] Champ de recherche globale** au-dessus du filtre projet dans la sidebar : filtre projets et conversations en cherchant dans le contenu de toutes les discussions du périmètre actif. Debounce 400ms, affichage du nombre de résultats dans la status bar.
  - **[v1.2] Respect du filtre projet dans la recherche** : si un projet est sélectionné dans le combo, la recherche ne porte que sur ses conversations.
  - **[v1.2] Barre de recherche locale (Find Bar)** sous le header du chat : pré-remplie automatiquement depuis la recherche globale, navigation ▲/▼ avec wrap-around, raccourci `Ctrl+F` pour ouvrir, `Échap` pour fermer.
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
- `Build-App.ps1` / `build.bat` : automatise le nettoyage, la fermeture des processus actifs, la vérification du `.venv`, l'exécution des tests unitaires (71 tests) et le packaging PyInstaller avec l'icône intégrée (`--icon assets/icon.ico`), le fichier `VERSION` et `--collect-submodules pygments` (lexers/styles chargés dynamiquement, sinon la coloration de l'aperçu de fichier serait muette dans l'exe). **[v1.4]** La suppression de `build/` et `dist/` passe par `Remove-BuildDirectory` (6 réessais, délai 1 s) pour absorber les verrous transitoires posés par une fenêtre de l'Explorateur ou un watcher d'IDE.
- `.gitattributes` : **[v1.4]** normalisation des fins de ligne (`VERSION`, `*.py`, `*.md`, `*.txt` en LF ; `*.ps1`, `*.bat` en CRLF ; `*.ico`/`*.png`/`*.pb` binaires). Supprime les avertissements « LF will be replaced by CRLF » à chaque commit.
- `tests/` : `test_config.py`, `test_data_loader.py`, `test_ui_sanity.py`, **[v1.4]** `test_file_preview_nav.py` (aperçu fichier, garde-fous, `_navigate_back`, pile `_nav_history`, raccourcis, compteur find bar), **[v1.5]** `test_search_index.py` (index FTS, 3 modes, sync incrémentale) + `test_search_ui.py` (toggles, mode effectif, résultat périmé) + `conftest.py`, +6 tests find bar regex/casse (v1.6), +11 tests robustesse (v1.7). 71 tests au total.
- `scripts/release.ps1` : calcul dynamique de la version et création du tag Git annoté.
