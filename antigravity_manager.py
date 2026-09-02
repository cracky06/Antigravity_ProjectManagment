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
    DEFAULT_PROJECTS_ROOT,
    DEFAULT_ANTIGRAVITY_ROOT,
)
from data_loader import (
    build_project_map,
    load_chat_messages,
    delete_project_cascade,
    delete_conversation,
    ConversationInfo,
    get_paths,
    _find_brain_path,
)

# =====================================================================
# STYLES CSS / QSS (Thème Moderne Antigravity)
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


# =====================================================================
# Boîte de Dialogue des Paramètres (PyQt6)
# =====================================================================
class SettingsDialog(QDialog):
    def __init__(self, parent: QMainWindow | None = None, on_save_callback=None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.setWindowTitle("Paramètres — Dossiers sources")
        self.setFixedSize(560, 260)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 1. Racine des Projets
        layout.addWidget(QLabel("Répertoire racine des projets (ex: E:\\Dev) :"))
        p_row = QHBoxLayout()
        self.proj_edit = QLineEdit(str(get_projects_root()))
        self.proj_edit.setStyleSheet("padding: 6px; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 5px; color: #fff;")
        p_row.addWidget(self.proj_edit)
        btn_browse_p = QPushButton("Parcourir…")
        btn_browse_p.clicked.connect(self._browse_proj)
        p_row.addWidget(btn_browse_p)
        layout.addLayout(p_row)

        # 2. Racine Antigravity
        layout.addWidget(QLabel("Dossier Antigravity IDE (ex: %USERPROFILE%\\.gemini\\antigravity-ide) :"))
        ag_row = QHBoxLayout()
        self.ag_edit = QLineEdit(str(get_antigravity_root()))
        self.ag_edit.setStyleSheet("padding: 6px; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 5px; color: #fff;")
        ag_row.addWidget(self.ag_edit)
        btn_browse_ag = QPushButton("Parcourir…")
        btn_browse_ag.clicked.connect(self._browse_ag)
        ag_row.addWidget(btn_browse_ag)
        layout.addLayout(ag_row)

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

    def _save(self):
        cfg = load_config()
        cfg["projects_root"] = self.proj_edit.text().strip()
        cfg["antigravity_root"] = self.ag_edit.text().strip()
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
        self.item_conv_map: dict[QTreeWidgetItem, ConversationInfo] = {}

        self._build_ui()
        self.reload_data()

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
    def reload_data(self):
        projects_root, _, _, _, _ = get_paths()
        self.status_bar.showMessage("Chargement des données Antigravity…")
        QApplication.processEvents()

        self.project_convs, self.all_convs = build_project_map()
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
        self.item_conv_map.clear()

        # Section 1 : Projets
        proj_header_item = QTreeWidgetItem(["PROJETS"])
        proj_header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        proj_header_item.setForeground(0, QColor("#a1a1aa"))
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
                p_item.setForeground(0, QColor("#f4f4f5"))
                for c_info in convs:
                    display_title = c_info.title if c_info.title else c_info.conv_id[:12]
                    if len(display_title) > 38:
                        display_title = display_title[:36] + "…"
                    
                    time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
                    c_item = QTreeWidgetItem([f"💬  {display_title}{time_suffix}"])
                    c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
                    p_item.addChild(c_item)
                    self.item_conv_map[c_item] = c_info
                
                # Auto-dépliage des projets contenant des conversations
                p_item.setExpanded(True)
            else:
                p_item.setForeground(0, QColor("#71717a"))

            self.tree.addTopLevelItem(p_item)

        # Section 2 : Conversations Récentes
        conv_header_item = QTreeWidgetItem(["CONVERSATIONS RÉCENTES"])
        conv_header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        conv_header_item.setForeground(0, QColor("#a1a1aa"))
        f2 = conv_header_item.font(0)
        f2.setBold(True)
        conv_header_item.setFont(0, f2)
        self.tree.addTopLevelItem(conv_header_item)

        for c_info in self.all_convs[:40]:
            display_title = c_info.title if c_info.title else c_info.conv_id[:12]
            if len(display_title) > 38:
                display_title = display_title[:36] + "…"
            time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
            c_item = QTreeWidgetItem([f"💬  {display_title}{time_suffix}"])
            c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
            self.tree.addTopLevelItem(c_item)
            self.item_conv_map[c_item] = c_info

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

        if not messages:
            html = """
            <div style="text-align: center; margin-top: 60px; color: #71717a; font-family: sans-serif;">
                <p style="font-size: 24px;">ℹ️</p>
                <p style="font-size: 14px; font-weight: bold; color: #a1a1aa;">Aucun message textuel dans les journaux.</p>
                <p style="font-size: 12px;">Cette session correspond probablement à une sous-tâche technique (subagent)<br>ou ses journaux ont été archivés.</p>
            </div>
            """
            self.chat_browser.setHtml(html)
            return

        # Construction du document HTML moderne
        html_parts = [
            """<!DOCTYPE html>
            <html>
            <head>
            <style>
                body {
                    background-color: #18181b;
                    color: #e4e4e7;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    font-size: 13px;
                    line-height: 1.6;
                    margin: 0;
                    padding: 10px;
                }
                .msg-container {
                    margin-bottom: 24px;
                }
                .user-box {
                    background-color: #27272a;
                    border: 1px solid #3f3f46;
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin-bottom: 12px;
                }
                .user-header {
                    font-weight: bold;
                    color: #60a5fa;
                    font-size: 12px;
                    margin-bottom: 6px;
                    display: flex;
                    justify-content: space-between;
                }
                .model-box {
                    background-color: #18181b;
                    border-left: 3px solid #8b5cf6;
                    padding: 4px 16px;
                    margin-bottom: 16px;
                }
                .model-header {
                    font-weight: bold;
                    color: #a78bfa;
                    font-size: 12px;
                    margin-bottom: 6px;
                }
                .time-tag {
                    color: #71717a;
                    font-weight: normal;
                    font-size: 11px;
                    float: right;
                }
                pre {
                    background-color: #121215;
                    border: 1px solid #27272a;
                    border-radius: 6px;
                    padding: 10px;
                    overflow-x: auto;
                    font-family: 'Consolas', 'Fira Code', monospace;
                    font-size: 12px;
                    color: #38bdf8;
                }
                code {
                    background-color: #27272a;
                    padding: 2px 4px;
                    border-radius: 4px;
                    font-family: 'Consolas', monospace;
                    font-size: 12px;
                    color: #38bdf8;
                }
                hr {
                    border: 0;
                    height: 1px;
                    background-color: #27272a;
                    margin: 20px 0;
                }
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

            menu.addSeparator()
            act_del_conv = menu.addAction("🗑️ Supprimer cette conversation")
            act_del_conv.triggered.connect(lambda: self._delete_single_conv(c_info))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

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
    app.setStyleSheet(DARK_QSS)

    window = AntigravityManagerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
