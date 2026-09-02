"""antigravity_manager.py — Interface PyQt6 Haute Performance pour Antigravity Manager.

Fournit une exploration ultra-fluide (C++ 60 FPS), une arborescence native (QTreeWidget),
un rendu HTML/CSS riche pour le chat (QTextBrowser), et la gestion complète des projets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import QIcon, QFont, QColor, QDesktopServices, QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
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
"""


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
# Application Principale Antigravity Manager (PyQt6)
# =====================================================================
class AntigravityManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Antigravity Manager — Project & Chat Management (PyQt6)")
        self.resize(1260, 840)
        self.setMinimumSize(850, 520)

        # Données
        self.project_convs: dict[str, list[ConversationInfo]] = {}
        self.all_convs: list[ConversationInfo] = []
        self.selected_conv: ConversationInfo | None = None

        self._apply_theme()
        self._build_ui()
        self.reload_data()

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
        btn_settings.setToolTip("Paramètres des dossiers")
        btn_settings.clicked.connect(self._open_settings)
        sb_header.addWidget(btn_settings)

        sidebar_layout.addLayout(sb_header)

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
        self.chat_title = QLabel("Sélectionnez une conversation")
        self.chat_title.setObjectName("chatTitle")
        header_top_row.addWidget(self.chat_title)
        header_top_row.addStretch()

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

        # Navigateur de Chat HTML / CSS riche
        self.chat_browser = QTextBrowser()
        self.chat_browser.setObjectName("chatBrowser")
        self.chat_browser.setOpenExternalLinks(True)
        chat_layout.addWidget(self.chat_browser)

        self.splitter.addWidget(chat_container)

        # Proportions initiales : 340px sidebar, reste pour le chat
        self.splitter.setSizes([340, 920])

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    # -----------------------------------------------------------------
    # Chargement & Rendu des Données
    # -----------------------------------------------------------------
    def _on_filter_changed(self):
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
                
                # Auto-dépliage des projets contenant des conversations
                p_item.setExpanded(True)
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

    # -----------------------------------------------------------------
    # Affichage du Chat avec Rendu HTML / CSS Riche
    # -----------------------------------------------------------------
    def display_chat(self, info: ConversationInfo):
        self.selected_conv = info
        title_text = info.title if info.title else "Conversation sans titre"
        self.chat_title.setText(title_text)

        proj_str = f"📁 {info.project}" if info.project else "📁 (aucun projet)"
        date_str = info.last_activity.strftime("%d/%m/%Y à %H:%M") if info.last_activity else "Date inconnue"
        self.chat_meta.setText(f"{proj_str}   •   {date_str}   •   ID: {info.conv_id}")
        self.btn_open_folder.setVisible(True)

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
            hr_col, time_col = "#e2e8f0", "#94a3b8"

        # Construction du document HTML moderne
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
                pre {{
                    background-color: {pre_bg};
                    border: 1px solid {pre_border};
                    border-radius: 6px;
                    padding: 10px;
                    overflow-x: auto;
                    font-family: 'Consolas', 'Fira Code', monospace;
                    font-size: 12px;
                    color: {pre_col};
                }}
                code {{
                    background-color: {code_bg};
                    padding: 2px 4px;
                    border-radius: 4px;
                    font-family: 'Consolas', monospace;
                    font-size: 12px;
                    color: {code_col};
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

            # Échappement et mise en forme légère du texte
            escaped = (
                raw_text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            # Retours à la ligne
            formatted = escaped.replace("\n", "<br>")

            if role == "user":
                html_parts.append(f"""
                <div class="msg-container">
                    <div class="user-box">
                        <div class="user-header">👤 Utilisateur {time_html}</div>
                        <div style="color: #ffffff;">{formatted}</div>
                    </div>
                </div>
                """)
            elif role == "model":
                html_parts.append(f"""
                <div class="msg-container">
                    <div class="model-box">
                        <div class="model-header">✨ Antigravity {time_html}</div>
                        <div>{formatted}</div>
                    </div>
                </div>
                """)

        html_parts.append("</body></html>")
        full_html = "".join(html_parts)
        self.chat_browser.setHtml(full_html)

    def _clear_chat(self):
        self.selected_conv = None
        self.chat_title.setText("Sélectionnez une conversation")
        self.chat_meta.setText("Choisissez un projet ou une conversation dans la barre latérale.")
        self.btn_open_folder.setVisible(False)
        self.chat_browser.setHtml("")

    def _open_current_session_folder(self):
        if not self.selected_conv:
            return
        brain_p = _find_brain_path(self.selected_conv.conv_id)
        if brain_p and brain_p.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(brain_p)))
        else:
            QMessageBox.information(self, "Dossier introuvable", "Le dossier de cette session n'a pas été trouvé sur le disque.")

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
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    active_theme = get_active_theme()
    app.setStyleSheet(DARK_QSS if active_theme == "dark" else LIGHT_QSS)

    window = AntigravityManagerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
