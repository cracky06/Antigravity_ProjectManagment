# Antigravity Manager (Project & Chat Management)

Application graphique indépendante permettant d'organiser, explorer et gérer les projets et conversations créés dans **Google Antigravity**.

Reproduit l'interface latérale et la visionneuse de conversation d'Antigravity avec des fonctionnalités de gestion avancées.

---

## 🌟 Fonctionnalités

- **Arborescence Projets & Conversations** :
  - Affichage identique au panneau latéral d'Antigravity (icônes 📁/📂, indentation).
  - Vrais titres officiels des conversations extraits des métadonnées internes.
  - Timestamps relatifs (*3h, 9d, 15d…*).
  - Pas d'espace vide superflu si un dossier projet ne contient aucune conversation.
- **Visionneuse de Chat intégrée** :
  - Cliquez sur n'importe quelle conversation pour afficher instantanément tout l'historique des échanges.
  - Bulles utilisateur distinctes avec date et heure.
  - Réponses de l'IA mises en page proprement.
- **Gestion des Projets & Conversations (Clic droit)** :
  - Renommer un projet (avec mise à jour automatique des liaisons).
  - **Suppression en cascade** : supprimer un projet supprime proprement le dossier sur disque **et l'ensemble de ses conversations associées** (stockage *brain* et bases de données *.db*).
  - Déplacer une conversation vers un autre projet.
  - Copier l'ID de la conversation.
- **Configuration dynamique des chemins (⚙️ Paramètres)** :
  - Définissez l'emplacement racine de vos projets (ex: `D:\DEV`).
  - Définissez le répertoire des données Antigravity (`%USERPROFILE%\.gemini\antigravity`).

---

## 🚀 Installation & Lancement

### Prérequis

- Python 3.10 ou supérieur
- CustomTkinter

### Installation des dépendances

```bash
pip install -r requirements.txt
```

### Lancement direct

Double-cliquez sur `run.bat` ou lancez en ligne de commande :

```bash
python antigravity_manager.py
```

### 📦 Compilation & Distribution (.exe)

Pour générer un exécutable Windows autonome dans `dist/AntigravityManager.exe` :

- **Via Batch** : Double-cliquez sur `build.bat`
- **Via PowerShell** :

  ```powershell
  .\Build-App.ps1
  ```

---

## 📁 Structure du projet

```
Antigravity_ProjectManagment/
├── antigravity_manager.py   # Interface graphique principale (CustomTkinter)
├── data_loader.py           # Décodeur protobuf & extraction des transcripts
├── config.py                # Gestion de la configuration persistante (config.json)
├── run.bat                  # Script de démarrage rapide Windows
├── build.bat                # Raccourci Windows pour compiler l'exécutable
├── Build-App.ps1            # Script PowerShell de build PyInstaller
├── scripts/
│   └── release.ps1          # Script de versioning et release Git automatique
├── requirements.txt         # Dépendances Python (customtkinter, pyinstaller)
├── .gitignore               # Fichiers ignorés par Git
└── README.md                # Documentation
```

---

## 🏷️ Versioning et Release

Le versioning suit le standard `MAJOR.MINOR` (ex: `1.67`) avec tags Git automatiques `V1.67` :

```powershell
# Release d'une version mineure (ex: 1.66 -> 1.67)
.\scripts\release.ps1 minor

# Release d'une version majeure (ex: 1.67 -> 2.0)
.\scripts\release.ps1 major
```

## 📄 Licence

MIT
