"""antigravity_manager.py — Interface PyQt6 Haute Performance pour Antigravity Manager.

Fournit une exploration ultra-fluide (C++ 60 FPS), une arborescence native (QTreeWidget),
un rendu HTML/CSS riche pour le chat (QTextBrowser), et la gestion complète des projets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QSize, QUrl, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor, QDesktopServices, QAction, QKeySequence, QShortcut, QTextDocument
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QTextBrowser,
    QLabel,
    QPushButton,
    QDialog,
    QLineEdit,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QMenu,
    QFrame,
    QStatusBar,
    QHeaderView,
)

from config import (
    load_config,
    save_config,
    get_projects_root,
    get_antigravity_root,
    get_active_theme,
    get_app_version,
    get_last_seen_version,
    set_last_seen_version,
    get_changelog_data,
    DEFAULT_PROJECTS_ROOT,
    DEFAULT_ANTIGRAVITY_ROOT,
)
from data_loader import (
    build_project_map,
    load_chat_messages,
    delete_project_cascade,
    delete_conversation,
    move_conversation,
    ConversationInfo,
    get_paths,
    _find_brain_path,
)

try:
    import markdown
except ImportError:
    markdown = None

try:
    from pygments import highlight as _pyg_highlight
    from pygments.lexers import get_lexer_for_filename, TextLexer
    from pygments.formatters import HtmlFormatter as _PygHtmlFormatter
    from pygments.util import ClassNotFound as _PygClassNotFound
except ImportError:  # pragma: no cover - pygments est une dépendance déclarée
    _pyg_highlight = None

# =====================================================================
# STYLES CSS / QSS (Thèmes Clair & Sombre Antigravity)
# =====================================================================
DARK_QSS = """
QMainWindow, QDialog {
    background-color: #18181b;
    color: #f4f4f5;
    font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

QSplitter::handle {
    background-color: #27272a;
    width: 2px;
}

/* Sidebar */
QFrame#sidebarFrame {
    background-color: #121215;
    border-right: 1px solid #27272a;
}

QLabel#appTitle {
    font-size: 15px;
    font-weight: bold;
    color: #ffffff;
}

QPushButton.toolBtn {
    background-color: transparent;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    color: #a1a1aa;
    font-size: 13px;
    padding: 4px 8px;
}
QPushButton.toolBtn:hover {
    background-color: #27272a;
    color: #ffffff;
    border-color: #52525b;
}

/* TreeWidget */
QTreeWidget {
    background-color: transparent;
    border: none;
    color: #e4e4e7;
    font-size: 12px;
    outline: none;
}
QTreeWidget::item {
    padding: 5px 4px;
    border-radius: 5px;
    margin: 1px 4px;
}
QTreeWidget::item:hover {
    background-color: #27272a;
    color: #ffffff;
}
QTreeWidget::item:selected {
    background-color: #2e384d;
    color: #60a5fa;
    font-weight: 600;
}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {
    image: none;
}
QTreeWidget::branch:open:has-children:!has-siblings,
QTreeWidget::branch:open:has-children:has-siblings {
    image: none;
}

/* Chat Viewer */
QFrame#chatHeader {
    background-color: #18181b;
    border-bottom: 1px solid #27272a;
    padding: 10px 16px;
}
QLabel#chatTitle {
    font-size: 16px;
    font-weight: bold;
    color: #ffffff;
}
QLabel#chatMeta {
    font-size: 11px;
    color: #a1a1aa;
}

QTextBrowser#chatBrowser {
    background-color: #18181b;
    border: none;
    padding: 16px;
    color: #e4e4e7;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
}

/* Status Bar */
QStatusBar {
    background-color: #121215;
    border-top: 1px solid #27272a;
    color: #71717a;
    font-size: 11px;
    padding: 4px 10px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #18181b;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #3f3f46;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #52525b;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Champ de recherche globale (sidebar) */
QLineEdit#searchInput {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    color: #f4f4f5;
    font-size: 12px;
    padding: 5px 8px;
}
QLineEdit#searchInput:focus {
    border-color: #60a5fa;
}

/* Barre de recherche locale (find bar) */
QFrame#findBar {
    background-color: #1f1f23;
    border-bottom: 1px solid #27272a;
}
QLineEdit#findInput {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 5px;
    color: #f4f4f5;
    font-size: 12px;
    padding: 4px 7px;
}
QLineEdit#findInput:focus {
    border-color: #60a5fa;
}
QLabel#findResultLabel {
    color: #71717a;
    font-size: 11px;
    min-width: 90px;
}
"""

LIGHT_QSS = """
QMainWindow, QDialog {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

QSplitter::handle {
    background-color: #e2e8f0;
    width: 2px;
}

/* Sidebar */
QFrame#sidebarFrame {
    background-color: #f1f5f9;
    border-right: 1px solid #e2e8f0;
}

QLabel#appTitle {
    font-size: 15px;
    font-weight: bold;
    color: #0f172a;
}

QPushButton.toolBtn {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #475569;
    font-size: 13px;
    padding: 4px 8px;
}
QPushButton.toolBtn:hover {
    background-color: #f8fafc;
    color: #0f172a;
    border-color: #94a3b8;
}

/* TreeWidget */
QTreeWidget {
    background-color: transparent;
    border: none;
    color: #1e293b;
    font-size: 12px;
    outline: none;
}
QTreeWidget::item {
    padding: 5px 4px;
    border-radius: 5px;
    margin: 1px 4px;
}
QTreeWidget::item:hover {
    background-color: #e2e8f0;
    color: #0f172a;
}
QTreeWidget::item:selected {
    background-color: #dbeafe;
    color: #1d4ed8;
    font-weight: 600;
}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {
    image: none;
}
QTreeWidget::branch:open:has-children:!has-siblings,
QTreeWidget::branch:open:has-children:has-siblings {
    image: none;
}

/* Chat Viewer */
QFrame#chatHeader {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 10px 16px;
}
QLabel#chatTitle {
    font-size: 16px;
    font-weight: bold;
    color: #0f172a;
}
QLabel#chatMeta {
    font-size: 11px;
    color: #64748b;
}

QTextBrowser#chatBrowser {
    background-color: #ffffff;
    border: none;
    padding: 16px;
    color: #0f172a;
    selection-background-color: #bfdbfe;
    selection-color: #1e3a8a;
}

/* Status Bar */
QStatusBar {
    background-color: #f1f5f9;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 11px;
    padding: 4px 10px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #f8fafc;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Champ de recherche globale (sidebar) */
QLineEdit#searchInput {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #0f172a;
    font-size: 12px;
    padding: 5px 8px;
}
QLineEdit#searchInput:focus {
    border-color: #2563eb;
}

