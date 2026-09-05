# Antigravity Manager — Liste des fonctionnalités

Le numéro entre parenthèses indique la version où la fonctionnalité a été introduite.

---

## Barre latérale (arborescence)

- Affichage des **projets et conversations** avec vrais titres officiels extraits des métadonnées internes *(v1.0)*
- **Timestamps relatifs** sur chaque conversation (3h, 9d, 15d…) *(v1.0)*
- **Icône de projet associé** en badge sur les conversations récentes *(v1.0)*
- **Filtre par projet** : Tous les projets / Sans projet / projet individuel *(v1.0)*
- **Dépliage intelligent** des dossiers : repliés en vue globale, dépliés en vue filtrée *(v1.0)*
- **Navigation clavier** (flèches haut/bas) dans l'arborescence *(v1.0)*
- Pas d'espace vide pour un dossier projet sans conversation *(v1.0)*
- Élimination des faux projets `n` / `nLast` (assainissement des logs) *(v1.0)*
- **Réorganisation en 3 sections** : PROJETS, CONVERSATIONS HORS PROJET, CONVERSATIONS RÉCENTES (repliée par défaut) *(v2.0)*
- Titres de section alignés à gauche, dossiers/conversations indentés d'un cran *(v2.0)*
- Section HORS PROJET : n'affiche que les conversations avec un vrai dialogue (sessions techniques des sous-agents ignorées) *(v2.0)*
- Conversations sans titre : affichage `<id> — <1re ligne d'un artéfact>` (task.md / walkthrough.md) *(v2.0)*
- **Interlignage resserré** (arborescence plus dense) *(v1.9)*
- **Compteur de conversations** sur les titres de section « PROJETS » et « CONVERSATIONS RÉCENTES » *(v2.5)*
- **Sélecteur de source** : bascule entre Antigravity et Claude Code / Claude Desktop — parcourt les conversations stockées localement par Claude Code (VS Code) et l'app Claude Desktop *(v2.5)*
- La source Claude Code offre la **même expérience** : arbre en 3 sections (PROJETS / HORS PROJET / RÉCENTES), filtre par projet, badge d'origine (VS Code / Desktop) et date, recherche globale, find bar locale, export Markdown/PDF *(v2.5)*
- Une session Claude Code démarrée sur une autre machine ou interface (sans dossier local) mais avec un vrai échange apparaît en « CONVERSATIONS HORS PROJET » plutôt que d'être perdue *(v2.5)*

---

## Vue discussion

- **Rendu HTML/CSS riche** des messages avec bulles utilisateur et cartes de réponses IA *(v1.0)*
- Bascule **Vue Riche HTML ↔ Source Markdown brute** (bouton `<>`) *(v1.0 / v1.1)*
- **Parseur Markdown officiel** : titres, gras, listes, code, tableaux, citations, retours à la ligne *(v1.1)*
- Typographie soignée, bordures et contrastes adaptés aux thèmes clair/sombre *(v1.1)*
- Fix contraste du texte en thème clair (gris foncé lisible au lieu de blanc) *(v1.0)*
- **Word-wrap** des liens `file:///` et des blocs de code longs (plus de débordement horizontal) *(v1.2 / v1.3)*
- Gestion des **sessions de sous-agents** : affichage des artéfacts et résumé des actions *(v1.0)*
- **Vue compactée** : moins d'espace sous « Utilisateur »/« Antigravity », entre messages et paragraphes *(v1.9)*
- Curseur remis en haut sans sélection à l'ouverture d'une discussion *(v1.9)*

### Liens dans la discussion

