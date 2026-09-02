# 🤖 AGENT.MD — Antigravity Project & Chat Manager

Ce document définit les directives d'architecture, les spécifications techniques et les protocoles de développement pour tout agent intervenant sur **Antigravity_ProjectManagment**.

---

## 📌 1. Vue d'Ensemble du Projet

* **Objectif** : Application de bureau autonome reproduisant le panneau latéral et la visionneuse de conversations de Google Antigravity, avec des fonctions avancées d'organisation, d'exploration et de suppression en cascade.
* **Stack Technique** :
  * Langage : Python 3.10+
  * Interface : CustomTkinter (Thème moderne, support Light/Dark)
  * Packaging : PyInstaller (`--onefile`, `--windowed`, `--collect-all customtkinter`)
  * Environnement : `.venv` local dédié

---

## 📁 2. Cartographie du Projet

```
Antigravity_ProjectManagment/
├── antigravity_manager.py   # Interface GUI principale (CustomTkinter, panneau dépliable, viewer de chat)
├── data_loader.py           # Moteur de données (parsing protobuf wire-format, extraction transcripts & artefacts)
├── config.py                # Persistance de configuration (config.json, gestion sys.frozen)
├── run.bat                  # Lanceur direct sous Windows (auto-détection .venv)
├── build.bat                # Raccourci Windows pour déclencher la compilation
├── Build-App.ps1            # Script de build PowerShell (nettoyage, checks, PyInstaller)
├── scripts/
│   └── release.ps1          # Automatisation du versioning MAJOR.MINOR et tags Git
├── requirements.txt         # Dépendances Python (customtkinter, pyinstaller)
├── .gitignore               # Exclusions Git (.venv, build, dist, *.spec, config.json)
├── README.md                # Documentation utilisateur
├── echange_IA.md            # Spécifications & historique des choix techniques
└── AGENT.md                 # Règles & directives d'ingénierie pour les agents IA
```

---

## ⚙️ 3. Spécificités Techniques & Gotchas

### 🧬 Décodage Protobuf Wire-Format (`data_loader.py`)
* Le fichier `%USERPROFILE%\.gemini\antigravity-ide\agyhub_summaries_proto.pb` contient les métadonnées officielles de toutes les conversations.
* **Extraction des chemins (`file:///`)** :
  * Ne jamais faire de split naïf sur `\x00` ou `file:///`.
  * Toujours utiliser `_clean_path_string()` pour tronquer au premier caractère de contrôle ou délimiteur binaire (ex: `\x12`, `\x1a`, `"`, `|`, etc.).
  * Privilégier les sous-champs structurés `sub[9]` et `sub[17]`.

### 📂 Résolution Multi-Dossiers Antigravity
* Antigravity 2.0 / IDE actif stocke ses données dans `%USERPROFILE%\.gemini\antigravity-ide`.
* Les versions antérieures utilisaient `%USERPROFILE%\.gemini\antigravity`.
* `_find_brain_path()` et `_find_transcript_file()` doivent toujours vérifier le dossier configuré puis inspecter les dossiers frères pour ne perdre aucune conversation ni aucun journal.

### 📝 Fallback sur Artefacts
* Lorsque `transcript.jsonl` ou `transcript_full.jsonl` est absent (sessions techniques, sous-agents, logs nettoyés), `load_chat_messages()` lit et formate les artefacts disponibles (`walkthrough.md`, `task.md`, `implementation_plan.md`).

### 📦 Mode Compilé PyInstaller (`config.py`)
* Lorsque l'application est exécutée sous forme de binaire (`sys.frozen == True`), `config.json` doit être localisé dans le même répertoire que `sys.executable` (et non dans le dossier temporaire `_MEIxxxx`).

---

## 🛠️ 4. Commandes & Workflows de Développement

### 🚀 Exécution locale
```powershell
# Via batch
.\run.bat

# Via Python (.venv)
.\.venv\Scripts\python.exe antigravity_manager.py
```

### 📦 Compilation & Packaging (.exe)
```powershell
# Compilation complète de l'exécutable autonome (dist/AntigravityManager.exe)
.\Build-App.ps1

# Nettoyage seul
.\Build-App.ps1 -CleanOnly
```

### 🏷️ Release & Versioning
```powershell
# Incrément mineur (ex: 1.0 -> 1.1)
.\scripts\release.ps1 minor

# Incrément majeur (ex: 1.1 -> 2.0)
.\scripts\release.ps1 major -Message "Refonte de l'interface"

# Release avec push automatique vers GitHub
.\scripts\release.ps1 minor -Push
```

---

## 📜 5. Règles Constitutionnelles & Bonnes Pratiques

1. **Zéro Destruction** : Ne jamais supprimer de code existant sans instruction explicite. Commenter plutôt que détruire si nécessaire.
2. **Isolation Python** : Toutes les dépendances doivent être installées dans `.venv`. Maintenir `requirements.txt` à jour.
3. **Conventions PowerShell** :
   * Toujours inclure `[CmdletBinding()]`.
   * Respecter le formalisme `Verb-Noun` (ex: `Build-App.ps1`, `New-Release`).
   * Proscrire les alias dans les scripts (`dir` ➔ `Get-ChildItem`, etc.).
4. **Typage Python** : Utiliser les *Type Hints* Python 3.10+ (`def func(param: str | None) -> Path:`) et `pathlib.Path`.