/* Barre de recherche locale (find bar) */
QFrame#findBar {
    background-color: #f1f5f9;
    border-bottom: 1px solid #e2e8f0;
}
QLineEdit#findInput {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    color: #0f172a;
    font-size: 12px;
    padding: 4px 7px;
}
QLineEdit#findInput:focus {
    border-color: #2563eb;
}
QLabel#findResultLabel {
    color: #64748b;
    font-size: 11px;
    min-width: 90px;
}
"""


# =====================================================================
# QLineEdit personnalisé pour la Find Bar (gestion locale de la touche Échap)
# =====================================================================
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QKeyEvent

class _FindLineEdit(QLineEdit):
    """QLineEdit qui émet escape_pressed quand l'utilisateur appuie sur Échap.

    Cela permet de fermer la find bar sans recourir à un QShortcut global
    (qui peut capturer Échap au niveau de la fenêtre et la fermer silencieusement
    dans les builds PyInstaller --windowed).
    """

    escape_pressed = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
        else:
            super().keyPressEvent(event)


# =====================================================================
# Boîte de Dialogue des Paramètres (PyQt6)
# =====================================================================
class SettingsDialog(QDialog):
    def __init__(self, parent: QMainWindow | None = None, on_save_callback=None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.setWindowTitle("Paramètres — Dossiers sources & Thème")
        self.setFixedSize(560, 320)
        self.setModal(True)

        is_dark = get_active_theme() == "dark"
        input_style = (
            "padding: 6px; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 5px; color: #fff;"
            if is_dark
            else "padding: 6px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 5px; color: #0f172a;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 1. Racine des Projets
        layout.addWidget(QLabel("Répertoire racine des projets (ex: E:\\Dev) :"))
        p_row = QHBoxLayout()
        self.proj_edit = QLineEdit(str(get_projects_root()))
        self.proj_edit.setStyleSheet(input_style)
        p_row.addWidget(self.proj_edit)
        btn_browse_p = QPushButton("Parcourir…")
        btn_browse_p.clicked.connect(self._browse_proj)
        p_row.addWidget(btn_browse_p)
        layout.addLayout(p_row)

        # 2. Racine Antigravity
        layout.addWidget(QLabel("Dossier Antigravity IDE (ex: %USERPROFILE%\\.gemini\\antigravity-ide) :"))
        ag_row = QHBoxLayout()
        self.ag_edit = QLineEdit(str(get_antigravity_root()))
        self.ag_edit.setStyleSheet(input_style)
        ag_row.addWidget(self.ag_edit)
        btn_browse_ag = QPushButton("Parcourir…")
        btn_browse_ag.clicked.connect(self._browse_ag)
        ag_row.addWidget(btn_browse_ag)
        layout.addLayout(ag_row)

        # 3. Thème de l'interface
        layout.addWidget(QLabel("Thème de l'application :"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Système (Par défaut)", "system")
        self.theme_combo.addItem("Clair (Light)", "light")
        self.theme_combo.addItem("Sombre (Dark)", "dark")
        self.theme_combo.setStyleSheet(input_style)

        current_theme = load_config().get("theme", "system").lower()
        if current_theme == "light":
            self.theme_combo.setCurrentIndex(1)
        elif current_theme == "dark":
            self.theme_combo.setCurrentIndex(2)
        else:
            self.theme_combo.setCurrentIndex(0)

        layout.addWidget(self.theme_combo)

        layout.addSpacing(10)

        # Boutons
        btn_box = QHBoxLayout()
        btn_reset = QPushButton("Réinitialiser")
        btn_reset.clicked.connect(self._reset_defaults)
        btn_box.addWidget(btn_reset)

        btn_changelog = QPushButton("📜 Quoi de neuf ?")
        btn_changelog.setToolTip("Afficher l'historique des modifications de cette version")
        btn_changelog.clicked.connect(self._open_changelog)
        btn_box.addWidget(btn_changelog)

        btn_box.addStretch()

        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Enregistrer")
        btn_save.setStyleSheet("background-color: #2563eb; color: #fff; font-weight: bold; padding: 6px 16px; border-radius: 5px;")
        btn_save.clicked.connect(self._save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _browse_proj(self):
        d = QFileDialog.getExistingDirectory(self, "Sélectionner la racine des projets", self.proj_edit.text())
        if d:
            self.proj_edit.setText(d)

    def _browse_ag(self):
        d = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier Antigravity", self.ag_edit.text())
        if d:
            self.ag_edit.setText(d)

    def _reset_defaults(self):
        self.proj_edit.setText(str(DEFAULT_PROJECTS_ROOT))
        self.ag_edit.setText(str(DEFAULT_ANTIGRAVITY_ROOT))
        self.theme_combo.setCurrentIndex(0)

    def _open_changelog(self):
        dlg = ChangelogDialog(self)
        dlg.show()

    def _save(self):
        cfg = load_config()
        cfg["projects_root"] = self.proj_edit.text().strip()
        cfg["antigravity_root"] = self.ag_edit.text().strip()
        cfg["theme"] = self.theme_combo.currentData()
        save_config(cfg)
        self.accept()
        if self.on_save_callback:
            self.on_save_callback()


# =====================================================================
# Boîte de Dialogue Modeless : Changelog (Notes de Version)
# =====================================================================
class ChangelogDialog(QDialog):
    """Fenêtre modeless affichant l'historique des versions sous forme de TreeView compacte."""

    def __init__(self, parent: QMainWindow | None = None):
        super().__init__(parent)
        self.setWindowTitle("Historique des Mises à Jour — Antigravity Manager")
        self.resize(620, 520)
        self.setMinimumSize(450, 320)
        self.setModal(False)  # Fenêtre non-bloquante (modeless)

        icon = _get_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        header_title = QLabel("🚀 Notes de Version")
        header_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(header_title)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setAnimated(True)
        layout.addWidget(self.tree)

        changelog = get_changelog_data()
        is_dark = get_active_theme() == "dark"
        tag_color = QColor("#60a5fa" if is_dark else "#0284c7")
        cat_color = QColor("#a78bfa" if is_dark else "#6d28d9")
        item_color = QColor("#f4f4f5" if is_dark else "#0f172a")

        for ver, cats in changelog.items():
            ver_item = QTreeWidgetItem([f"📦 Version {ver} (Actuelle)"])
            ver_item.setForeground(0, tag_color)
            f = ver_item.font(0)
            f.setBold(True)
            f.setPointSize(f.pointSize() + 1)
            ver_item.setFont(0, f)
            self.tree.addTopLevelItem(ver_item)

            for cat, items in cats.items():
                cat_item = QTreeWidgetItem([cat])
                cat_item.setForeground(0, cat_color)
                f_c = cat_item.font(0)
                f_c.setBold(True)
                cat_item.setFont(0, f_c)
                ver_item.addChild(cat_item)

                for it in items:
                    leaf = QTreeWidgetItem([f"  •  {it}"])
                    leaf.setForeground(0, item_color)
                    cat_item.addChild(leaf)

            ver_item.setExpanded(True)
            for i in range(ver_item.childCount()):
                ver_item.child(i).setExpanded(True)

        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch()
        btn_close = QPushButton("Fermer")
        btn_close.setStyleSheet("padding: 6px 18px; font-weight: bold; border-radius: 5px;")
        btn_close.clicked.connect(self.close)
        bottom_bar.addWidget(btn_close)
        layout.addLayout(bottom_bar)



def _get_app_icon() -> QIcon:
    """Retourne l'icône officielle de l'application depuis assets/."""
    base_dirs = [
        Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent,
        Path(__file__).parent,
    ]
    if hasattr(sys, "_MEIPASS"):
        base_dirs.insert(0, Path(getattr(sys, "_MEIPASS")))

    for base in base_dirs:
        for name in ("assets/icon.png", "assets/icon.ico", "icon.png", "icon.ico"):
            p = base / name
            if p.is_file():
                return QIcon(str(p))
    return QIcon()