- Clic sur un lien fichier → **affiche son contenu dans la vue** (jamais d'exécution), avec **coloration syntaxique Pygments** *(v1.3)*
- Fin des exécutions accidentelles (un clic sur `build.bat` ne lance plus le build) *(v1.3)*
- **Bouton ← Retour** : revient à la conversation précédente, ou depuis un aperçu fichier à la conversation d'origine *(v1.3)*
- **Menu contextuel (clic droit)** sur un lien fichier : copier le lien, ouvrir le dossier parent, révéler dans l'Explorateur *(v2.2)*

---

## Recherche

### Recherche globale (toutes les discussions)

- **Recherche dans le contenu** de toutes les conversations, barre au-dessus du filtre projet *(v1.2)*
- Filtrage des résultats selon le **projet sélectionné** *(v1.2)*
- **Index plein-texte SQLite FTS5** : recherche instantanée (plus de parsing à chaque frappe) *(v1.5)*
- **3 modes** via les boutons `[.*]` et `[Ab]` : « contient » (défaut), « mots » (FTS, tolérant aux accents/préfixes), « regex » *(v1.5)*
- Bordure rouge si le motif regex est invalide *(v1.5)*
- Recherche **exécutée en tâche de fond** : l'interface ne se fige plus *(v1.5)*
- **Reconstruction automatique** de l'index s'il est corrompu, avec repli sur la recherche à la volée *(v1.5)*
- Bouton **« Réindexer »** dans les Paramètres + affichage de l'état de l'index (prêt / absent / corrompu) *(v1.5)*
- **Indexation au fil de l'eau** : l'index se met à jour dès qu'une conversation est consultée *(v2.2)*
- La recherche globale fonctionne aussi sur la source **Claude Code / Desktop** (index dédié, mêmes 3 modes) *(v2.5)*

### Barre de recherche locale (dans une discussion)

- **Find Bar** dans la vue discussion, navigation ▲/▼ avec wrap-around *(v1.2)*
- Ouverture/fermeture via le bouton 🔍 du header *(v1.2)*
- **Pré-remplissage automatique** depuis la recherche globale *(v1.2)*
- **Compteur d'occurrences** « n / total » + surlignage de toutes les occurrences *(v1.5)*
- Navigation `F3` / `Maj+F3` avec wrap-around *(v1.5)*
- Boutons **`[.*]` (regex)** et **`[Aa]` (respect de la casse)**, indépendants de la recherche globale *(v1.6)*
- Surlignage correct des correspondances de longueur variable en mode regex *(v1.6)*
- Le point `.` d'une regex ne franchit plus une fin de ligne *(v1.8)*
- Occurrence courante en **orange**, les autres en **jaune** (plus recouverte par le fond de sélection) *(v1.8)*
- Motif regex invalide → bordure rouge + 0 résultat *(v1.6)*
- Fonctionne aussi dans les conversations de la source **Claude Code / Desktop** *(v2.5)*

---

## Gestion des conversations

- **Déplacement officiel** d'une conversation vers un projet (réécriture binaire `agyhub_summaries_proto.pb` pour synchro directe avec Antigravity IDE) *(v1.0)*
- **Suppression en cascade** d'un projet (dossier + dossiers `brain/` + bases SQLite) *(v1.0)*
- Menu contextuel : copier l'ID de session, ouvrir le dossier des journaux, déplacer vers un projet, supprimer *(v1.0)*
- **Sauvegarde horodatée automatique** de `agyhub_summaries_proto.pb` avant chaque réécriture (rotation de 5 copies) *(v1.7)*

### Export Markdown

- **Export d'une conversation en Markdown** (clic droit) : dans le projet (`<projet>/_conversations/…`) ou vers un emplacement au choix *(v2.0)*
- L'export inclut l'en-tête (titre, projet, date, ID) et tous les messages *(v2.0)*
- **Annexe des artéfacts** de session (walkthrough.md, implementation_plan.md, task.md) s'ils existent *(v2.0)*
- **Images copiées** à côté du `.md` (dans `<nom>_images/`), liens relatifs → document autonome *(v2.0)*
- Images générées **placées dans l'échange** auquel elles correspondent (corrélation via les événements de génération du journal) *(v2.1)*
- Images téléversées / temporaires regroupées dans une section « Images » de fin *(v2.1)*
- **Liens fichiers portables** : chemin relatif au projet s'ils sont dedans, sinon simple code (le document reste valide même déplacé) *(v2.2)*
- **Export de tout un projet** (clic droit sur le dossier projet) : exporte toutes ses conversations en Markdown dans `<projet>/_conversations/` *(v2.4)*
- **Export d'un projet entier en PDF** (clic droit sur le dossier projet) : un seul PDF avec page de garde, table des matières, une section par conversation (en-tête/pied de page) et une annexe pour les images non corrélées à un échange *(v2.4)*
- La page de garde du PDF illustre automatiquement le projet si un visuel évident est trouvé dans ses dossiers `assets` (background, splash, logo, nom du projet, ou une icône .ico à défaut) *(v2.4)*
- **Archiver (ZIP) et supprimer un projet** : crée un ZIP de toutes les conversations (Markdown + images) puis supprime le projet en cascade — l'historique est conservé après suppression *(v2.4)*
- Garde-fou : l'archive ZIP ne peut pas être placée dans le dossier qui va être supprimé *(v2.4)*
- **Source Claude Code / Desktop** : export Markdown (une conversation ou tout un projet) et export PDF du projet, écrits dans le dossier `_conversations/` du vrai dossier de code du projet. Pas de suppression ni de déplacement (fichiers gérés par Claude Code) *(v2.5)*

---

## Interface & paramètres

- **Thèmes Système / Sombre / Clair** avec bascule à chaud *(v1.0)*
- **Fenêtre de paramètres** ⚙️ : dossiers sources, thème *(v1.0)*
- Détection dynamique des dossiers par défaut (`E:\Dev`, `D:\DEV`… ; `.gemini/antigravity-ide` puis `.gemini/antigravity`) *(v1.0)*
- **Fenêtre de changelog** modeless automatique lors d'une nouvelle version *(v1.0)*
- **Fenêtre « À propos »** (bouton dans les Paramètres) : illustration, version, lien GitHub *(v2.3)*
- **Icône officielle** de l'application (barre latérale, barre de titre, barre des tâches Windows via AppUserModelID) *(v1.0)*
- **Persistance de l'état d'interface** : taille/position de la fenêtre, répartition du panneau latéral, dernier filtre projet mémorisés entre sessions *(v1.7)*

### Raccourcis clavier

- `Ctrl+F` : ouvrir la barre de recherche locale *(v1.2)*
- `Ctrl+K` / `Ctrl+L` : focus sur la recherche globale *(v1.4)*
- `F3` / `Maj+F3` : occurrence suivante / précédente *(v1.4)*
- `Échap` : ferme la barre de recherche locale, ou efface la recherche globale *(v1.4)*
- Flèches ↑/↓ : navigation dans l'arborescence *(v1.0)*

---

## Robustesse & diagnostic

- Lecture résiliente en cas de fichier log ou metadata absent/corrompu *(v1.0)*
- Découverte multi-dossiers `.gemini` (antigravity-ide / antigravity / antigravity-backup) *(v1.0)*
- Fix lecture du fichier `VERSION` en mode `--onefile` PyInstaller *(v1.2)*
- **Journal de diagnostic optionnel** : `ANTIGRAVITY_MANAGER_DEBUG=1` → écrit `data_loader.log` *(v1.7)*
- **`crash.log`** : capture globale des exceptions non gérées, y compris dans les gestionnaires d'événements Qt (clics, minuteries) *(v2.2)*
- `crash.log` en mode ajout (les incidents successifs ne s'écrasent plus) *(v2.2)*
- Migration complète vers **PyQt6** (zéro scintillement, dépliage natif C++) *(v1.0)*

---

## Distribution

- Numéro de version géré via le fichier `VERSION` (source unique), affiché dans la barre de titre *(v1.0)*
- **Exécutable autonome** `dist/AntigravityManager.exe` (PyInstaller `--onefile --windowed`), sans console *(v1.0)*
- Script de build `Build-App.ps1` : nettoyage, tests unitaires, packaging *(v1.0)*
- Suppression de `build/` et `dist/` **avec réessais** (contourne les verrous transitoires de l'Explorateur / de l'IDE) *(v1.4)*
- Script `scripts/release.ps1` : calcul de version, tag Git annoté, push *(v1.0)*
- `.gitattributes` : fins de ligne normalisées *(v1.4)*
- Suite de **tests unitaires** exécutée à chaque build (114 tests en v2.3) *(v1.0, étendue en continu)*