# =====================================================================
# Application Principale Antigravity Manager (PyQt6)
# =====================================================================
class AntigravityManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.version = get_app_version()
        self.setWindowTitle(f"Antigravity Manager v{self.version} — Project & Chat Management")
        self.resize(1260, 840)
        self.setMinimumSize(850, 520)

        icon = _get_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        # Données
        self.project_convs: dict[str, list[ConversationInfo]] = {}
        self.all_convs: list[ConversationInfo] = []
        self.selected_conv: ConversationInfo | None = None
        self.show_raw_markdown: bool = False
        self.changelog_dialog: ChangelogDialog | None = None

        # Historique de navigation entre conversations (pile maison, alimentée
        # par display_chat). Le bouton ← dépile pour revenir à la conversation
        # précédente. On n'utilise plus l'historique interne de QTextBrowser
        # (celui-ci était pollué par les clics sur les liens file:///).
        self._nav_history: list[ConversationInfo] = []
        self._nav_suppress_push: bool = False

        # État « aperçu de fichier » : quand on clique un lien fichier dans une
        # conversation, on affiche son contenu dans la vue et le bouton ←
        # restaure la conversation mémorisée ici.
        self._file_view_active: bool = False
        self._file_view_return_conv: ConversationInfo | None = None

        # Timer debounce pour la recherche globale (400ms)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)

        self._apply_theme()
        self._build_ui()
        self.reload_data()

    def showEvent(self, event):
        super().showEvent(event)
        # Affichage automatique de la fenêtre de changelog (modeless) au 1er lancement d'une mise à jour
        last_seen = get_last_seen_version()
        if last_seen != self.version:
            set_last_seen_version(self.version)
            self.changelog_dialog = ChangelogDialog(self)
            self.changelog_dialog.show()

    def _apply_theme(self):
        app = QApplication.instance()
        if app:
            theme = get_active_theme()
            app.setStyleSheet(DARK_QSS if theme == "dark" else LIGHT_QSS)

    def _build_ui(self):
        # Widget central + Layout principal
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # QSplitter horizontal (Sidebar + Chat)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # -------------------------------------------------------------
        # 1. VOLET GAUCHE (Sidebar)
        # -------------------------------------------------------------
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 12, 10, 8)
        sidebar_layout.setSpacing(8)

        # Header Sidebar
        sb_header = QHBoxLayout()
        app_icon = _get_app_icon()
        if not app_icon.isNull():
            icon_lbl = QLabel()
            icon_lbl.setPixmap(app_icon.pixmap(24, 24))
            icon_lbl.setFixedSize(24, 24)
            sb_header.addWidget(icon_lbl)

        title_lbl = QLabel("Antigravity")
        title_lbl.setObjectName("appTitle")
        sb_header.addWidget(title_lbl)
        sb_header.addStretch()

        btn_refresh = QPushButton("🔄")
        btn_refresh.setProperty("class", "toolBtn")
        btn_refresh.setToolTip("Actualiser les données")
        btn_refresh.clicked.connect(self.reload_data)
        sb_header.addWidget(btn_refresh)

        btn_settings = QPushButton("⚙️")
        btn_settings.setProperty("class", "toolBtn")
        btn_settings.setToolTip("Paramètres des dossiers & Thème")
        btn_settings.clicked.connect(self._open_settings)
        sb_header.addWidget(btn_settings)

        sidebar_layout.addLayout(sb_header)

        # Champ de recherche globale (au-dessus du filtre projet)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("🔍  Rechercher dans les discussions…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        sidebar_layout.addWidget(self.search_input)

        # Filtre par projet
        self.project_filter_combo = QComboBox()
        self.project_filter_combo.setObjectName("projectFilterCombo")
        is_dark = get_active_theme() == "dark"
        self.project_filter_combo.setStyleSheet(
            "padding: 5px 8px; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 6px; color: #f4f4f5; font-size: 12px;"
            if is_dark
            else "padding: 5px 8px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; color: #0f172a; font-size: 12px;"
        )
        self.project_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        sidebar_layout.addWidget(self.project_filter_combo)

        # Tree Widget natif accéléré matériellement
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setAnimated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        sidebar_layout.addWidget(self.tree)

        self.splitter.addWidget(sidebar)

        # -------------------------------------------------------------
        # 2. VOLET DROIT (Chat Viewer)
        # -------------------------------------------------------------
        chat_container = QFrame()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # En-tête du Chat
        self.chat_header = QFrame()
        self.chat_header.setObjectName("chatHeader")
        header_vbox = QVBoxLayout(self.chat_header)
        header_vbox.setContentsMargins(16, 12, 16, 12)
        header_vbox.setSpacing(4)

        header_top_row = QHBoxLayout()

        # Bouton retour : revient à la conversation précédemment consultée
        # (pile d'historique maison self._nav_history).
        self.btn_back = QPushButton("←")
        self.btn_back.setProperty("class", "toolBtn")
        self.btn_back.setToolTip("Revenir à la conversation précédente")
        self.btn_back.setFixedWidth(32)
        self.btn_back.setVisible(False)
        self.btn_back.clicked.connect(self._navigate_back)
        header_top_row.addWidget(self.btn_back)

        self.chat_title = QLabel("Sélectionnez une conversation")
        self.chat_title.setObjectName("chatTitle")
        header_top_row.addWidget(self.chat_title)
        header_top_row.addStretch()

        self.btn_toggle_raw = QPushButton("<> Source")
        self.btn_toggle_raw.setProperty("class", "toolBtn")
        self.btn_toggle_raw.setToolTip("Basculer entre la vue riche HTML et le code Markdown brut (<>)")
        self.btn_toggle_raw.clicked.connect(self._toggle_markdown_mode)
        self.btn_toggle_raw.setVisible(False)
        header_top_row.addWidget(self.btn_toggle_raw)

        self.btn_find_toggle = QPushButton("🔍")
        self.btn_find_toggle.setProperty("class", "toolBtn")
        self.btn_find_toggle.setToolTip("Rechercher dans la discussion (Ctrl+F)")
        self.btn_find_toggle.clicked.connect(self._toggle_find_bar)
        self.btn_find_toggle.setVisible(False)
        header_top_row.addWidget(self.btn_find_toggle)

        self.btn_open_folder = QPushButton("📂 Ouvrir le dossier")
        self.btn_open_folder.setProperty("class", "toolBtn")
        self.btn_open_folder.setToolTip("Ouvrir le dossier de la session dans l'Explorateur Windows")
        self.btn_open_folder.clicked.connect(self._open_current_session_folder)
        self.btn_open_folder.setVisible(False)
        header_top_row.addWidget(self.btn_open_folder)

        header_vbox.addLayout(header_top_row)

        self.chat_meta = QLabel("Choisissez un projet ou une conversation dans la barre latérale.")
        self.chat_meta.setObjectName("chatMeta")
        header_vbox.addWidget(self.chat_meta)

        chat_layout.addWidget(self.chat_header)

        # Barre de recherche locale dans la discussion (Find Bar)
        self.find_bar = QFrame()
        self.find_bar.setObjectName("findBar")
        find_bar_layout = QHBoxLayout(self.find_bar)
        find_bar_layout.setContentsMargins(8, 4, 8, 4)
        find_bar_layout.setSpacing(4)

        self.find_input = _FindLineEdit()
        self.find_input.setObjectName("findInput")
        self.find_input.setPlaceholderText("Rechercher dans la discussion…")
        self.find_input.returnPressed.connect(self._find_next)
        self.find_input.textChanged.connect(self._on_find_text_changed)
        self.find_input.escape_pressed.connect(self._hide_find_bar)
        find_bar_layout.addWidget(self.find_input)

        self.find_result_label = QLabel("")
        self.find_result_label.setObjectName("findResultLabel")
        find_bar_layout.addWidget(self.find_result_label)

        self._btn_find_prev = QPushButton("▲")
        self._btn_find_prev.setProperty("class", "toolBtn")
        self._btn_find_prev.setToolTip("Occurrence précédente")
        self._btn_find_prev.setFixedWidth(28)
        self._btn_find_prev.clicked.connect(self._find_prev)
        find_bar_layout.addWidget(self._btn_find_prev)

        self._btn_find_next = QPushButton("▼")
        self._btn_find_next.setProperty("class", "toolBtn")
        self._btn_find_next.setToolTip("Occurrence suivante")
        self._btn_find_next.setFixedWidth(28)
        self._btn_find_next.clicked.connect(self._find_next)
        find_bar_layout.addWidget(self._btn_find_next)

        self._btn_find_close = QPushButton("✕")
        self._btn_find_close.setProperty("class", "toolBtn")
        self._btn_find_close.setToolTip("Fermer la recherche (Échap)")
        self._btn_find_close.setFixedWidth(28)
        self._btn_find_close.clicked.connect(self._hide_find_bar)
        find_bar_layout.addWidget(self._btn_find_close)

        self.find_bar.setVisible(False)
        chat_layout.addWidget(self.find_bar)

        # Navigateur de Chat HTML / CSS riche
        self.chat_browser = QTextBrowser()
        self.chat_browser.setObjectName("chatBrowser")
        # On NE laisse PAS QTextBrowser naviguer en interne : un clic sur un lien
        # file:///... était traité comme une ressource interne (setSource), ce qui
        # polluait son historique et cassait le bouton retour. On intercepte donc
        # tous les clics et on les ouvre dans l'application système adéquate.
        self.chat_browser.setOpenLinks(False)
        self.chat_browser.setOpenExternalLinks(False)
        self.chat_browser.anchorClicked.connect(self._on_anchor_clicked)
        chat_layout.addWidget(self.chat_browser)

        self.splitter.addWidget(chat_container)

        # Raccourci clavier : Ctrl+F → ouvrir la find bar
        # Stocké en attribut d'instance pour éviter le garbage-collection Python
        self._shortcut_find = QShortcut(QKeySequence("Ctrl+F"), self)
        self._shortcut_find.activated.connect(self._show_find_bar)
        # Note : Escape est géré directement par _FindLineEdit (voir classe dédiée)

        # Proportions initiales : 340px sidebar, reste pour le chat
        self.splitter.setSizes([340, 920])

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    # -----------------------------------------------------------------
    # Chargement & Rendu des Données
    # -----------------------------------------------------------------
    def _on_filter_changed(self):
        """Réagit au changement de filtre projet. Relance la recherche si active."""
        if hasattr(self, "search_input") and self.search_input.text().strip():
            self._do_search()
        else:
            self._populate_tree()

    def reload_data(self):
        self._apply_theme()
        projects_root, _, _, _, _ = get_paths()
        self.status_bar.showMessage("Chargement des données Antigravity…")
        QApplication.processEvents()

        self.project_convs, self.all_convs = build_project_map()

        # Mettre à jour la boîte de filtre par projet
        if hasattr(self, "project_filter_combo"):
            self.project_filter_combo.blockSignals(True)
            cur_data = self.project_filter_combo.currentData()
            self.project_filter_combo.clear()

            total_c = len(self.all_convs)
            no_proj = [c for c in self.all_convs if not c.project]
            
            self.project_filter_combo.addItem(f"📁 Tous les projets ({len(self.project_convs)} projs, {total_c} convs)", "ALL")
            if no_proj:
                self.project_filter_combo.addItem(f"⚠️ Sans projet ({len(no_proj)})", "NONE")

            for p_name in sorted(self.project_convs.keys(), key=str.lower):
                c_count = len(self.project_convs[p_name])
                self.project_filter_combo.addItem(f"📁 {p_name} ({c_count})", p_name)

            # Restaurer sélection précédente si disponible
            idx = 0
            if cur_data:
                for i in range(self.project_filter_combo.count()):
                    if self.project_filter_combo.itemData(i) == cur_data:
                        idx = i
                        break
            self.project_filter_combo.setCurrentIndex(idx)
            self.project_filter_combo.blockSignals(False)

        self._populate_tree()

        if self.selected_conv:
            # Tenter de restaurer la sélection
            found = False
            for c in self.all_convs:
                if c.conv_id == self.selected_conv.conv_id:
                    self.display_chat(c)
                    found = True
                    break
            if not found:
                self._clear_chat()
        else:
            self._clear_chat()

        total_p = len(self.project_convs)
        total_c = len(self.all_convs)
        self.status_bar.showMessage(f"Racine : {projects_root} | {total_p} projets — {total_c} conversations")

    def _populate_tree(self):
        self.tree.clear()
        is_dark = get_active_theme() == "dark"
        header_color = QColor("#a1a1aa" if is_dark else "#64748b")
        active_color = QColor("#f4f4f5" if is_dark else "#0f172a")
        empty_color = QColor("#71717a" if is_dark else "#94a3b8")

        filter_val = "ALL"
        if hasattr(self, "project_filter_combo") and self.project_filter_combo.count() > 0:
            filter_val = self.project_filter_combo.currentData() or "ALL"

        # CAS 1 : Filtre "Sans projet" uniquement
        if filter_val == "NONE":
            no_proj_convs = [c for c in self.all_convs if not c.project]
            header_item = QTreeWidgetItem([f"DISCUSSIONS SANS PROJET ({len(no_proj_convs)})"])
            header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header_item.setForeground(0, header_color)
            f = header_item.font(0)
            f.setBold(True)
            header_item.setFont(0, f)
            self.tree.addTopLevelItem(header_item)

            for c_info in no_proj_convs:
                display_title = c_info.title if c_info.title else c_info.conv_id[:12]
                if len(display_title) > 36:
                    display_title = display_title[:34] + "…"
                time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
                c_item = QTreeWidgetItem([f"💬  {display_title}  •  [⚠️ Sans projet]{time_suffix}"])
                c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
                self.tree.addTopLevelItem(c_item)

            header_item.setExpanded(True)
            return

        # CAS 2 : Projet unique sélectionné
        if filter_val != "ALL" and filter_val in self.project_convs:
            convs = self.project_convs[filter_val]
            proj_header_item = QTreeWidgetItem([f"PROJET : {filter_val} ({len(convs)} convs)"])
            proj_header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            proj_header_item.setForeground(0, header_color)
            f = proj_header_item.font(0)
            f.setBold(True)
            proj_header_item.setFont(0, f)
            self.tree.addTopLevelItem(proj_header_item)

            p_item = QTreeWidgetItem([f"📁  {filter_val}  ({len(convs)})"])
            p_item.setData(0, Qt.ItemDataRole.UserRole, ("project", filter_val, convs))
            p_item.setForeground(0, active_color if convs else empty_color)

            for c_info in convs:
                display_title = c_info.title if c_info.title else c_info.conv_id[:12]
                if len(display_title) > 38:
                    display_title = display_title[:36] + "…"
                time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
                c_item = QTreeWidgetItem([f"💬  {display_title}{time_suffix}"])
                c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
                p_item.addChild(c_item)

            p_item.setExpanded(True)
            self.tree.addTopLevelItem(p_item)
            proj_header_item.setExpanded(True)
            return

        # CAS 3 : "ALL" — Tous les projets + Toutes les conversations récentes
        # Section 1 : Projets
        proj_header_item = QTreeWidgetItem(["PROJETS"])
        proj_header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        proj_header_item.setForeground(0, header_color)
        f = proj_header_item.font(0)
        f.setBold(True)
        proj_header_item.setFont(0, f)
        self.tree.addTopLevelItem(proj_header_item)

        for proj_name in sorted(self.project_convs.keys(), key=str.lower):
            convs = self.project_convs[proj_name]
            count = len(convs)
            
            p_text = f"📁  {proj_name}" + (f"  ({count})" if count > 0 else "")
            p_item = QTreeWidgetItem([p_text])
            p_item.setData(0, Qt.ItemDataRole.UserRole, ("project", proj_name, convs))
            
            if count > 0:
                p_item.setForeground(0, active_color)
                for c_info in convs:
                    display_title = c_info.title if c_info.title else c_info.conv_id[:12]
                    if len(display_title) > 38:
                        display_title = display_title[:36] + "…"
                    
                    time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
                    c_item = QTreeWidgetItem([f"💬  {display_title}{time_suffix}"])
                    c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
                    p_item.addChild(c_item)
                
                # En mode "Tous les projets", les dossiers restent repliés par défaut
                p_item.setExpanded(False)
            else:
                p_item.setForeground(0, empty_color)

            self.tree.addTopLevelItem(p_item)

        # Section 2 : Conversations Récentes avec badge de projet
        conv_header_item = QTreeWidgetItem(["CONVERSATIONS RÉCENTES"])
        conv_header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        conv_header_item.setForeground(0, header_color)
        f2 = conv_header_item.font(0)
        f2.setBold(True)
        conv_header_item.setFont(0, f2)
        self.tree.addTopLevelItem(conv_header_item)

        for c_info in self.all_convs[:40]:
            display_title = c_info.title if c_info.title else c_info.conv_id[:12]
            if len(display_title) > 30:
                display_title = display_title[:28] + "…"
            p_badge = f"  •  [{c_info.project}]" if c_info.project else "  •  [⚠️ Sans projet]"
            time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
            c_item = QTreeWidgetItem([f"💬  {display_title}{p_badge}{time_suffix}"])
            c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
            self.tree.addTopLevelItem(c_item)

        # Déplier les sections principales
        proj_header_item.setExpanded(True)
        conv_header_item.setExpanded(True)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        dtype = data[0]
        if dtype == "conv":
            c_info: ConversationInfo = data[1]
            self.display_chat(c_info)
        elif dtype == "project":
            # Si on clique sur le projet, on bascule son expansion
            if item.childCount() > 0:
                item.setExpanded(not item.isExpanded())

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None):
        """Met à jour l'affichage lors de la navigation au clavier (flèches haut/bas)."""
        if not current:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        dtype = data[0]
        if dtype == "conv":
            c_info: ConversationInfo = data[1]
            if not self.selected_conv or self.selected_conv.conv_id != c_info.conv_id:
                # Navigation au clavier : on ne pollue pas l'historique du bouton ←
                # (seuls un clic explicite, un résultat de recherche ou un lien empilent).
                self.display_chat(c_info, record_history=False)

    def _toggle_markdown_mode(self):
        """Bascule entre la vue riche HTML et le mode markdown source brut (<>)."""
        self.show_raw_markdown = not self.show_raw_markdown
        self.btn_toggle_raw.setText("👁️ Vue Riche" if self.show_raw_markdown else "<> Source")
        if self.selected_conv:
            self.display_chat(self.selected_conv)

    # -----------------------------------------------------------------
    # Affichage du Chat avec Rendu HTML / CSS Riche & Mode Markdown
    # -----------------------------------------------------------------
    def display_chat(self, info: ConversationInfo, record_history: bool = True):
        # Historique de navigation : on empile la conversation qui était affichée
        # avant celle-ci, sauf quand l'appel vient de _navigate_back (dépilage),
        # d'un simple re-render de la même conversation (toggle markdown, etc.),
        # ou d'un survol au clavier (record_history=False).
        if record_history and not self._nav_suppress_push:
            if self.selected_conv and self.selected_conv.conv_id != info.conv_id:
                self._nav_history.append(self.selected_conv)

        # On quitte l'éventuel mode « aperçu de fichier ».
        self._file_view_active = False
        self._file_view_return_conv = None
        self.btn_back.setToolTip("Revenir à la conversation précédente")
        self.btn_back.setVisible(bool(self._nav_history))

        self.selected_conv = info
        title_text = info.title if info.title else "Conversation sans titre"
        self.chat_title.setText(title_text)

        proj_str = f"📁 {info.project}" if info.project else "📁 (aucun projet)"
        date_str = info.last_activity.strftime("%d/%m/%Y à %H:%M") if info.last_activity else "Date inconnue"
        self.chat_meta.setText(f"{proj_str}   •   {date_str}   •   ID: {info.conv_id}")
        self.btn_open_folder.setVisible(True)
        self.btn_toggle_raw.setVisible(True)
        self.btn_find_toggle.setVisible(True)

        messages = load_chat_messages(info.conv_id)
        is_dark = get_active_theme() == "dark"

        if not messages:
            info_col = "#a1a1aa" if is_dark else "#475569"
            sub_col = "#71717a" if is_dark else "#64748b"
            html = f"""
            <div style="text-align: center; margin-top: 60px; font-family: sans-serif;">
                <p style="font-size: 24px;">ℹ️</p>
                <p style="font-size: 14px; font-weight: bold; color: {info_col};">Aucun message textuel dans les journaux.</p>
                <p style="font-size: 12px; color: {sub_col};">Cette session correspond probablement à une sous-tâche technique (subagent)<br>ou ses journaux ont été archivés.</p>
            </div>
            """
            self.chat_browser.setHtml(html)
            return

        # Couleurs selon le thème
        if is_dark:
            body_bg, body_col = "#18181b", "#e4e4e7"
            user_bg, user_border, user_title_col, user_text_col = "#27272a", "#3f3f46", "#60a5fa", "#ffffff"
            model_bg, model_border, model_title_col, model_text_col = "#18181b", "#8b5cf6", "#a78bfa", "#e4e4e7"
            pre_bg, pre_border, pre_col = "#121215", "#27272a", "#38bdf8"
            code_bg, code_col = "#27272a", "#38bdf8"
            hr_col, time_col = "#27272a", "#71717a"
        else:
            body_bg, body_col = "#ffffff", "#0f172a"
            user_bg, user_border, user_title_col, user_text_col = "#f0f9ff", "#bae6fd", "#0284c7", "#0f172a"
            model_bg, model_border, model_title_col, model_text_col = "#ffffff", "#7c3aed", "#6d28d9", "#1e293b"
            pre_bg, pre_border, pre_col = "#f8fafc", "#e2e8f0", "#0369a1"
            code_bg, code_col = "#f1f5f9", "#0369a1"
            hr_col, time_col = "#e2e8f0", "#64748b"

        # Mode Markdown Source Brut (<>)
        if self.show_raw_markdown:
            raw_blocks = []
            for msg in messages:
                role_label = "👤 Utilisateur" if msg.get("role") == "user" else "✨ Antigravity"
                ts = msg.get("timestamp", "")
                ts_str = f" ({ts})" if ts else ""
                raw_blocks.append(f"### {role_label}{ts_str}\n\n{msg.get('text', '').strip()}\n\n" + "─" * 50 + "\n")

            raw_content = "\n".join(raw_blocks)
            escaped_raw = (
                raw_content.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            html = f"""<!DOCTYPE html><html><head><style>
                body {{
                    background-color: {body_bg};
                    color: {body_col};
                    font-family: 'Consolas', 'Fira Code', monospace;
                    font-size: 13px;
                    line-height: 1.5;
                    padding: 16px;
                    white-space: pre-wrap;
                }}
            </style></head><body>{escaped_raw}</body></html>"""
            self.chat_browser.setHtml(html)
            # Pré-remplir la find bar si recherche globale active
            self._prefill_find_from_search()
            return

        # Construction du document HTML moderne (Vue Riche)
        html_parts = [
            f"""<!DOCTYPE html>
            <html>
            <head>
            <style>
                body {{
                    background-color: {body_bg};
                    color: {body_col};
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    font-size: 13px;
                    line-height: 1.6;
                    margin: 0;
                    padding: 10px;
                }}
                .msg-container {{
                    margin-bottom: 24px;
                }}
                .user-box {{
                    background-color: {user_bg};
                    border: 1px solid {user_border};
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin-bottom: 12px;
                }}
                .user-header {{
                    font-weight: bold;
                    color: {user_title_col};
                    font-size: 12px;
                    margin-bottom: 6px;
                    display: flex;
                    justify-content: space-between;
                }}
                .model-box {{
                    background-color: {model_bg};
                    border-left: 3px solid {model_border};
                    padding: 4px 16px;
                    margin-bottom: 16px;
                }}
                .model-header {{
                    font-weight: bold;
                    color: {model_title_col};
                    font-size: 12px;
                    margin-bottom: 6px;
                }}
                .time-tag {{
                    color: {time_col};
                    font-weight: normal;
                    font-size: 11px;
                    float: right;
                }}
                h1, h2, h3, h4 {{
                    margin-top: 12px;
                    margin-bottom: 6px;
                    color: {model_title_col};
                }}
                h1 {{ font-size: 16px; border-bottom: 1px solid {hr_col}; padding-bottom: 3px; }}
                h2 {{ font-size: 15px; border-bottom: 1px solid {hr_col}; padding-bottom: 2px; }}
                h3 {{ font-size: 14px; }}
                h4 {{ font-size: 13px; }}
                p {{ margin: 4px 0; }}
                ul, ol {{ margin: 4px 0; padding-left: 20px; }}
                li {{ margin-bottom: 2px; }}
                strong {{ font-weight: bold; }}
                blockquote {{
                    border-left: 3px solid {model_border};
                    margin: 6px 0;
                    padding: 4px 10px;
                    color: {time_col};
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 10px 0;
                }}
                th, td {{
                    border: 1px solid {hr_col};
                    padding: 5px 8px;
                    text-align: left;
                }}
                th {{
                    background-color: {pre_bg};
                    font-weight: bold;
                }}
                pre {{
                    background-color: {pre_bg};
                    border: 1px solid {pre_border};
                    border-radius: 6px;
                    padding: 10px;
                    font-family: 'Consolas', 'Fira Code', monospace;
                    font-size: 12px;
                    color: {pre_col};
                    /* Le moteur de QTextBrowser ne gère pas le scroll horizontal
                       d'un bloc : sans wrap, une longue ligne (chemin, commande
                       .bat/.ps1/.json) déborde de la fenêtre. On enroule. */
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                pre code {{
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                code {{
                    background-color: {code_bg};
                    padding: 2px 4px;
                    border-radius: 4px;
                    font-family: 'Consolas', monospace;
                    font-size: 12px;
                    color: {code_col};
                    /* Idem pour le code inline : un long `chemin\\vers\\script.ps1`
                       ne doit pas pousser toute la ligne hors du cadre. */
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                a {{
                    color: {model_title_col};
                    word-wrap: break-word;
                }}
                hr {{
                    border: 0;
                    height: 1px;
                    background-color: {hr_col};
                    margin: 20px 0;
                }}
            </style>
            </head>
            <body>
            """
        ]

        for msg in messages:
            role = msg.get("role")
            raw_text = msg.get("text", "").strip()
            ts = msg.get("timestamp", "")
            time_html = f"<span class='time-tag'>{ts}</span>" if ts else ""

            # Interprétation Markdown complète
            if markdown:
                try:
                    formatted = markdown.markdown(
                        raw_text,
                        extensions=["fenced_code", "tables", "nl2br"]
                    )
                except Exception:
                    escaped = (
                        raw_text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    formatted = escaped.replace("\n", "<br>")
            else:
                escaped = (
                    raw_text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                formatted = escaped.replace("\n", "<br>")

            if role == "user":
                html_parts.append(f"""
                <div class="msg-container">
                    <div class="user-box">
                        <div class="user-header">👤 Utilisateur {time_html}</div>
                        <div style="color: {user_text_col};">{formatted}</div>
                    </div>
                </div>
                """)
            elif role == "model":
                html_parts.append(f"""
                <div class="msg-container">
                    <div class="model-box">
                        <div class="model-header">✨ Antigravity {time_html}</div>
                        <div style="color: {model_text_col};">{formatted}</div>
                    </div>
                </div>
                """)

        html_parts.append("</body></html>")
        full_html = "".join(html_parts)
        self.chat_browser.setHtml(full_html)
        # Pré-remplir la find bar si recherche globale active
        self._prefill_find_from_search()

    def _clear_chat(self):
        self.selected_conv = None
        self.chat_title.setText("Sélectionnez une conversation")
        self.chat_meta.setText("Choisissez un projet ou une conversation dans la barre latérale.")
        self.btn_open_folder.setVisible(False)
        self.btn_toggle_raw.setVisible(False)
        self.btn_find_toggle.setVisible(False)
        self.chat_browser.setHtml("")
        self.find_bar.setVisible(False)
        self.find_result_label.setText("")
        self._nav_history.clear()
        self._file_view_active = False
        self._file_view_return_conv = None
        self.btn_back.setToolTip("Revenir à la conversation précédente")
        self.btn_back.setVisible(False)

    def _open_current_session_folder(self):
        if not self.selected_conv:
            return
        brain_p = _find_brain_path(self.selected_conv.conv_id)
        if brain_p and brain_p.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(brain_p)))
        else:
            QMessageBox.information(self, "Dossier introuvable", "Le dossier de cette session n'a pas été trouvé sur le disque.")

    # -----------------------------------------------------------------
    # Navigation : liens externes & bouton retour
    # -----------------------------------------------------------------
    # Extensions considérées comme du texte affichable dans la vue discussion.
    _TEXT_FILE_SUFFIXES = {
        ".py", ".bat", ".ps1", ".psm1", ".sh", ".json", ".jsonl", ".txt", ".md",
        ".markdown", ".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml", ".xml",
        ".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx", ".c", ".h", ".cpp",
        ".hpp", ".cs", ".java", ".rb", ".go", ".rs", ".sql", ".log", ".env",
        ".gitignore", ".dockerignore", ".spec", ".csv", ".tsv", ".properties",
    }
    _MAX_FILE_VIEW_BYTES = 512 * 1024  # 512 Ko : au-delà, on n'affiche pas

    def _on_anchor_clicked(self, url: QUrl):
        """Gère un clic sur un lien dans la vue discussion.

        QTextBrowser ne doit jamais naviguer en interne (setOpenLinks(False)) :
        les liens file:/// étaient sinon chargés comme des ressources internes,
        polluant l'historique et cassant le bouton retour.

        Règles :
          - lien web / mailto -> ouverture dans l'application système.
          - fichier texte local -> AFFICHAGE du contenu dans la vue discussion
                                   (jamais d'exécution : ouvrir un .py / .bat /
                                   .ps1 avec son application associée revient à
                                   l'exécuter). Coloration syntaxique si Pygments.
          - dossier local -> ouverture dans l'Explorateur.
          - fichier binaire / trop gros / introuvable -> message en status bar.
        """
        if url.isEmpty():
            return
        scheme = url.scheme().lower()

        if scheme in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)
            return

        if url.isLocalFile() or scheme == "file":
            local = Path(url.toLocalFile())
            if local.is_dir():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(local)))
                self.status_bar.showMessage(f"📂 Dossier ouvert : {local}", 4000)
            else:
                self._show_file_content(local)
            return
        # Tout autre schéma : ignoré volontairement (aucune navigation du browser).

    def _show_file_content(self, path: Path) -> None:
        """Affiche le contenu texte de `path` dans la vue discussion.

        Le bouton ← (‹_navigate_back›) restaure ensuite la conversation courante.
        Aucune exécution n'a lieu : on lit et on rend le fichier, point.
        """
        if not path.exists() or not path.is_file():
            self.status_bar.showMessage(f"⚠️ Fichier introuvable : {path}", 5000)
            return

        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size > self._MAX_FILE_VIEW_BYTES:
            self.status_bar.showMessage(
                f"⚠️ Fichier trop volumineux pour l'aperçu ({size // 1024} Ko) : {path.name}",
                6000,
            )
            return

        suffix = path.suffix.lower()
        looks_texty = suffix in self._TEXT_FILE_SUFFIXES or suffix == ""
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            self.status_bar.showMessage(f"⚠️ Lecture impossible : {exc}", 6000)
            return

        # Heuristique binaire : présence d'octets NUL.
        if b"\x00" in raw_bytes or (not looks_texty and suffix):
            self.status_bar.showMessage(
                f"⚠️ Fichier binaire ou non textuel, aperçu indisponible : {path.name}",
                6000,
            )
            return

        text = raw_bytes.decode("utf-8", errors="replace")

        # Mémorise la conversation à restaurer via le bouton ←.
        self._file_view_return_conv = self.selected_conv
        self._file_view_active = True

        is_dark = get_active_theme() == "dark"
        body_bg = "#18181b" if is_dark else "#ffffff"
        body_col = "#e4e4e7" if is_dark else "#0f172a"
        head_col = "#a78bfa" if is_dark else "#6d28d9"
        meta_col = "#71717a" if is_dark else "#64748b"
        border_col = "#27272a" if is_dark else "#e2e8f0"

        code_html, extra_css = self._render_file_body(path, text, is_dark)

        html = f"""<!DOCTYPE html><html><head><style>
            body {{
                background-color: {body_bg};
                color: {body_col};
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 13px;
                margin: 0;
                padding: 12px 16px;
            }}
            .file-head {{
                color: {head_col};
                font-weight: bold;
                font-size: 14px;
                word-break: break-all;
            }}
            .file-meta {{
                color: {meta_col};
                font-size: 11px;
                margin: 2px 0 10px 0;
                border-bottom: 1px solid {border_col};
                padding-bottom: 8px;
                word-break: break-all;
            }}
            pre {{
                white-space: pre-wrap;
                word-wrap: break-word;
                font-family: 'Consolas', 'Fira Code', monospace;
                font-size: 12px;
                line-height: 1.45;
                margin: 0;
            }}
            {extra_css}
        </style></head><body>
            <div class="file-head">📄 {path.name}</div>
            <div class="file-meta">{path}  •  {size} octets</div>
            {code_html}
        </body></html>"""

        self.chat_browser.setHtml(html)
        self.chat_title.setText(f"📄 {path.name}")
        self.chat_meta.setText(f"Aperçu fichier — {path}")
        self.btn_back.setVisible(True)
        self.btn_back.setToolTip("Revenir à la conversation")
        # La find bar reste pertinente sur le contenu du fichier ; les autres
        # boutons propres à la conversation n'ont pas de sens ici.
        self.btn_toggle_raw.setVisible(False)
        self.status_bar.showMessage(f"📄 Aperçu de {path.name}", 4000)

    def _render_file_body(self, path: Path, text: str, is_dark: bool) -> tuple[str, str]:
        """Retourne (html_du_contenu, css_additionnel).

        Utilise Pygments si disponible pour la coloration syntaxique, sinon
        repli sur un simple <pre> échappé.
        """
        if _pyg_highlight is not None:
            try:
                try:
                    lexer = get_lexer_for_filename(path.name, text)
                except _PygClassNotFound:
                    lexer = TextLexer()
                formatter = _PygHtmlFormatter(
                    style="monokai" if is_dark else "default",
                    nowrap=False,
                    noclasses=True,
                    prestyles="white-space: pre-wrap; word-wrap: break-word",
                )
                return _pyg_highlight(text, lexer, formatter), ""
            except Exception:
                pass  # repli ci-dessous

        escaped = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f"<pre>{escaped}</pre>", ""

    def _navigate_back(self):
        """Bouton ← : restaure la conversation.

        Deux cas :
          1. On regarde un fichier (‹_file_view_active›) -> on ré-affiche la
             conversation d'où venait le clic, sans toucher à l'historique.
          2. Sinon -> on dépile l'historique de navigation entre conversations.
        """
        if getattr(self, "_file_view_active", False):
            self._file_view_active = False
            conv = getattr(self, "_file_view_return_conv", None)
            self._file_view_return_conv = None
            self.btn_back.setToolTip("Revenir à la conversation précédente")
            if conv is not None:
                self._nav_suppress_push = True
                try:
                    self.display_chat(conv)
                finally:
                    self._nav_suppress_push = False
                self._select_conv_in_tree(conv.conv_id)
            else:
                self._clear_chat()
            self.btn_back.setVisible(bool(self._nav_history))
            return

        if not self._nav_history:
            return
        target = self._nav_history.pop()
        self._nav_suppress_push = True
        try:
            self.display_chat(target)
        finally:
            self._nav_suppress_push = False
        self.btn_back.setVisible(bool(self._nav_history))
        # Sélectionne la conversation cible dans l'arbre si elle y figure.
        self._select_conv_in_tree(target.conv_id)

    def _select_conv_in_tree(self, conv_id: str):
        """Positionne la sélection de l'arbre sur la conversation donnée (si présente)."""
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "conv" and data[1].conv_id == conv_id:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(item)
                self.tree.blockSignals(False)
                return
            it += 1

    # -----------------------------------------------------------------
    # Recherche Globale (Sidebar)
    # -----------------------------------------------------------------
    def _on_search_text_changed(self, text: str):
        """Déclenche la recherche avec un debounce de 400ms."""
        self._search_timer.stop()
        if not text.strip():
            self._populate_tree()
            projects_root, _, _, _, _ = get_paths()
            total_p = len(self.project_convs)
            total_c = len(self.all_convs)
            self.status_bar.showMessage(
                f"Racine : {projects_root} | {total_p} projets — {total_c} conversations"
            )
            return
        self._search_timer.start(400)

    def _do_search(self):
        """Lance la recherche dans le périmètre filtré (respecte le filtre projet actif)."""
        query = self.search_input.text().strip()
        if not query:
            return
        scope = self._get_search_scope()
        self.status_bar.showMessage(f"🔍 Recherche de « {query} » dans {len(scope)} conversation(s)…")
        QApplication.processEvents()

        results: dict[str, list[ConversationInfo]] = {}
        for i, c_info in enumerate(scope):
            if i % 5 == 0:
                QApplication.processEvents()
            messages = load_chat_messages(c_info.conv_id)
            found = any(query.lower() in msg.get("text", "").lower() for msg in messages)
            if found:
                key = c_info.project or "⚠️ Sans projet"
                results.setdefault(key, []).append(c_info)

        total_found = sum(len(v) for v in results.values())
        self.status_bar.showMessage(
            f"🔍 {total_found} conversation(s) trouvée(s) pour « {query} »"
        )
        self._populate_tree_search_results(results, query)

    def _get_search_scope(self) -> list[ConversationInfo]:
        """Retourne la liste des conversations dans le périmètre du filtre actif."""
        if not hasattr(self, "project_filter_combo"):
            return self.all_convs
        filter_val = self.project_filter_combo.currentData() or "ALL"
        if filter_val == "ALL":
            return self.all_convs
        if filter_val == "NONE":
            return [c for c in self.all_convs if not c.project]
        if filter_val in self.project_convs:
            return self.project_convs[filter_val]
        return self.all_convs

    def _populate_tree_search_results(
        self, results: dict[str, list[ConversationInfo]], query: str
    ):
        """Peuple l'arbre avec uniquement les résultats de recherche groupes par projet."""
        self.tree.clear()
        is_dark = get_active_theme() == "dark"
        header_color = QColor("#a1a1aa" if is_dark else "#64748b")
        active_color = QColor("#f4f4f5" if is_dark else "#0f172a")
        highlight_color = QColor("#f59e0b" if is_dark else "#d97706")

        if not results:
            no_result = QTreeWidgetItem([f"  Aucun résultat pour « {query} »"])
            no_result.setFlags(Qt.ItemFlag.ItemIsEnabled)
            no_result.setForeground(0, header_color)
            self.tree.addTopLevelItem(no_result)
            return

        total = sum(len(v) for v in results.values())
        header_item = QTreeWidgetItem([f"🔍 RÉSULTATS : {total} conv. — « {query} »"])
        header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        header_item.setForeground(0, highlight_color)
        f = header_item.font(0)
        f.setBold(True)
        header_item.setFont(0, f)
        self.tree.addTopLevelItem(header_item)

        for proj_name, convs in sorted(results.items(), key=lambda x: x[0].lower()):
            p_item = QTreeWidgetItem([f"📁  {proj_name}  ({len(convs)})"])
            p_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            p_item.setForeground(0, active_color)

            for c_info in convs:
                display_title = c_info.title if c_info.title else c_info.conv_id[:12]
                if len(display_title) > 38:
                    display_title = display_title[:36] + "…"
                time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
                c_item = QTreeWidgetItem([f"💬  {display_title}{time_suffix}"])
                c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
                p_item.addChild(c_item)

            p_item.setExpanded(True)
            self.tree.addTopLevelItem(p_item)

        header_item.setExpanded(True)

    # -----------------------------------------------------------------
    # Recherche Locale dans la Discussion (Find Bar)
    # -----------------------------------------------------------------
    def _prefill_find_from_search(self):
        """Pré-remplit et affiche la find bar si une recherche globale est active."""
        if hasattr(self, "search_input"):
            q = self.search_input.text().strip()
            if q:
                self._show_find_bar(prefill=q)

    def _show_find_bar(self, prefill: str = ""):
        """Affiche la barre de recherche locale. Pré-remplit optionnellement le champ."""
        if not self.selected_conv:
            return
        self.find_bar.setVisible(True)
        if prefill and self.find_input.text() != prefill:
            self.find_input.setText(prefill)
        self.find_input.setFocus()
        self.find_input.selectAll()
        if self.find_input.text():
            self._do_find_from_start()

    def _toggle_find_bar(self):
        """Bascule la visibilité de la find bar (bouton 🔍 dans le header)."""
        if self.find_bar.isVisible():
            self._hide_find_bar()
        else:
            self._show_find_bar()

    def _hide_find_bar(self):
        """Masque la barre de recherche locale et remet le focus sur le navigateur."""
        self.find_bar.setVisible(False)
        self.find_result_label.setText("")
        self.chat_browser.setFocus()

    def _on_find_text_changed(self):
        """Réinitialise la recherche depuis le début quand le texte change."""
        self._do_find_from_start()

    def _do_find_from_start(self):
        """Cherche depuis le début du document et met à jour le label de résultat."""
        query = self.find_input.text()
        if not query:
            self.find_result_label.setText("")
            return
        cursor = self.chat_browser.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        self.chat_browser.setTextCursor(cursor)
        found = self.chat_browser.find(query)
        self.find_result_label.setText("Trouvé ✓" if found else "Aucun résultat")

    def _find_next(self):
        """Cherche l'occurrence suivante (avec wrap autour)."""
        query = self.find_input.text()
        if not query:
            return
        found = self.chat_browser.find(query)
        if not found:
            # Wrap : retour au début
            cursor = self.chat_browser.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.chat_browser.setTextCursor(cursor)
            self.chat_browser.find(query)

    def _find_prev(self):
        """Cherche l'occurrence précédente (avec wrap autour)."""
        query = self.find_input.text()
        if not query:
            return
        found = self.chat_browser.find(query, QTextDocument.FindFlag.FindBackward)
        if not found:
            # Wrap : aller à la fin
            cursor = self.chat_browser.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.chat_browser.setTextCursor(cursor)
            self.chat_browser.find(query, QTextDocument.FindFlag.FindBackward)

    # -----------------------------------------------------------------
    # Menus Contextuels (Clic Droit)
    # -----------------------------------------------------------------
    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        dtype = data[0]
        menu = QMenu(self)

        if dtype == "project":
            _, proj_name, convs = data
            act_open = menu.addAction(f"📂 Ouvrir '{proj_name}' dans l'Explorateur")
            act_open.triggered.connect(lambda: self._open_project_folder(proj_name))

            menu.addSeparator()
            act_del = menu.addAction(f"🗑️ Supprimer '{proj_name}' et ses {len(convs)} conversation(s)")
            act_del.triggered.connect(lambda: self._delete_project(proj_name, convs))

        elif dtype == "conv":
            c_info: ConversationInfo = data[1]
            act_copy_id = menu.addAction("📋 Copier l'ID de session")
            act_copy_id.triggered.connect(lambda: QApplication.clipboard().setText(c_info.conv_id))

            act_open_brain = menu.addAction("📂 Ouvrir le dossier des journaux (brain)")
            act_open_brain.triggered.connect(lambda: self._open_conv_brain(c_info.conv_id))

            # Menu Déplacer vers un projet
            menu.addSeparator()
            move_menu = menu.addMenu("➡️ Déplacer vers le projet…")
            all_projs = sorted(self.project_convs.keys(), key=str.lower)
            for p in all_projs:
                if p != c_info.project:
                    act_m = move_menu.addAction(f"📁  {p}")
                    act_m.triggered.connect(lambda checked=False, target=p, info=c_info: self._move_conv_action(info, target))

            menu.addSeparator()
            act_del_conv = menu.addAction("🗑️ Supprimer cette conversation")
            act_del_conv.triggered.connect(lambda: self._delete_single_conv(c_info))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _move_conv_action(self, c_info: ConversationInfo, target_project: str):
        ok, msg = move_conversation(c_info.conv_id, target_project)
        if ok:
            QMessageBox.information(self, "Déplacement réussi", msg)
            self.reload_data()
        else:
            QMessageBox.critical(self, "Erreur", f"Échec du déplacement :\n{msg}")

    def _open_project_folder(self, project_name: str):
        proj_dir = get_projects_root() / project_name
        if proj_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(proj_dir)))
        else:
            QMessageBox.warning(self, "Erreur", f"Le dossier {proj_dir} n'existe pas.")

    def _open_conv_brain(self, conv_id: str):
        brain_p = _find_brain_path(conv_id)
        if brain_p and brain_p.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(brain_p)))
        else:
            QMessageBox.warning(self, "Erreur", "Dossier brain introuvable.")

    def _delete_single_conv(self, c_info: ConversationInfo):
        ret = QMessageBox.question(
            self,
            "Confirmer la suppression",
            f"Voulez-vous vraiment supprimer définitivement cette conversation ?\n\n"
            f"Titre : {c_info.title}\nID : {c_info.conv_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            ok, msg = delete_conversation(c_info.conv_id)
            if ok:
                QMessageBox.information(self, "Succès", "Conversation supprimée avec succès.")
                self.reload_data()
            else:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer : {msg}")

    def _delete_project(self, project_name: str, convs: list[ConversationInfo]):
        count = len(convs)
        ret = QMessageBox.warning(
            self,
            "Suppression de projet & conversations",
            f"⚠️ ATTENTION : Vous allez supprimer définitivement :\n\n"
            f"1. Le dossier du projet sur le disque : {get_projects_root() / project_name}\n"
            f"2. Toutes les {count} conversation(s) associée(s) dans Antigravity\n\n"
            f"Cette action est irréversible. Confirmer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            cids = [c.conv_id for c in convs]
            ok, msg = delete_project_cascade(project_name, cids)
            if ok:
                QMessageBox.information(self, "Succès", f"Le projet '{project_name}' et ses données ont été supprimés.")
                self.reload_data()
            else:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la suppression :\n{msg}")

    def _open_settings(self):
        dlg = SettingsDialog(self, on_save_callback=self.reload_data)
        dlg.exec()


# =====================================================================
# Point d'entrée de l'application
# =====================================================================
def main():
    import traceback
    import datetime

    # Chemin du log d'erreur : à côté du .exe (frozen) ou du script (dev)
    _log_path = (
        Path(sys.executable).resolve().parent / "crash.log"
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent / "crash.log"
    )
    # Marqueur de démarrage (confirme que main() est bien atteinte)
    try:
        _log_path.write_text(f"[{datetime.datetime.now()}] main() démarrée\n", encoding="utf-8")
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Antigravity.ProjectManager.App")
        except Exception:
            pass

    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")

        app_icon = _get_app_icon()
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)

        active_theme = get_active_theme()
        app.setStyleSheet(DARK_QSS if active_theme == "dark" else LIGHT_QSS)

        window = AntigravityManagerWindow()
        window.show()

        sys.exit(app.exec())
    except SystemExit:
        raise  # Sortie normale, ne pas loguer
    except Exception:
        err = traceback.format_exc()
        try:
            _log_path.write_text(
                f"[{datetime.datetime.now()}] CRASH:\n{err}",
                encoding="utf-8",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
