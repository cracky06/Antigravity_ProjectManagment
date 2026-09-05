"""antigravity_manager.py — Interface PyQt6 Haute Performance pour Antigravity Manager.

Fournit une exploration ultra-fluide (C++ 60 FPS), une arborescence native (QTreeWidget),
un rendu HTML/CSS riche pour le chat (QTextBrowser), et la gestion complète des projets.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QSize, QUrl, QTimer, QObject, QRunnable, QThreadPool, QByteArray, pyqtSignal as _Signal
from PyQt6.QtGui import QIcon, QFont, QColor, QDesktopServices, QAction, QKeySequence, QShortcut, QTextCursor, QPixmap
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
    get_ui_state,
    save_ui_state,
    DEFAULT_PROJECTS_ROOT,
    DEFAULT_ANTIGRAVITY_ROOT,
    DEFAULT_CLAUDE_ROOT,
)
from data_loader import (
    build_project_map,
    load_chat_messages,
    delete_project_cascade,
    delete_conversation,
    move_conversation,
    export_conversation_to_project,
    export_conversation_to_path,
    export_project_conversations,
    archive_project,
    default_export_filename,
    conversation_has_dialogue,
    derive_conv_label,
    ConversationInfo,
    get_paths,
    _find_brain_path,
)
import search_index
from claude_code_loader import (
    build_claude_project_map,
    load_claude_messages,
    default_claude_export_filename,
    export_claude_conversation_to_project,
    export_claude_conversation_to_path,
    export_claude_project_conversations,
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
    padding: 3px 4px;
    border-radius: 5px;
    margin: 0px 4px;
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
QLineEdit#searchInput[queryError="true"] {
    border-color: #ef4444;
}
QPushButton#searchModeBtn {
    background-color: #27272a;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    color: #a1a1aa;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    padding: 4px 0;
}
QPushButton#searchModeBtn:hover {
    border-color: #52525b;
}
QPushButton#searchModeBtn:checked {
    background-color: #1d4ed8;
    border-color: #3b82f6;
    color: #ffffff;
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
    padding: 3px 4px;
    border-radius: 5px;
    margin: 0px 4px;
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
QLineEdit#searchInput[queryError="true"] {
    border-color: #dc2626;
}
QPushButton#searchModeBtn {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    color: #64748b;
    font-family: 'Consolas', monospace;
    font-size: 11px;
    padding: 4px 0;
}
QPushButton#searchModeBtn:hover {
    border-color: #94a3b8;
}
QPushButton#searchModeBtn:checked {
    background-color: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
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
# Recherche globale asynchrone (thread pool)
# =====================================================================
class _SearchSignals(QObject):
    """Signaux d'un _SearchRunnable (QRunnable ne peut pas hériter de QObject)."""

    finished = _Signal(int, set)     # (generation, set[conv_id])
    failed = _Signal(int, str)       # (generation, message d'erreur)


class _SearchRunnable(QRunnable):
    """Exécute une recherche dans l'index sur un thread du pool.

    `generation` identifie la requête ; la fenêtre ignore tout résultat dont la
    génération n'est plus la dernière (frappe plus récente).
    """

    def __init__(
        self,
        generation: int,
        query: str,
        mode: str,
        scope_ids: set[str] | None,
        index_ready: bool,
    ):
        super().__init__()
        self.signals = _SearchSignals()
        self._generation = generation
        self._query = query
        self._mode = mode
        self._scope_ids = scope_ids
        self._index_ready = index_ready

    def run(self) -> None:  # type: ignore[override]
        try:
            if self._index_ready:
                found = search_index.search(
                    self._query, mode=self._mode, conv_ids=self._scope_ids
                )
            else:
                # Repli : l'index n'est pas encore utilisable, on parse à la volée
                # (uniquement le mode « contient » et « regex » — « mots » exige
                # l'index FTS).
                found = _fallback_search(self._query, self._mode, self._scope_ids)
        except re.error as exc:
            self.signals.failed.emit(self._generation, f"Regex invalide : {exc}")
            return
        except Exception as exc:  # pragma: no cover - garde-fou
            self.signals.failed.emit(self._generation, f"Échec de la recherche : {exc}")
            return
        finally:
            search_index.close_thread_connection()
        self.signals.finished.emit(self._generation, found)


def _fallback_search(query: str, mode: str, scope_ids: set[str] | None) -> set[str]:
    """Recherche sans index : itère les conversations et parse leurs transcripts.

    Utilisé tant que l'index n'est pas prêt/valide. Le mode « mots » retombe
    sur « contient ».
    """
    from data_loader import load_chat_messages as _load

    ids = scope_ids
    if ids is None:
        return set()  # portée inconnue hors index -> l'appelant fournit toujours scope_ids ici
    rx = re.compile(query, re.IGNORECASE | re.MULTILINE) if mode == "regex" else None
    needle = query.lower()
    out: set[str] = set()
    for cid in ids:
        body = "\n".join(m.get("text", "") for m in _load(cid) if m.get("text"))
        if rx is not None:
            if rx.search(body):
                out.add(cid)
        elif needle in body.lower():
            out.add(cid)
    return out


class _ClaudeSearchRunnable(QRunnable):
    """Équivalent de `_SearchRunnable` pour la source Claude Code / Desktop
    (v2.5) — module d'index séparé (`claude_search_index`), jamais mélangé
    avec la recherche Antigravity. Classe distincte plutôt que généraliser
    `_SearchRunnable` : évite tout risque de régression sur la recherche
    Antigravity existante en la laissant intacte."""

    def __init__(self, generation: int, query: str, mode: str, scope, index_ready: bool):
        """`scope` : set[str] (ids) si `index_ready`, sinon dict {id: ClaudeConv}
        (le repli sans index a besoin du .path de chaque session)."""
        super().__init__()
        self.signals = _SearchSignals()
        self._generation = generation
        self._query = query
        self._mode = mode
        self._scope_ids = scope
        self._index_ready = index_ready

    def run(self) -> None:  # type: ignore[override]
        import claude_search_index

        try:
            if self._index_ready:
                found = claude_search_index.search(
                    self._query, mode=self._mode, conv_ids=self._scope_ids
                )
            else:
                found = _fallback_claude_search(self._query, self._mode, self._scope_ids)
        except re.error as exc:
            self.signals.failed.emit(self._generation, f"Regex invalide : {exc}")
            return
        except Exception as exc:  # pragma: no cover - garde-fou
            self.signals.failed.emit(self._generation, f"Échec de la recherche : {exc}")
            return
        finally:
            claude_search_index.close_thread_connection()
        self.signals.finished.emit(self._generation, found)


def _fallback_claude_search(query: str, mode: str, scope: dict | None) -> set[str]:
    """Recherche sans index pour la source Claude Code : `scope` est un
    mapping {conv_id: ClaudeConv} (il faut le `.path` de chaque session, pas
    juste son id, pour relire le transcript)."""
    if not scope:
        return set()
    rx = re.compile(query, re.IGNORECASE | re.MULTILINE) if mode == "regex" else None
    needle = query.lower()
    out: set[str] = set()
    for cid, conv in scope.items():
        body = "\n".join(m.get("text", "") for m in load_claude_messages(conv.path) if m.get("text"))
        if rx is not None:
            if rx.search(body):
                out.add(cid)
        elif needle in body.lower():
            out.add(cid)
    return out


class _IndexSyncSignals(QObject):
    finished = _Signal(int, int, bool, str)  # (updated, deleted, ok, message)


class _IndexSyncRunnable(QRunnable):
    """Synchronise (ou reconstruit) l'index en tâche de fond au démarrage."""

    def __init__(self, convs: list, rebuild: bool = False):
        super().__init__()
        self.signals = _IndexSyncSignals()
        self._convs = convs
        self._rebuild = rebuild

    def run(self) -> None:  # type: ignore[override]
        try:
            fn = search_index.rebuild_index if self._rebuild else search_index.sync_index
            updated, deleted = fn(self._convs)
            status = search_index.check_status()
            self.signals.finished.emit(updated, deleted, status.ok, status.message)
        except Exception as exc:  # pragma: no cover - garde-fou
            self.signals.finished.emit(0, 0, False, f"Échec de l'indexation : {exc}")
        finally:
            search_index.close_thread_connection()


class _ClaudeIndexSyncRunnable(QRunnable):
    """Équivalent de `_IndexSyncRunnable` pour la source Claude Code (v2.5)."""

    def __init__(self, convs: list, rebuild: bool = False):
        super().__init__()
        self.signals = _IndexSyncSignals()
        self._convs = convs
        self._rebuild = rebuild

    def run(self) -> None:  # type: ignore[override]
        import claude_search_index

        try:
            fn = claude_search_index.rebuild_index if self._rebuild else claude_search_index.sync_index
            updated, deleted = fn(self._convs)
            status = claude_search_index.check_status()
            self.signals.finished.emit(updated, deleted, status.ok, status.message)
        except Exception as exc:  # pragma: no cover - garde-fou
            self.signals.finished.emit(0, 0, False, f"Échec de l'indexation : {exc}")
        finally:
            claude_search_index.close_thread_connection()


class _ClaudeTouchIndexRunnable(QRunnable):
    """Indexe UNE conversation Claude Code au fil de l'eau (consultation)."""

    def __init__(self, conv):
        super().__init__()
        self._conv = conv

    def run(self) -> None:  # type: ignore[override]
        import claude_search_index

        try:
            claude_search_index.touch_conversation(self._conv)
        except Exception:  # pragma: no cover - ne doit jamais gêner l'affichage
            pass
        finally:
            claude_search_index.close_thread_connection()


class _TouchIndexRunnable(QRunnable):
    """Indexe UNE conversation au fil de l'eau (quand elle est consultée).

    Silencieux : pas de signal, l'index se met à jour en arrière-plan et la
    prochaine recherche en profitera.
    """

    def __init__(self, conv_id: str, project: str, title: str):
        super().__init__()
        self._conv_id = conv_id
        self._project = project
        self._title = title

    def run(self) -> None:  # type: ignore[override]
        try:
            search_index.touch_conversation(
                self._conv_id, project=self._project, title=self._title
            )
        except Exception:
            pass
        finally:
            search_index.close_thread_connection()


# =====================================================================
# Boîte de Dialogue des Paramètres (PyQt6)
# =====================================================================
class SettingsDialog(QDialog):
    def __init__(self, parent: QMainWindow | None = None, on_save_callback=None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.setWindowTitle("Paramètres — Dossiers sources & Thème")
        self.setFixedSize(560, 430)
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

        # 3. Dossier Claude Code (source « Claude Code / Desktop »). On affiche
        # la valeur BRUTE de config.json (souvent %USERPROFILE%\.claude\projects)
        # plutôt que le chemin résolu, cohérent avec le champ Antigravity.
        layout.addWidget(QLabel("Dossier Claude Code (ex: %USERPROFILE%\\.claude\\projects) :"))
        cc_row = QHBoxLayout()
        self.claude_edit = QLineEdit(load_config().get("claude_root", DEFAULT_CLAUDE_ROOT))
        self.claude_edit.setStyleSheet(input_style)
        cc_row.addWidget(self.claude_edit)
        btn_browse_cc = QPushButton("Parcourir…")
        btn_browse_cc.clicked.connect(self._browse_claude)
        cc_row.addWidget(btn_browse_cc)
        layout.addLayout(cc_row)

        # 4. Thème de l'interface
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

        # 4. Index de recherche plein-texte
        idx_row = QHBoxLayout()
        try:
            _st = search_index.check_status()
            _idx_txt = _st.message
        except Exception as exc:  # pragma: no cover
            _idx_txt = f"état inconnu ({exc})"
        self._idx_status_label = QLabel(f"Index de recherche : {_idx_txt}")
        self._idx_status_label.setStyleSheet(
            "color: #a1a1aa; font-size: 11px;" if is_dark else "color: #64748b; font-size: 11px;"
        )
        idx_row.addWidget(self._idx_status_label, 1)
        btn_reindex = QPushButton("Réindexer")
        btn_reindex.setToolTip("Reconstruire entièrement l'index de recherche plein-texte")
        btn_reindex.clicked.connect(self._trigger_reindex)
        idx_row.addWidget(btn_reindex)
        layout.addLayout(idx_row)

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

        btn_about = QPushButton("À propos")
        btn_about.setToolTip("À propos d'Antigravity Manager")
        btn_about.clicked.connect(self._open_about)
        btn_box.addWidget(btn_about)

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

    def _browse_claude(self):
        import os as _os

        start = _os.path.expandvars(self.claude_edit.text()) or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Sélectionner le dossier Claude Code", start)
        if d:
            self.claude_edit.setText(d)

    def _reset_defaults(self):
        self.proj_edit.setText(str(DEFAULT_PROJECTS_ROOT))
        self.ag_edit.setText(str(DEFAULT_ANTIGRAVITY_ROOT))
        self.claude_edit.setText(DEFAULT_CLAUDE_ROOT)
        self.theme_combo.setCurrentIndex(0)

    def _open_changelog(self):
        dlg = ChangelogDialog(self)
        dlg.show()

    def _open_about(self):
        AboutDialog(self).exec()

    def _trigger_reindex(self):
        """Demande à la fenêtre principale de reconstruire l'index."""
        parent = self.parent()
        if parent is not None and hasattr(parent, "rebuild_search_index"):
            parent.rebuild_search_index()
            self._idx_status_label.setText("Index de recherche : reconstruction lancée…")

    def _save(self):
        cfg = load_config()
        cfg["projects_root"] = self.proj_edit.text().strip()
        cfg["antigravity_root"] = self.ag_edit.text().strip()
        cfg["claude_root"] = self.claude_edit.text().strip() or DEFAULT_CLAUDE_ROOT
        cfg["theme"] = self.theme_combo.currentData()
        save_config(cfg)
        self.accept()
        if self.on_save_callback:
            self.on_save_callback()


# =====================================================================
# Boîte de Dialogue : À propos
# =====================================================================
GITHUB_URL = "https://github.com/cracky06/Antigravity_ProjectManagment"


class AboutDialog(QDialog):
    """Petite fenêtre « À propos » : illustration + version + lien GitHub."""

    def __init__(self, parent: QMainWindow | None = None):
        super().__init__(parent)
        self.setWindowTitle("À propos — Antigravity Manager")
        self.setModal(True)
        self.setFixedWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(12)

        pm = _get_splash_pixmap()
        if pm is not None:
            img = QLabel()
            img.setPixmap(pm.scaledToWidth(560, Qt.TransformationMode.SmoothTransformation))
            img.setScaledContents(False)
            layout.addWidget(img)

        version = get_app_version()
        txt = QLabel(
            f"<div style='text-align:center;'>"
            f"<h2 style='margin:4px 0;'>Antigravity Manager</h2>"
            f"<p style='margin:2px 0; color:#64748b;'>Version {version}</p>"
            f"<p style='margin:8px 0;'>Exploration, organisation et export des "
            f"conversations Google&nbsp;Antigravity.</p>"
            f"<p style='margin:8px 0;'>"
            f"<a href='{GITHUB_URL}'>{GITHUB_URL}</a></p>"
            f"<p style='margin:8px 0; color:#94a3b8; font-size:11px;'>"
            f"Développé avec l'assistance de Claude&nbsp;(Anthropic).</p>"
            f"</div>"
        )
        txt.setOpenExternalLinks(True)
        txt.setWordWrap(True)
        txt.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(txt)

        row = QHBoxLayout()
        row.addStretch()
        btn_gh = QPushButton("🌐 Ouvrir GitHub")
        btn_gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        row.addWidget(btn_gh)
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        row.addStretch()
        layout.addLayout(row)


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



def _asset_base_dirs() -> list[Path]:
    """Emplacements possibles du dossier assets/ (dev, --onedir, --onefile)."""
    dirs = [
        Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent,
        Path(__file__).parent,
    ]
    if hasattr(sys, "_MEIPASS"):
        dirs.insert(0, Path(getattr(sys, "_MEIPASS")))
    return dirs


def _find_asset(*names: str) -> Path | None:
    """Premier fichier existant parmi `names`, cherché dans les dossiers assets."""
    for base in _asset_base_dirs():
        for name in names:
            p = base / name
            if p.is_file():
                return p
    return None


def _get_app_icon() -> QIcon:
    """Retourne l'icône officielle de l'application depuis assets/."""
    p = _find_asset("assets/icon.png", "assets/icon.ico", "icon.png", "icon.ico")
    return QIcon(str(p)) if p else QIcon()


def _get_splash_pixmap():
    """Charge l'image d'accueil (assets/splash.jpg) si présente ; None sinon."""
    p = _find_asset("assets/splash.jpg", "assets/splash.png", "splash.jpg")
    if not p:
        return None
    pm = QPixmap(str(p))
    return pm if not pm.isNull() else None


def _antigravity_source_icon(dark: bool) -> QIcon:
    """Logo Antigravity (le même « A »/montagne, tracé sombre ou blanc selon
    le thème pour rester lisible sur le fond du sélecteur)."""
    name = "antigravity_white.svg" if dark else "antigravity_black.svg"
    p = _find_asset(f"assets/{name}", name)
    return QIcon(str(p)) if p else QIcon()


def _claude_source_icon() -> QIcon:
    """Icône Claude (Claude Desktop `assets/claude.png`)."""
    p = _find_asset("assets/claude.png", "claude.png")
    return QIcon(str(p)) if p else QIcon()


# =====================================================================
# Application Principale Antigravity Manager (PyQt6)
# =====================================================================
class AntigravityManagerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.version = get_app_version()
        self.setWindowTitle(f"Antigravity Manager v{self.version} — Project & Chat Management")
        self.setMinimumSize(850, 520)

        # Restauration de la géométrie de la fenêtre (sinon taille par défaut).
        self._ui_state = get_ui_state()
        geo_b64 = self._ui_state.get("geometry")
        restored = False
        if geo_b64:
            try:
                if self.restoreGeometry(QByteArray.fromBase64(geo_b64.encode("ascii"))):
                    restored = True
            except Exception:
                restored = False
        if not restored:
            self.resize(1260, 840)

        icon = _get_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        # Données
        self.project_convs: dict[str, list[ConversationInfo]] = {}
        self.all_convs: list[ConversationInfo] = []
        self.selected_conv: ConversationInfo | None = None

        # Source « Claude Code / Desktop » (v2.5, lecture seule) : arbre de
        # données parallèle, jamais mélangé avec celui d'Antigravity.
        self._active_source: str = "antigravity"   # "antigravity" | "claude_code"
        self.claude_project_map: dict = {}
        self.selected_claude_conv = None
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

        # Recherche locale (find bar) : positions de toutes les occurrences dans
        # le document courant + index de l'occurrence active.
        self._find_positions: list[int] = []
        self._find_current: int = -1

        # Timer debounce pour la recherche globale (400ms)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._do_search)

        # Recherche asynchrone : pool de threads + compteur de génération pour
        # ignorer les résultats périmés, + état de l'index plein-texte.
        self._thread_pool = QThreadPool.globalInstance()
        self._search_generation = 0
        self._index_ready = False
        self._index_syncing = False
        self._shutting_down = False
        # Index de recherche de la source Claude Code (v2.5) : état séparé,
        # jamais mélangé avec _index_ready (Antigravity).
        self._claude_index_ready = False
        self._claude_index_syncing = False
        # Références fortes aux runnables en vol (sinon leurs QObject de signaux
        # peuvent être collectés avant l'émission -> RuntimeError).
        self._active_runnables: set = set()

        self._apply_theme()
        self._build_ui()
        self.reload_data()  # déclenche aussi _kick_off_index_sync()

    def showEvent(self, event):
        super().showEvent(event)
        # Affichage automatique de la fenêtre de changelog (modeless) au 1er lancement d'une mise à jour
        last_seen = get_last_seen_version()
        if last_seen != self.version:
            set_last_seen_version(self.version)
            self.changelog_dialog = ChangelogDialog(self)
            self.changelog_dialog.show()

    def closeEvent(self, event):
        """Persiste l'état d'interface puis attend la fin des tâches de fond
        (un runnable qui émet un signal vers un widget détruit -> crash)."""
        self._persist_ui_state()
        self._shutting_down = True
        self._search_generation += 1  # invalide toute recherche en vol
        try:
            self._thread_pool.waitForDone(3000)
        except Exception:
            pass
        super().closeEvent(event)

    def _persist_ui_state(self):
        """Enregistre géométrie fenêtre, proportions du splitter et filtre projet."""
        try:
            state = {
                "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            }
            if hasattr(self, "splitter"):
                sizes = self.splitter.sizes()
                if len(sizes) == 2 and all(s > 0 for s in sizes):
                    state["splitter"] = list(sizes)
            if hasattr(self, "project_filter_combo"):
                data = self.project_filter_combo.currentData()
                if data:
                    state["project_filter"] = data
            save_ui_state(state)
        except Exception:
            pass  # la persistance ne doit jamais empêcher la fermeture

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

        # Champ de recherche globale (au-dessus du filtre projet) + toggles de mode
        search_row = QHBoxLayout()
        search_row.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("🔍  Rechercher dans les discussions…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self.search_input)

        # [.*] : mode expression régulière
        self.btn_mode_regex = QPushButton(".*")
        self.btn_mode_regex.setObjectName("searchModeBtn")
        self.btn_mode_regex.setCheckable(True)
        self.btn_mode_regex.setFixedWidth(30)
        self.btn_mode_regex.setToolTip("Recherche par expression régulière")
        self.btn_mode_regex.toggled.connect(self._on_search_mode_toggled)
        search_row.addWidget(self.btn_mode_regex)

        # [Ab] : mode « mots » (index FTS, tolérant aux accents / préfixes)
        self.btn_mode_words = QPushButton("Ab")
        self.btn_mode_words.setObjectName("searchModeBtn")
        self.btn_mode_words.setCheckable(True)
        self.btn_mode_words.setFixedWidth(30)
        self.btn_mode_words.setToolTip("Recherche par mots entiers (index plein-texte)")
        self.btn_mode_words.toggled.connect(self._on_search_mode_toggled)
        search_row.addWidget(self.btn_mode_words)

        sidebar_layout.addLayout(search_row)

        # Sélecteur de source de données (v2.5) : Antigravity ou Claude Code /
        # Claude Desktop (~/.claude/projects/*.jsonl, lecture seule pour l'instant
        # — cf. claude_code_loader.py). Change ce que _populate_tree affiche.
        is_dark = get_active_theme() == "dark"
        combo_style = (
            "padding: 5px 8px; background-color: #27272a; border: 1px solid #3f3f46; border-radius: 6px; color: #f4f4f5; font-size: 12px;"
            if is_dark
            else "padding: 5px 8px; background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; color: #0f172a; font-size: 12px;"
        )
        self.source_combo = QComboBox()
        self.source_combo.setObjectName("sourceCombo")
        self.source_combo.setStyleSheet(combo_style)
        self.source_combo.setIconSize(QSize(16, 16))
        _ag_icon = _antigravity_source_icon(is_dark)
        _cc_icon = _claude_source_icon()
        # Repli sur l'emoji si l'asset manque (build sans les svg/png).
        if _ag_icon.isNull():
            self.source_combo.addItem("🌀 Antigravity", "antigravity")
        else:
            self.source_combo.addItem(_ag_icon, "Antigravity", "antigravity")
        if _cc_icon.isNull():
            self.source_combo.addItem("✳️ Claude Code / Desktop", "claude_code")
        else:
            self.source_combo.addItem(_cc_icon, "Claude Code / Desktop", "claude_code")
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        sidebar_layout.addWidget(self.source_combo)

        # Filtre par projet
        self.project_filter_combo = QComboBox()
        self.project_filter_combo.setObjectName("projectFilterCombo")
        self.project_filter_combo.setStyleSheet(combo_style)
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

        # Toggles de mode de la find bar (autonomes vis-à-vis de la recherche
        # globale) : [.*] expression régulière, [Aa] respect de la casse.
        self.btn_find_regex = QPushButton(".*")
        self.btn_find_regex.setObjectName("searchModeBtn")
        self.btn_find_regex.setCheckable(True)
        self.btn_find_regex.setFixedWidth(28)
        self.btn_find_regex.setToolTip("Recherche par expression régulière")
        self.btn_find_regex.toggled.connect(lambda _=False: self._on_find_text_changed())
        find_bar_layout.addWidget(self.btn_find_regex)

        self.btn_find_case = QPushButton("Aa")
        self.btn_find_case.setObjectName("searchModeBtn")
        self.btn_find_case.setCheckable(True)
        self.btn_find_case.setFixedWidth(28)
        self.btn_find_case.setToolTip("Respecter la casse")
        self.btn_find_case.toggled.connect(lambda _=False: self._on_find_text_changed())
        find_bar_layout.addWidget(self.btn_find_case)

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
        self.chat_browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_browser.customContextMenuRequested.connect(self._on_chat_context_menu)
        chat_layout.addWidget(self.chat_browser)

        self.splitter.addWidget(chat_container)

        # Raccourcis clavier — stockés en attributs d'instance pour éviter le
        # garbage-collection Python des objets QShortcut.
        # Note : Échap dans la find bar est géré par _FindLineEdit (classe dédiée).
        self._shortcuts: list[QShortcut] = []

        def _add_shortcut(sequence: str, slot) -> None:
            sc = QShortcut(QKeySequence(sequence), self)
            sc.activated.connect(slot)
            self._shortcuts.append(sc)

        _add_shortcut("Ctrl+F", self._show_find_bar)          # find bar locale
        _add_shortcut("Ctrl+K", self._focus_global_search)    # recherche globale
        _add_shortcut("Ctrl+L", self._focus_global_search)    # alias
        _add_shortcut("F3", self._find_next)                  # occurrence suivante
        _add_shortcut("Shift+F3", self._find_prev)            # occurrence précédente
        _add_shortcut("Escape", self._on_escape)             # effacer recherche / fermer find bar

        # Proportions du splitter : restaurées si valides, sinon 340px sidebar.
        saved_sizes = self._ui_state.get("splitter")
        if (
            isinstance(saved_sizes, list)
            and len(saved_sizes) == 2
            and all(isinstance(s, int) and s > 0 for s in saved_sizes)
        ):
            self.splitter.setSizes(saved_sizes)
        else:
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

    def _on_source_changed(self):
        """Bascule entre la source Antigravity et Claude Code / Desktop (v2.5).

        Les deux arbres de données restent strictement séparés — on ne
        mélange jamais les conversations des deux sources. Le même
        `project_filter_combo` est réutilisé pour les deux (repeuplé à
        chaque bascule), pour une expérience de filtrage identique.
        """
        new_source = self.source_combo.currentData() or "antigravity"
        if new_source == self._active_source:
            return
        self._active_source = new_source
        self.selected_claude_conv = None
        self._clear_chat()

        if new_source == "claude_code":
            self.status_bar.showMessage("Chargement des conversations Claude Code / Desktop…")
            self.claude_project_map = build_claude_project_map()
            n_conv = sum(len(v) for v in self.claude_project_map.values())
            self.status_bar.showMessage(
                f"✳️ Claude Code / Desktop : {len(self.claude_project_map)} projet(s), {n_conv} conversation(s)",
                6000,
            )
            self._kick_off_claude_index_sync()

        self._refresh_project_filter_combo()
        self._populate_tree()
        # Une recherche en cours ne correspond plus à la source affichée.
        if hasattr(self, "search_input") and self.search_input.text().strip():
            self.search_input.clear()

    def _refresh_project_filter_combo(self, restore_saved: bool = False):
        """Repeuple `project_filter_combo` avec les projets de la source
        active. Antigravity : ALL / NONE (sans projet) / un par projet.
        Claude Code : ALL / un par projet (pas de notion « sans projet »,
        chaque session a toujours un `cwd`).

        `restore_saved` : au tout premier chargement Antigravity, reprend le
        dernier filtre enregistré dans `_ui_state` (aucune sélection courante
        à ce stade sinon)."""
        if not hasattr(self, "project_filter_combo"):
            return
        self.project_filter_combo.blockSignals(True)
        cur_data = self.project_filter_combo.currentData()
        if cur_data is None and restore_saved:
            cur_data = self._ui_state.get("project_filter")
        self.project_filter_combo.clear()

        if self._active_source == "claude_code":
            total_c = sum(len(v) for v in self.claude_project_map.values())
            self.project_filter_combo.addItem(
                f"📁 Tous les projets ({len(self.claude_project_map)} projs, {total_c} convs)", "ALL"
            )
            for p_name in sorted(self.claude_project_map.keys(), key=str.lower):
                c_count = len(self.claude_project_map[p_name])
                self.project_filter_combo.addItem(f"📁 {p_name} ({c_count})", p_name)
        else:
            total_c = len(self.all_convs)
            no_proj = [c for c in self.all_convs if not c.project]
            self.project_filter_combo.addItem(
                f"📁 Tous les projets ({len(self.project_convs)} projs, {total_c} convs)", "ALL"
            )
            if no_proj:
                self.project_filter_combo.addItem(f"⚠️ Sans projet ({len(no_proj)})", "NONE")
            for p_name in sorted(self.project_convs.keys(), key=str.lower):
                c_count = len(self.project_convs[p_name])
                self.project_filter_combo.addItem(f"📁 {p_name} ({c_count})", p_name)

        # Restaurer la sélection précédente si elle existe encore dans cette
        # source (sinon on retombe sur "Tous les projets").
        idx = 0
        if cur_data:
            for i in range(self.project_filter_combo.count()):
                if self.project_filter_combo.itemData(i) == cur_data:
                    idx = i
                    break
        self.project_filter_combo.setCurrentIndex(idx)
        self.project_filter_combo.blockSignals(False)

    def reload_data(self):
        self._apply_theme()

        # Le bouton 🔄 (et les actions de gestion Antigravity : suppression,
        # déplacement, import…) appellent reload_data() sans savoir quelle
        # source est active. Si Claude Code est la source affichée, on
        # rafraîchit CETTE source plutôt que d'écraser la vue avec des
        # données Antigravity qui ne correspondraient plus au sélecteur.
        if self._active_source == "claude_code":
            self.status_bar.showMessage("Actualisation Claude Code / Desktop…")
            self.claude_project_map = build_claude_project_map()
            self._refresh_project_filter_combo()
            self._populate_tree()
            n_conv = sum(len(v) for v in self.claude_project_map.values())
            self.status_bar.showMessage(
                f"✳️ Claude Code / Desktop : {len(self.claude_project_map)} projet(s), {n_conv} conversation(s)",
                6000,
            )
            return

        projects_root, _, _, _, _ = get_paths()
        self.status_bar.showMessage("Chargement des données Antigravity…")

        self.project_convs, self.all_convs = build_project_map()

        self._refresh_project_filter_combo(restore_saved=True)
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

        # Après un rechargement manuel, resynchroniser l'index en tâche de fond.
        if hasattr(self, "_thread_pool"):
            self._kick_off_index_sync()

    # -----------------------------------------------------------------
    # Index plein-texte : synchronisation & santé
    # -----------------------------------------------------------------
    def _kick_off_index_sync(self, rebuild: bool = False):
        """Lance (en tâche de fond) la synchro de l'index de recherche."""
        if self._index_syncing or not self.all_convs:
            return
        status = search_index.check_status()
        if status.corrupt and not rebuild:
            self.status_bar.showMessage(
                f"⚠️ {status.message} — reconstruction automatique de l'index…", 6000
            )
            rebuild = True

        self._index_syncing = True
        self._index_ready = status.ok and not status.corrupt
        runnable = _IndexSyncRunnable(list(self.all_convs), rebuild=rebuild)
        self._active_runnables.add(runnable)
        runnable.signals.finished.connect(self._on_index_sync_finished)
        runnable.signals.finished.connect(lambda *_: self._active_runnables.discard(runnable))
        self._thread_pool.start(runnable)

    def _on_index_sync_finished(self, updated: int, deleted: int, ok: bool, message: str):
        if self._shutting_down:
            return
        self._index_syncing = False
        self._index_ready = ok
        if ok:
            if updated or deleted:
                self.status_bar.showMessage(
                    f"✅ Index à jour ({updated} indexée(s), {deleted} retirée(s)). {message}",
                    5000,
                )
            # Si une recherche « mots » attend l'index, la relancer maintenant.
            if self.btn_mode_words.isChecked() and self.search_input.text().strip():
                self._do_search()
        else:
            self.status_bar.showMessage(
                f"⚠️ Index indisponible : {message} — recherche en mode dégradé.", 8000
            )

    def rebuild_search_index(self):
        """Action utilisateur : reconstruction complète de l'index."""
        if self._index_syncing:
            self.status_bar.showMessage("Indexation déjà en cours…", 3000)
            return
        search_index.drop_index()
        self._index_ready = False
        self.status_bar.showMessage("Reconstruction de l'index de recherche…", 4000)
        self._kick_off_index_sync(rebuild=True)

    # -----------------------------------------------------------------
    # Index plein-texte — source Claude Code / Desktop (v2.5)
    # -----------------------------------------------------------------
    def _kick_off_claude_index_sync(self, rebuild: bool = False):
        all_convs = [c for convs in self.claude_project_map.values() for c in convs]
        if self._claude_index_syncing or not all_convs:
            return
        import claude_search_index

        status = claude_search_index.check_status()
        if status.corrupt and not rebuild:
            self.status_bar.showMessage(
                f"⚠️ {status.message} — reconstruction automatique de l'index Claude Code…", 6000
            )
            rebuild = True

        self._claude_index_syncing = True
        self._claude_index_ready = status.ok and not status.corrupt
        runnable = _ClaudeIndexSyncRunnable(all_convs, rebuild=rebuild)
        self._active_runnables.add(runnable)
        runnable.signals.finished.connect(self._on_claude_index_sync_finished)
        runnable.signals.finished.connect(lambda *_: self._active_runnables.discard(runnable))
        self._thread_pool.start(runnable)

    def _on_claude_index_sync_finished(self, updated: int, deleted: int, ok: bool, message: str):
        if self._shutting_down:
            return
        self._claude_index_syncing = False
        self._claude_index_ready = ok
        if ok:
            if self.btn_mode_words.isChecked() and self.search_input.text().strip():
                self._do_search()
        else:
            self.status_bar.showMessage(
                f"⚠️ Index Claude Code indisponible : {message} — recherche en mode dégradé.", 8000
            )

    def _populate_tree(self):
        self.tree.clear()
        is_dark = get_active_theme() == "dark"
        header_color = QColor("#a1a1aa" if is_dark else "#64748b")
        active_color = QColor("#f4f4f5" if is_dark else "#0f172a")
        empty_color = QColor("#71717a" if is_dark else "#94a3b8")

        # Source Claude Code / Desktop (v2.5, lecture seule) : même principe
        # à 3 sections que la vue Antigravity (PROJETS / HORS PROJET /
        # RÉCENTES) quand le filtre est sur « Tous les projets », ou vue
        # projet unique quand un projet précis est sélectionné.
        if self._active_source == "claude_code":
            def _add_claude_project_item(proj_name: str, convs) -> QTreeWidgetItem:
                # NB : ne PAS appeler setExpanded ici — Qt l'ignore sur un item
                # pas encore rattaché à l'arbre. L'appelant le fait APRÈS
                # addTopLevelItem/addChild.
                p_item = QTreeWidgetItem([f"📁  {proj_name}  ({len(convs)})"])
                p_item.setData(0, Qt.ItemDataRole.UserRole, ("claude_project", proj_name, convs))
                p_item.setForeground(0, active_color if convs else empty_color)
                for c_info in convs:
                    _add_claude_conv_child(p_item, c_info)
                return p_item

            def _add_claude_conv_child(parent: QTreeWidgetItem, c_info, *, badge: bool = False):
                label = c_info.title or c_info.conv_id[:12]
                max_len = 34 if badge else 40
                if len(label) > max_len:
                    label = label[:max_len - 2] + "…"
                badge_txt = f"  •  [{c_info.project}]" if badge else ""
                origin = f"  •  [{c_info.origin_label}]" if c_info.origin_label and not badge else ""
                date_str = c_info.last_dt.strftime("%d/%m %H:%M") if c_info.last_dt else ""
                time_suffix = f"   {date_str}" if date_str else ""
                c_item = QTreeWidgetItem([f"💬  {label}{badge_txt}{origin}{time_suffix}"])
                c_item.setData(0, Qt.ItemDataRole.UserRole, ("claude_conv", c_info))
                parent.addChild(c_item)
                return c_item

            claude_filter = "ALL"
            if hasattr(self, "project_filter_combo") and self.project_filter_combo.count() > 0:
                claude_filter = self.project_filter_combo.currentData() or "ALL"

            if claude_filter != "ALL" and claude_filter in self.claude_project_map:
                # Vue projet unique — équivalent du CAS 2 Antigravity.
                convs = self.claude_project_map[claude_filter]
                header_item = QTreeWidgetItem([f"PROJET : {claude_filter} ({len(convs)} convs)"])
                header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                header_item.setForeground(0, header_color)
                f = header_item.font(0)
                f.setBold(True)
                header_item.setFont(0, f)
                self.tree.addTopLevelItem(header_item)
                header_item.setExpanded(True)
                p_item = _add_claude_project_item(claude_filter, convs)
                self.tree.addTopLevelItem(p_item)
                p_item.setExpanded(True)  # après insertion, sinon Qt ignore
                return

            # Aucune donnée : message explicite plutôt que 3 sections à (0).
            if not self.claude_project_map:
                from claude_code_loader import get_claude_projects_root

                root = get_claude_projects_root()
                exists = root.is_dir()
                msg = (
                    "Aucune conversation Claude Code trouvée dans ce dossier."
                    if exists
                    else "Dossier Claude Code introuvable."
                )
                it = QTreeWidgetItem([f"  ℹ️  {msg}"])
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                it.setForeground(0, header_color)
                self.tree.addTopLevelItem(it)
                hint = QTreeWidgetItem([
                    "      Installez l'extension VS Code ou l'app Claude Desktop,"
                    if not exists else
                    "      Lancez une session Claude Code dans un projet pour la voir ici."
                ])
                hint.setFlags(Qt.ItemFlag.ItemIsEnabled)
                hint.setForeground(0, empty_color)
                self.tree.addTopLevelItem(hint)
                if not exists:
                    hint2 = QTreeWidgetItem([
                        f"      ou changez le dossier dans Paramètres ⚙️ (actuel : {root})."
                    ])
                    hint2.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    hint2.setForeground(0, empty_color)
                    self.tree.addTopLevelItem(hint2)
                return

            # Vue « Tous les projets » — 3 sections comme côté Antigravity.
            def _make_section_header(label: str) -> QTreeWidgetItem:
                it = QTreeWidgetItem([label])
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                it.setForeground(0, header_color)
                fnt = it.font(0)
                fnt.setBold(True)
                it.setFont(0, fnt)
                self.tree.addTopLevelItem(it)
                return it

            all_claude_convs = [c for convs in self.claude_project_map.values() for c in convs]

            # --- Section 1 : PROJETS ---------------------------------
            proj_header_item = _make_section_header(f"PROJETS ({len(self.claude_project_map)})")
            for proj_name in sorted(self.claude_project_map.keys(), key=str.lower):
                convs = self.claude_project_map[proj_name]
                proj_header_item.addChild(_add_claude_project_item(proj_name, convs))
                # dossiers repliés par défaut en vue globale (état par défaut
                # d'un QTreeWidgetItem, rien à forcer)

            # --- Section 2 : CONVERSATIONS HORS PROJET ---------------
            # Cas rare (session « teleported-from » sans cwd local, cf.
            # claude_code_loader._decode_folder_name) — pas d'équivalent
            # « conversation_has_dialogue » nécessaire ici : ces sessions ne
            # sont déjà gardées par le scan que si elles ont un vrai message.
            no_root_convs = [c for c in all_claude_convs if c.project_root is None]
            orphan_header_item = _make_section_header(
                f"CONVERSATIONS HORS PROJET ({len(no_root_convs)})"
            )
            for c_info in no_root_convs:
                _add_claude_conv_child(orphan_header_item, c_info)

            # --- Section 3 : CONVERSATIONS RÉCENTES -------------------
            # Limitée à 40 -> le compteur reflète ce qui est réellement listé.
            recent_sorted = sorted(
                all_claude_convs,
                key=lambda c: c.last_dt or __import__("datetime").datetime.min,
                reverse=True,
            )[:40]
            recent_header_item = _make_section_header(f"CONVERSATIONS RÉCENTES ({len(recent_sorted)})")
            for c_info in recent_sorted:
                _add_claude_conv_child(recent_header_item, c_info, badge=True)

            proj_header_item.setExpanded(True)
            orphan_header_item.setExpanded(True)
            recent_header_item.setExpanded(False)
            return

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
                label = derive_conv_label(c_info.conv_id, c_info.title or "")
                if len(label) > 40:
                    label = label[:38] + "…"
                time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
                c_item = QTreeWidgetItem([f"💬  {label}  •  [⚠️ Sans projet]{time_suffix}"])
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

        # CAS 3 : "ALL" — vue d'ensemble en 3 sections.
        # Les TITRES de section sont au niveau 0 ; les dossiers 📁 et les
        # conversations 💬 sont leurs ENFANTS -> l'indentation native de l'arbre
        # décale visuellement tout ce qui n'est pas un titre.

        def _make_section_header(label: str) -> QTreeWidgetItem:
            it = QTreeWidgetItem([label])
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it.setForeground(0, header_color)
            fnt = it.font(0)
            fnt.setBold(True)
            it.setFont(0, fnt)
            self.tree.addTopLevelItem(it)
            return it

        def _add_conv_child(parent: QTreeWidgetItem, c_info, *, badge: bool = False):
            label = derive_conv_label(c_info.conv_id, c_info.title or "")
            max_len = 34 if badge else 44
            if len(label) > max_len:
                label = label[: max_len - 2] + "…"
            badge_txt = ""
            if badge:
                badge_txt = (
                    f"  •  [{c_info.project}]" if c_info.project else "  •  [⚠️ Sans projet]"
                )
            time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
            c_item = QTreeWidgetItem([f"💬  {label}{badge_txt}{time_suffix}"])
            c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
            parent.addChild(c_item)
            return c_item

        # --- Section 1 : PROJETS -------------------------------------------
        proj_header_item = _make_section_header(f"PROJETS ({len(self.project_convs)})")
        for proj_name in sorted(self.project_convs.keys(), key=str.lower):
            convs = self.project_convs[proj_name]
            count = len(convs)
            p_text = f"📁  {proj_name}" + (f"  ({count})" if count > 0 else "")
            p_item = QTreeWidgetItem([p_text])
            p_item.setData(0, Qt.ItemDataRole.UserRole, ("project", proj_name, convs))
            if count > 0:
                p_item.setForeground(0, active_color)
                for c_info in convs:
                    _add_conv_child(p_item, c_info)
                p_item.setExpanded(False)  # dossiers repliés par défaut en vue globale
            else:
                p_item.setForeground(0, empty_color)
            proj_header_item.addChild(p_item)

        # --- Section 2 : CONVERSATIONS HORS PROJET ------------------------
        # Seules les orphelines AYANT un vrai dialogue sont affichées : les
        # sessions techniques (sous-agents, exécutions d'outils sans transcript)
        # sont vides et sans intérêt ici.
        no_proj_convs = [c for c in self.all_convs if not c.project]
        with_dialogue = [c for c in no_proj_convs if conversation_has_dialogue(c.conv_id)]

        orphan_header_item = _make_section_header(
            f"CONVERSATIONS HORS PROJET ({len(with_dialogue)})"
        )
        for c_info in with_dialogue:
            _add_conv_child(orphan_header_item, c_info)

        # --- Section 3 : CONVERSATIONS RÉCENTES (repliée par défaut) -------
        # Limitée à 40 -> le compteur reflète ce qui est réellement listé,
        # pas le total de conversations toutes sources confondues.
        recent_convs = self.all_convs[:40]
        recent_header_item = _make_section_header(f"CONVERSATIONS RÉCENTES ({len(recent_convs)})")
        for c_info in recent_convs:
            _add_conv_child(recent_header_item, c_info, badge=True)

        proj_header_item.setExpanded(True)
        orphan_header_item.setExpanded(True)
        recent_header_item.setExpanded(False)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            # Titre de section (PROJETS / HORS PROJET / RÉCENTES) : clic = repli.
            if item.childCount() > 0:
                item.setExpanded(not item.isExpanded())
            return
        dtype = data[0]
        if dtype == "conv":
            c_info: ConversationInfo = data[1]
            self.display_chat(c_info)
        elif dtype == "claude_conv":
            self.display_claude_chat(data[1])
        elif dtype in ("project", "claude_project"):
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
        elif dtype == "claude_conv":
            c_info = data[1]
            if not self.selected_claude_conv or self.selected_claude_conv.conv_id != c_info.conv_id:
                self.display_claude_chat(c_info)

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

        # Indexation au fil de l'eau : garde l'index de recherche frais pour
        # cette conversation sans attendre la synchro groupée.
        if not self._shutting_down and self._index_ready and not self._index_syncing:
            r = _TouchIndexRunnable(
                info.conv_id, info.project or "", info.title or ""
            )
            self._thread_pool.start(r)

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
            self._set_chat_html(html)
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
            self._set_chat_html(html)
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
                    line-height: 1.45;
                    margin: 0;
                    padding: 10px;
                }}
                .msg-container {{
                    margin-bottom: 14px;
                }}
                .user-box {{
                    background-color: {user_bg};
                    border: 1px solid {user_border};
                    border-radius: 8px;
                    padding: 8px 14px;
                    margin-bottom: 8px;
                }}
                .user-header {{
                    font-weight: bold;
                    color: {user_title_col};
                    font-size: 12px;
                    line-height: 1.2;
                    margin: 0 0 1px 0;
                    display: flex;
                    justify-content: space-between;
                }}
                .model-box {{
                    background-color: {model_bg};
                    border-left: 3px solid {model_border};
                    padding: 2px 14px;
                    margin-bottom: 10px;
                }}
                .model-header {{
                    font-weight: bold;
                    color: {model_title_col};
                    font-size: 12px;
                    line-height: 1.2;
                    margin: 0 0 1px 0;
                }}
                .msg-body {{ line-height: 1.4; }}
                .time-tag {{
                    color: {time_col};
                    font-weight: normal;
                    font-size: 11px;
                    float: right;
                }}
                h1, h2, h3, h4 {{
                    margin-top: 10px;
                    margin-bottom: 4px;
                    color: {model_title_col};
                }}
                h1 {{ font-size: 16px; border-bottom: 1px solid {hr_col}; padding-bottom: 3px; }}
                h2 {{ font-size: 15px; border-bottom: 1px solid {hr_col}; padding-bottom: 2px; }}
                h3 {{ font-size: 14px; }}
                h4 {{ font-size: 13px; }}
                p {{ margin: 2px 0; }}
                ul, ol {{ margin: 2px 0; padding-left: 20px; }}
                li {{ margin-bottom: 1px; }}
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

            # QTextBrowser ne gère pas « .msg-body > :first-child » : on retire
            # nous-mêmes le <p> enveloppant d'un message d'un seul paragraphe
            # pour que le texte colle au header (« Utilisateur » / « Antigravity »).
            _stripped = formatted.strip()
            if (
                _stripped.startswith("<p>")
                and _stripped.endswith("</p>")
                and _stripped.count("<p>") == 1
            ):
                formatted = _stripped[3:-4]

            if role == "user":
                html_parts.append(f"""
                <div class="msg-container">
                    <div class="user-box">
                        <div class="user-header">👤 Utilisateur {time_html}</div>
                        <div class="msg-body" style="color: {user_text_col};">{formatted}</div>
                    </div>
                </div>
                """)
            elif role == "model":
                html_parts.append(f"""
                <div class="msg-container">
                    <div class="model-box">
                        <div class="model-header">✨ Antigravity {time_html}</div>
                        <div class="msg-body" style="color: {model_text_col};">{formatted}</div>
                    </div>
                </div>
                """)

        html_parts.append("</body></html>")
        full_html = "".join(html_parts)
        self._set_chat_html(full_html)
        # Pré-remplir la find bar si recherche globale active
        self._prefill_find_from_search()

    def display_claude_chat(self, conv):
        """Affiche une conversation Claude Code / Desktop (v2.5, lecture seule).

        Rendu volontairement plus simple que `display_chat` (pas d'historique
        de navigation, pas de mode source brut) — cf. portée v1 documentée
        dans claude_code_loader.py. L'indexation FTS (v2.5) est au fil de
        l'eau comme côté Antigravity : `_ClaudeTouchIndexRunnable`.
        """
        self.selected_claude_conv = conv
        self.chat_title.setText(conv.title or "Conversation sans titre")
        date_str = conv.last_dt.strftime("%d/%m/%Y à %H:%M") if conv.last_dt else "Date inconnue"
        origin = f" • {conv.origin_label}" if conv.origin_label else ""
        self.chat_meta.setText(f"📁 {conv.project}   •   {date_str}{origin}   •   ID: {conv.conv_id}")
        self.btn_open_folder.setVisible(False)
        self.btn_toggle_raw.setVisible(False)
        self.btn_find_toggle.setVisible(True)

        if not self._shutting_down and self._claude_index_ready and not self._claude_index_syncing:
            r = _ClaudeTouchIndexRunnable(conv)
            self._thread_pool.start(r)

        messages = load_claude_messages(conv.path)
        is_dark = get_active_theme() == "dark"

        if not messages:
            info_col = "#a1a1aa" if is_dark else "#475569"
            sub_col = "#71717a" if is_dark else "#64748b"
            self._set_chat_html(f"""
            <div style="text-align: center; margin-top: 60px; font-family: sans-serif;">
                <p style="font-size: 24px;">ℹ️</p>
                <p style="font-size: 14px; font-weight: bold; color: {info_col};">Aucun message textuel dans cette session.</p>
                <p style="font-size: 12px; color: {sub_col};">Session probablement technique (queue/bridge) sans dialogue.</p>
            </div>
            """)
            return

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

        html_parts = [f"""<!DOCTYPE html><html><head><style>
            body {{ background-color: {body_bg}; color: {body_col};
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    font-size: 13px; line-height: 1.45; margin: 0; padding: 10px; }}
            .msg-container {{ margin-bottom: 14px; }}
            .user-box {{ background-color: {user_bg}; border: 1px solid {user_border};
                         border-radius: 8px; padding: 8px 14px; margin-bottom: 8px; }}
            .user-header {{ font-weight: bold; color: {user_title_col}; font-size: 12px; margin: 0 0 1px 0; }}
            .model-box {{ background-color: {model_bg}; border-left: 3px solid {model_border};
                          padding: 2px 14px; margin-bottom: 10px; }}
            .model-header {{ font-weight: bold; color: {model_title_col}; font-size: 12px; margin: 0 0 1px 0; }}
            .msg-body {{ line-height: 1.4; }}
            .time-tag {{ color: {time_col}; font-weight: normal; font-size: 11px; float: right; }}
            h1, h2, h3, h4 {{ margin-top: 10px; margin-bottom: 4px; color: {model_title_col}; }}
            h1 {{ font-size: 16px; border-bottom: 1px solid {hr_col}; padding-bottom: 3px; }}
            h2 {{ font-size: 15px; border-bottom: 1px solid {hr_col}; padding-bottom: 2px; }}
            h3 {{ font-size: 14px; }} h4 {{ font-size: 13px; }}
            p {{ margin: 2px 0; }} ul, ol {{ margin: 2px 0; padding-left: 20px; }} li {{ margin-bottom: 1px; }}
            strong {{ font-weight: bold; }}
            blockquote {{ border-left: 3px solid {model_border}; margin: 6px 0; padding: 4px 10px; color: {time_col}; }}
            table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
            th, td {{ border: 1px solid {hr_col}; padding: 5px 8px; text-align: left; }}
            th {{ background-color: {pre_bg}; font-weight: bold; }}
            pre {{ background-color: {pre_bg}; border: 1px solid {pre_border}; border-radius: 6px;
                   padding: 10px; font-family: 'Consolas', 'Fira Code', monospace; font-size: 12px;
                   color: {pre_col}; white-space: pre-wrap; word-wrap: break-word; }}
            code {{ background-color: {code_bg}; padding: 2px 4px; border-radius: 4px;
                    font-family: 'Consolas', monospace; font-size: 12px; color: {code_col};
                    white-space: pre-wrap; word-wrap: break-word; }}
            a {{ color: {model_title_col}; word-wrap: break-word; }}
        </style></head><body>"""]

        for msg in messages:
            role = msg.get("role")
            raw_text = msg.get("text", "").strip()
            ts = msg.get("timestamp", "")
            time_html = f"<span class='time-tag'>{ts}</span>" if ts else ""

            def _escape_pre(text: str) -> str:
                escaped = (
                    text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                return escaped.replace("\n", "<br>")

            if markdown:
                try:
                    formatted = markdown.markdown(raw_text, extensions=["fenced_code", "tables", "nl2br"])
                except Exception:
                    formatted = _escape_pre(raw_text)
            else:
                formatted = _escape_pre(raw_text)

            _stripped = formatted.strip()
            if _stripped.startswith("<p>") and _stripped.endswith("</p>") and _stripped.count("<p>") == 1:
                formatted = _stripped[3:-4]

            if role == "user":
                html_parts.append(f"""
                <div class="msg-container"><div class="user-box">
                    <div class="user-header">👤 Utilisateur {time_html}</div>
                    <div class="msg-body" style="color: {user_text_col};">{formatted}</div>
                </div></div>""")
            elif role == "assistant":
                html_parts.append(f"""
                <div class="msg-container"><div class="model-box">
                    <div class="model-header">✳️ Claude {time_html}</div>
                    <div class="msg-body" style="color: {model_text_col};">{formatted}</div>
                </div></div>""")

        html_parts.append("</body></html>")
        self._set_chat_html("".join(html_parts))
        self._prefill_find_from_search()

    def _set_chat_html(self, html: str):
        """Charge le HTML dans le navigateur et remet le curseur au début SANS
        sélection : sinon QTextBrowser ouvre le document avec le premier bloc
        sélectionné (surlignage bleu parasite)."""
        self.chat_browser.setHtml(html)
        cur = self.chat_browser.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.Start)
        cur.clearSelection()
        self.chat_browser.setTextCursor(cur)
        self.chat_browser.verticalScrollBar().setValue(0)

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

    def _on_chat_context_menu(self, pos):
        """Menu contextuel dans la vue discussion.

        Sur un lien fichier : actions « copier le chemin » / « ouvrir le
        dossier parent » / « révéler dans l'Explorateur ». Ailleurs : le menu
        standard de QTextBrowser (copier la sélection, tout sélectionner).
        """
        href = self.chat_browser.anchorAt(pos)
        menu = self.chat_browser.createStandardContextMenu(pos)

        if href:
            url = QUrl(href)
            local: Path | None = None
            if url.isLocalFile() or url.scheme().lower() == "file":
                local = Path(url.toLocalFile())

            menu.addSeparator()
            act_copy = menu.addAction("📋 Copier le lien")
            act_copy.triggered.connect(
                lambda: QApplication.clipboard().setText(
                    str(local) if local is not None else href
                )
            )
            if local is not None:
                act_open_parent = menu.addAction("📂 Ouvrir le dossier parent")
                act_open_parent.triggered.connect(
                    lambda: self._open_parent_folder(local)
                )
                if sys.platform == "win32":
                    act_reveal = menu.addAction("🔎 Révéler dans l'Explorateur")
                    act_reveal.triggered.connect(lambda: self._reveal_in_explorer(local))

        menu.exec(self.chat_browser.viewport().mapToGlobal(pos))

    def _open_parent_folder(self, path: Path):
        parent = path.parent
        if parent.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent)))
        else:
            self.status_bar.showMessage(f"⚠️ Dossier introuvable : {parent}", 5000)

    def _reveal_in_explorer(self, path: Path):
        """Ouvre l'Explorateur avec le fichier pré-sélectionné (Windows)."""
        import subprocess
        try:
            if path.exists():
                subprocess.run(["explorer", "/select,", str(path)], check=False)
            else:
                self._open_parent_folder(path)
        except Exception as exc:
            self.status_bar.showMessage(f"⚠️ {exc}", 5000)

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

        self._set_chat_html(html)
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

    def _current_search_mode(self) -> str:
        """Mode actif d'après les toggles : 'regex' > 'words' > 'substring'."""
        if self.btn_mode_regex.isChecked():
            return "regex"
        if self.btn_mode_words.isChecked():
            return "words"
        return "substring"

    def _on_search_mode_toggled(self, _checked: bool = False):
        """Un toggle de mode a changé : les deux sont mutuellement exclusifs,
        puis on relance la recherche courante."""
        sender = self.sender()
        if sender is self.btn_mode_regex and self.btn_mode_regex.isChecked():
            self.btn_mode_words.setChecked(False)
        elif sender is self.btn_mode_words and self.btn_mode_words.isChecked():
            self.btn_mode_regex.setChecked(False)

        # « mots » exige l'index FTS ; si indisponible on prévient, sans bloquer.
        if self.btn_mode_words.isChecked() and not self._index_ready:
            self.status_bar.showMessage(
                "Mode « mots » : l'index plein-texte n'est pas encore prêt, "
                "repli temporaire sur « contient ».", 5000
            )
        if self.search_input.text().strip():
            self._search_timer.start(200)

    def _do_search(self):
        """Lance une recherche asynchrone dans le périmètre du filtre projet actif."""
        query = self.search_input.text().strip()
        if not query:
            return

        mode = self._current_search_mode()
        is_claude = self._active_source == "claude_code"
        index_ready = self._claude_index_ready if is_claude else self._index_ready
        # Repli si « mots » demandé sans index : on rétrograde en « contient ».
        effective_mode = mode
        if mode == "words" and not index_ready:
            effective_mode = "substring"

        scope = self._get_claude_search_scope() if is_claude else self._get_search_scope()
        self._search_scope_by_id = {c.conv_id: c for c in scope}
        scope_ids = set(self._search_scope_by_id.keys())

        self._search_generation += 1
        gen = self._search_generation
        self._set_query_error(False)
        self.status_bar.showMessage(
            f"🔍 Recherche ({self._mode_label(mode)}) de « {query} » "
            f"dans {len(scope_ids)} conversation(s)…"
        )

        if is_claude:
            # Le repli sans index a besoin du .path de chaque session, pas
            # seulement de son id -> on passe le mapping complet.
            runnable = _ClaudeSearchRunnable(
                gen, query, effective_mode,
                scope_ids if index_ready else dict(self._search_scope_by_id),
                index_ready,
            )
        else:
            runnable = _SearchRunnable(gen, query, effective_mode, scope_ids, index_ready)
        self._active_runnables.add(runnable)
        runnable.signals.finished.connect(self._on_search_finished)
        runnable.signals.failed.connect(self._on_search_failed)
        runnable.signals.finished.connect(lambda *_: self._active_runnables.discard(runnable))
        runnable.signals.failed.connect(lambda *_: self._active_runnables.discard(runnable))
        self._thread_pool.start(runnable)

    @staticmethod
    def _mode_label(mode: str) -> str:
        return {"regex": "regex", "words": "mots", "substring": "contient"}.get(mode, mode)

    def _set_query_error(self, is_error: bool):
        """Bordure rouge du champ de recherche (motif regex invalide)."""
        self.search_input.setProperty("queryError", "true" if is_error else "false")
        self.search_input.style().unpolish(self.search_input)
        self.search_input.style().polish(self.search_input)

    def _on_search_failed(self, generation: int, message: str):
        if self._shutting_down or generation != self._search_generation:
            return
        self._set_query_error("regex" in message.lower())
        self.status_bar.showMessage(f"⚠️ {message}", 6000)

    def _on_search_finished(self, generation: int, found_ids: set):
        if self._shutting_down or generation != self._search_generation:
            return  # résultat périmé (frappe plus récente) ou fermeture en cours

        scope_map = getattr(self, "_search_scope_by_id", {})
        results: dict[str, list[ConversationInfo]] = {}
        for cid in found_ids:
            c_info = scope_map.get(cid)
            if c_info is None:
                continue
            key = c_info.project or "⚠️ Sans projet"
            results.setdefault(key, []).append(c_info)

        query = self.search_input.text().strip()
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

    def _get_claude_search_scope(self) -> list:
        """Équivalent de `_get_search_scope` pour la source Claude Code."""
        all_convs = [c for convs in self.claude_project_map.values() for c in convs]
        if not hasattr(self, "project_filter_combo"):
            return all_convs
        filter_val = self.project_filter_combo.currentData() or "ALL"
        if filter_val == "ALL":
            return all_convs
        return self.claude_project_map.get(filter_val, all_convs)

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

        is_claude = self._active_source == "claude_code"
        conv_dtype = "claude_conv" if is_claude else "conv"
        for proj_name, convs in sorted(results.items(), key=lambda x: x[0].lower()):
            p_item = QTreeWidgetItem([f"📁  {proj_name}  ({len(convs)})"])
            p_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            p_item.setForeground(0, active_color)

            for c_info in convs:
                display_title = c_info.title if c_info.title else c_info.conv_id[:12]
                if len(display_title) > 38:
                    display_title = display_title[:36] + "…"
                # ClaudeConv n'a pas de temps relatif ; on affiche sa date
                # comme dans l'arbre normal de cette source.
                if is_claude:
                    time_suffix = (
                        f"   {c_info.last_dt.strftime('%d/%m %H:%M')}" if c_info.last_dt else ""
                    )
                else:
                    time_suffix = f"   {c_info.rel_time}" if c_info.rel_time else ""
                c_item = QTreeWidgetItem([f"💬  {display_title}{time_suffix}"])
                c_item.setData(0, Qt.ItemDataRole.UserRole, (conv_dtype, c_info))
                p_item.addChild(c_item)

            p_item.setExpanded(True)
            self.tree.addTopLevelItem(p_item)

        header_item.setExpanded(True)

    # -----------------------------------------------------------------
    # Recherche Locale dans la Discussion (Find Bar)
    # -----------------------------------------------------------------
    def _prefill_find_from_search(self):
        """Pré-remplit et affiche la find bar si une recherche globale est active.

        Le mode (regex / casse) de la find bar s'aligne sur celui de la
        recherche globale au moment du pré-remplissage — l'utilisateur reste
        libre de le changer ensuite via les toggles de la find bar.
        """
        if not hasattr(self, "search_input"):
            return
        q = self.search_input.text().strip()
        if not q:
            return
        self.btn_find_regex.setChecked(self.btn_mode_regex.isChecked())
        # « mots » (global) n'a pas d'équivalent local -> on n'active pas regex.
        self._show_find_bar(prefill=q)

    def _show_find_bar(self, prefill: str = ""):
        """Affiche la barre de recherche locale. Pré-remplit optionnellement le champ.

        Fonctionne pour les deux sources : `_recompute_find_matches` opère
        directement sur `self.chat_browser.document()`, sans distinction —
        seul un contenu affiché (Antigravity OU Claude Code) est requis."""
        if not self.selected_conv and not self.selected_claude_conv:
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

    def _focus_global_search(self):
        """Ctrl+K / Ctrl+L : place le focus dans le champ de recherche globale."""
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _on_escape(self):
        """Échap : ferme la find bar si visible, sinon efface la recherche globale.

        Échap à l'intérieur du champ de la find bar est déjà intercepté par
        _FindLineEdit ; ce raccourci couvre le cas où le focus est ailleurs
        (arbre, navigateur de chat).
        """
        # isVisibleTo(self) reflète l'intention (setVisible) même si la fenêtre
        # n'est pas encore montrée — plus fiable que isVisible() ici.
        if self.find_bar.isVisibleTo(self):
            self._hide_find_bar()
        elif self.search_input.text():
            self.search_input.clear()
            self.tree.setFocus()

    def _hide_find_bar(self):
        """Masque la barre de recherche locale et remet le focus sur le navigateur."""
        self.find_bar.setVisible(False)
        self.find_result_label.setText("")
        self.chat_browser.setExtraSelections([])
        self._find_positions = []
        self._find_current = -1
        self._set_find_error(False)
        self.chat_browser.setFocus()

    def _on_find_text_changed(self):
        """Recompte les occurrences quand le texte OU un mode change."""
        self._recompute_find_matches()
        if self._find_positions:
            self._goto_find_match(0)
        else:
            self._update_find_label()

    def _do_find_from_start(self):
        """Point d'entrée quand la find bar est (ré)affichée : recompte et va au 1er."""
        self._on_find_text_changed()

    # -- Recherche locale : moteur de comptage & surlignage --------------
    #
    # On parcourt le QTextDocument BLOC PAR BLOC :
    #   - le texte d'un bloc (QTextBlock.text()) est une ligne logique sans
    #     séparateur ; `re` de Python y cherche avec un `.` qui ne franchit
    #     jamais une frontière de ligne (contrairement à QRegularExpression +
    #     document().find(), où `.` traversait les paragraphes et un `.*?`
    #     débordait sur plusieurs lignes visibles) ;
    #   - la position document d'une occurrence = block.position() + offset
    #     dans le texte du bloc — mapping exact, pas de décalage plain/doc.
    def _compile_find_pattern(self):
        """Compile le motif de recherche courant.

        Retourne un `re.Pattern`, ou None si le champ est vide ou le motif
        regex invalide (dans ce dernier cas, pose aussi la bordure rouge).
        """
        query = self.find_input.text()
        if not query:
            self._set_find_error(False)
            return None

        flags = 0 if self.btn_find_case.isChecked() else re.IGNORECASE
        if self.btn_find_regex.isChecked():
            try:
                pat = re.compile(query, flags)
            except re.error:
                self._set_find_error(True)
                return None
        else:
            pat = re.compile(re.escape(query), flags)
        self._set_find_error(False)
        return pat

    def _set_find_error(self, is_error: bool):
        self.find_input.setProperty("queryError", "true" if is_error else "false")
        self.find_input.style().unpolish(self.find_input)
        self.find_input.style().polish(self.find_input)

    def _recompute_find_matches(self):
        """Recense toutes les occurrences (bloc par bloc) et les surligne."""
        self._find_positions = []       # list[tuple[start, end]] en positions document
        self._find_current = -1
        query = self.find_input.text()
        if not query:
            self.chat_browser.setExtraSelections([])
            self._set_find_error(False)
            self._update_find_label()
            return

        pat = self._compile_find_pattern()
        if pat is None:
            self.chat_browser.setExtraSelections([])
            self._update_find_label()
            return

        doc = self.chat_browser.document()
        is_dark = get_active_theme() == "dark"
        base = QColor("#b45309") if is_dark else QColor("#fde68a")

        selections = []
        block = doc.firstBlock()
        while block.isValid():
            btext = block.text()
            if btext:
                bpos = block.position()
                for m in pat.finditer(btext):
                    s, e = m.span()
                    if e <= s:
                        continue  # correspondance vide -> ignorée
                    a, p = bpos + s, bpos + e
                    self._find_positions.append((a, p))
                    c = QTextCursor(doc)
                    c.setPosition(a)
                    c.setPosition(p, QTextCursor.MoveMode.KeepAnchor)
                    sel = self.chat_browser.ExtraSelection()
                    sel.cursor = c
                    sel.format.setBackground(base)
                    selections.append(sel)
            block = block.next()

        self.chat_browser.setExtraSelections(selections)
        self._update_find_label()

    def _goto_find_match(self, index: int):
        """Défile jusqu'à l'occurrence `index` (avec wrap) et l'indique.

        On NE fait PAS setTextCursor avec une sélection : le fond de sélection
        du navigateur masquerait le surlignage jaune. On déplace juste un
        curseur non sélectionnant pour amener la zone dans la vue, et on
        renforce visuellement l'occurrence courante dans les ExtraSelection.
        """
        if not self._find_positions:
            self._update_find_label()
            return
        n = len(self._find_positions)
        index %= n
        self._find_current = index
        anchor, _end = self._find_positions[index]

        cur = self.chat_browser.textCursor()
        cur.setPosition(anchor)
        self.chat_browser.setTextCursor(cur)   # curseur sans sélection -> pas de fond bleu
        self.chat_browser.ensureCursorVisible()

        self._refresh_find_highlight()
        self._update_find_label()

    def _refresh_find_highlight(self):
        """Reconstruit les ExtraSelection : toutes en jaune pâle, la courante
        en orange plus soutenu."""
        if not self._find_positions:
            return
        doc = self.chat_browser.document()
        is_dark = get_active_theme() == "dark"
        base = QColor("#b45309") if is_dark else QColor("#fde68a")
        current = QColor("#f59e0b") if is_dark else QColor("#fbbf24")
        selections = []
        for i, (a, p) in enumerate(self._find_positions):
            c = QTextCursor(doc)
            c.setPosition(a)
            c.setPosition(p, QTextCursor.MoveMode.KeepAnchor)
            sel = self.chat_browser.ExtraSelection()
            sel.cursor = c
            sel.format.setBackground(current if i == self._find_current else base)
            selections.append(sel)
        self.chat_browser.setExtraSelections(selections)

    def _update_find_label(self):
        query = self.find_input.text()
        if not query:
            self.find_result_label.setText("")
            return
        n = len(self._find_positions)
        if n == 0:
            self.find_result_label.setText("0 résultat")
            return
        pos = self._find_current + 1 if self._find_current >= 0 else 1
        self.find_result_label.setText(f"{pos} / {n}")

    def _find_next(self):
        """Occurrence suivante (avec wrap autour)."""
        if not self._find_positions:
            self._recompute_find_matches()
        if self._find_positions:
            self._goto_find_match(self._find_current + 1)

    def _find_prev(self):
        """Occurrence précédente (avec wrap autour)."""
        if not self._find_positions:
            self._recompute_find_matches()
        if self._find_positions:
            start = self._find_current if self._find_current >= 0 else 0
            self._goto_find_match(start - 1)

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
        if dtype in ("claude_project", "claude_conv"):
            # Source Claude Code / Desktop (v2.5) : export Markdown seulement.
            # Suppression/déplacement délibérément absents — ce sont des
            # fichiers gérés par Claude Code, pas par cette app (garde-fou
            # demandé explicitement).
            self._build_claude_context_menu(dtype, data, pos)
            return
        menu = QMenu(self)

        if dtype == "project":
            _, proj_name, convs = data
            act_open = menu.addAction(f"📂 Ouvrir '{proj_name}' dans l'Explorateur")
            act_open.triggered.connect(lambda: self._open_project_folder(proj_name))

            menu.addSeparator()
            n = len(convs)
            act_exp_all = menu.addAction(
                f"💾 Exporter les {n} conversation(s) en Markdown"
            )
            act_exp_all.setEnabled(n > 0)
            act_exp_all.triggered.connect(
                lambda checked=False, p=proj_name, cs=list(convs): self._export_project_all(p, cs)
            )
            act_pdf = menu.addAction("📄 Exporter le projet en PDF…")
            act_pdf.setEnabled(n > 0)
            act_pdf.triggered.connect(
                lambda checked=False, p=proj_name, cs=list(convs): self._export_project_pdf(p, cs)
            )
            act_archive = menu.addAction("🗃️ Archiver (ZIP) et supprimer le projet")
            act_archive.triggered.connect(
                lambda checked=False, p=proj_name, cs=list(convs): self._archive_and_delete_project(p, cs)
            )

            menu.addSeparator()
            act_del = menu.addAction(f"🗑️ Supprimer '{proj_name}' et ses {len(convs)} conversation(s)")
            act_del.triggered.connect(lambda: self._delete_project(proj_name, convs))

        elif dtype == "conv":
            c_info: ConversationInfo = data[1]
            act_copy_id = menu.addAction("📋 Copier l'ID de session")
            act_copy_id.triggered.connect(lambda: QApplication.clipboard().setText(c_info.conv_id))

            act_open_brain = menu.addAction("📂 Ouvrir le dossier des journaux (brain)")
            act_open_brain.triggered.connect(lambda: self._open_conv_brain(c_info.conv_id))

            # Export Markdown
            menu.addSeparator()
            if c_info.project:
                act_exp_proj = menu.addAction("💾 Exporter en Markdown dans le projet")
                act_exp_proj.triggered.connect(
                    lambda checked=False, info=c_info: self._export_conv_to_project(info)
                )
            act_exp_as = menu.addAction("💾 Exporter en Markdown…")
            act_exp_as.triggered.connect(
                lambda checked=False, info=c_info: self._export_conv_as(info)
            )

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

    # -----------------------------------------------------------------
    # Export Markdown d'une conversation
    # -----------------------------------------------------------------
    def _export_conv_to_project(self, c_info: ConversationInfo):
        """Écrit l'export dans <racine>/<projet>/_conversations/."""
        if not c_info.project:
            QMessageBox.information(
                self, "Aucun projet",
                "Cette conversation n'est rattachée à aucun projet.\n"
                "Utilisez « Exporter en Markdown… » pour choisir l'emplacement.",
            )
            return
        ok, result = export_conversation_to_project(
            c_info.conv_id, c_info.project, title=c_info.title or ""
        )
        if ok:
            self.status_bar.showMessage(f"💾 Exporté : {result}", 6000)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result).parent)))
        else:
            QMessageBox.critical(self, "Échec de l'export", result)

    def _export_conv_as(self, c_info: ConversationInfo):
        """Demande l'emplacement puis écrit l'export Markdown."""
        suggested = default_export_filename(c_info.conv_id, c_info.title or "")
        start_dir = str(get_projects_root() / (c_info.project or ""))
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter la conversation en Markdown",
            str(Path(start_dir) / suggested),
            "Fichiers Markdown (*.md);;Tous les fichiers (*)",
        )
        if not path:
            return
        ok, result = export_conversation_to_path(
            c_info.conv_id, path, title=c_info.title or "", project=c_info.project or ""
        )
        if ok:
            self.status_bar.showMessage(f"💾 Exporté : {result}", 6000)
        else:
            QMessageBox.critical(self, "Échec de l'export", result)

    # -----------------------------------------------------------------
    # Menu contextuel & export Markdown — source Claude Code / Desktop (v2.5)
    # Volontairement limité à l'export : pas de suppression/déplacement, ce
    # sont des fichiers gérés par Claude Code, pas par cette app.
    # -----------------------------------------------------------------
    def _build_claude_context_menu(self, dtype: str, data: tuple, pos):
        menu = QMenu(self)
        if dtype == "claude_conv":
            conv = data[1]
            act_open = menu.addAction("📂 Ouvrir le dossier du projet dans l'Explorateur")
            act_open.setEnabled(bool(conv.project_root and conv.project_root.is_dir()))
            act_open.triggered.connect(lambda: self._open_claude_project_folder(conv))

            act_copy_id = menu.addAction("📋 Copier l'ID de session")
            act_copy_id.triggered.connect(lambda: QApplication.clipboard().setText(conv.conv_id))

            menu.addSeparator()
            act_exp_proj = menu.addAction("💾 Exporter en Markdown dans le projet")
            act_exp_proj.setEnabled(bool(conv.project_root))
            act_exp_proj.triggered.connect(lambda checked=False, c=conv: self._export_claude_conv_to_project(c))
            act_exp_as = menu.addAction("💾 Exporter en Markdown…")
            act_exp_as.triggered.connect(lambda checked=False, c=conv: self._export_claude_conv_as(c))
        elif dtype == "claude_project":
            _, proj_name, convs = data
            act_open = menu.addAction(f"📂 Ouvrir '{proj_name}' dans l'Explorateur")
            root = convs[0].project_root if convs else None
            act_open.setEnabled(bool(root and root.is_dir()))
            act_open.triggered.connect(lambda: self._open_claude_project_folder(convs[0]) if convs else None)

            menu.addSeparator()
            n = len(convs)
            act_exp_all = menu.addAction(f"💾 Exporter les {n} conversation(s) en Markdown")
            act_exp_all.setEnabled(n > 0)
            act_exp_all.triggered.connect(
                lambda checked=False, p=proj_name, cs=list(convs): self._export_claude_project_all(p, cs)
            )
            act_pdf = menu.addAction("📄 Exporter le projet en PDF…")
            act_pdf.setEnabled(n > 0)
            act_pdf.triggered.connect(
                lambda checked=False, p=proj_name, cs=list(convs): self._export_claude_project_pdf(p, cs)
            )
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _open_claude_project_folder(self, conv):
        if conv.project_root and conv.project_root.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(conv.project_root)))
        else:
            QMessageBox.warning(self, "Erreur", "Dossier de projet introuvable.")

    def _export_claude_conv_to_project(self, conv):
        """Écrit l'export dans `<project_root>/_conversations/`."""
        ok, result = export_claude_conversation_to_project(conv)
        if ok:
            self.status_bar.showMessage(f"💾 Exporté : {result}", 6000)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(result).parent)))
        else:
            QMessageBox.critical(self, "Échec de l'export", result)

    def _export_claude_conv_as(self, conv):
        """Demande l'emplacement puis écrit l'export Markdown."""
        suggested = default_claude_export_filename(conv)
        start_dir = str(conv.project_root) if conv.project_root else str(Path.home())
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter la conversation en Markdown",
            str(Path(start_dir) / suggested),
            "Fichiers Markdown (*.md);;Tous les fichiers (*)",
        )
        if not path:
            return
        ok, result = export_claude_conversation_to_path(conv, path)
        if ok:
            self.status_bar.showMessage(f"💾 Exporté : {result}", 6000)
        else:
            QMessageBox.critical(self, "Échec de l'export", result)

    def _export_claude_project_all(self, project_name: str, convs: list):
        """Exporte en masse toutes les conversations Claude Code d'un projet
        en Markdown dans `<project_root>/_conversations/`."""
        if not convs:
            return
        root = convs[0].project_root
        if not root:
            QMessageBox.information(
                self, "Racine inconnue",
                "Ce projet n'a pas de dossier local identifiable "
                "(session démarrée ailleurs) — export en masse impossible.\n"
                "Utilisez « Exporter en Markdown… » sur chaque conversation.",
            )
            return
        dest = root / "_conversations"
        ret = QMessageBox.question(
            self,
            "Exporter le projet",
            f"Exporter les {len(convs)} conversation(s) de « {project_name} » "
            f"en Markdown dans :\n{dest}\n\n"
            f"Les fichiers existants seront écrasés. Continuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage(f"💾 Export de « {project_name} »…")
        QApplication.processEvents()
        try:
            ok, fail, dest_dir = export_claude_project_conversations(convs)
        except ValueError as exc:
            QMessageBox.critical(self, "Échec de l'export", str(exc))
            return
        msg = f"💾 {ok} conversation(s) exportée(s) dans {dest_dir}"
        if fail:
            msg += f" — {fail} échec(s)"
        self.status_bar.showMessage(msg, 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest_dir)))

    def _export_claude_project_pdf(self, project_name: str, convs: list):
        """Assemble toutes les conversations Claude Code du projet dans un
        seul PDF (même moteur Edge/Chromium headless que côté Antigravity)."""
        if not convs:
            return
        root = convs[0].project_root
        default_name = f"{project_name}_{__import__('datetime').datetime.now():%Y%m%d}.pdf"
        suggested = str((root / default_name) if root else Path.home() / default_name)
        pdf_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le projet en PDF", suggested, "Document PDF (*.pdf)"
        )
        if not pdf_path:
            return

        from pdf_export_html import export_claude_project_to_pdf

        self.status_bar.showMessage(
            f"📄 Génération du PDF de « {project_name} » ({len(convs)} conv.)…"
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            ok, result = export_claude_project_to_pdf(project_name, convs, pdf_path)
        finally:
            QApplication.restoreOverrideCursor()

        if ok:
            self.status_bar.showMessage(f"📄 PDF créé : {result}", 8000)
            QDesktopServices.openUrl(QUrl.fromLocalFile(result))
        else:
            QMessageBox.critical(self, "Échec de l'export PDF", result)

    # -----------------------------------------------------------------
    # Export / archivage au niveau d'un PROJET
    # -----------------------------------------------------------------
    def _export_project_all(self, project_name: str, convs: list):
        """Exporte toutes les conversations d'un projet dans son dossier
        `_conversations/`."""
        if not convs:
            return
        ret = QMessageBox.question(
            self,
            "Exporter le projet",
            f"Exporter les {len(convs)} conversation(s) de « {project_name} » "
            f"en Markdown dans :\n{get_projects_root() / project_name / '_conversations'}\n\n"
            f"Les fichiers existants seront écrasés. Continuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage(f"💾 Export de « {project_name} »…")
        QApplication.processEvents()
        ok, fail, dest = export_project_conversations(project_name, convs)
        msg = f"💾 {ok} conversation(s) exportée(s) dans {dest}"
        if fail:
            msg += f" — {fail} échec(s)"
        self.status_bar.showMessage(msg, 8000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest)))

    def _export_project_pdf(self, project_name: str, convs: list):
        """Assemble toutes les conversations du projet dans un seul PDF."""
        if not convs:
            return
        default_name = f"{project_name}_{__import__('datetime').datetime.now():%Y%m%d}.pdf"
        suggested = str(get_projects_root() / project_name / default_name)
        pdf_path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le projet en PDF", suggested, "Document PDF (*.pdf)"
        )
        if not pdf_path:
            return

        from pdf_export_html import export_project_to_pdf

        self.status_bar.showMessage(
            f"📄 Génération du PDF de « {project_name} » ({len(convs)} conv.)…"
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            ok, result = export_project_to_pdf(project_name, convs, pdf_path)
        finally:
            QApplication.restoreOverrideCursor()

        if ok:
            self.status_bar.showMessage(f"📄 PDF créé : {result}", 8000)
            QDesktopServices.openUrl(QUrl.fromLocalFile(result))
        else:
            QMessageBox.critical(self, "Échec de l'export PDF", result)

    def _archive_and_delete_project(self, project_name: str, convs: list):
        """Crée un ZIP de toutes les conversations (Markdown + images) PUIS
        supprime le projet en cascade."""
        default_name = (
            f"{project_name}_archive_"
            f"{__import__('datetime').datetime.now():%Y%m%d-%H%M%S}.zip"
        )
        # Suggestion : à côté du dossier projet (donc hors de ce qui sera supprimé).
        suggested = str(get_projects_root() / default_name)
        zip_path, _ = QFileDialog.getSaveFileName(
            self,
            "Archiver le projet — choisir l'emplacement du ZIP",
            suggested,
            "Archive ZIP (*.zip)",
        )
        if not zip_path:
            return

        # Garde-fou : le ZIP ne doit pas être DANS le dossier qu'on va supprimer.
        proj_dir = (get_projects_root() / project_name).resolve()
        try:
            Path(zip_path).resolve().relative_to(proj_dir)
            QMessageBox.warning(
                self, "Emplacement invalide",
                "Le ZIP ne peut pas être créé à l'intérieur du dossier du projet "
                "(il serait supprimé avec lui). Choisissez un autre emplacement.",
            )
            return
        except ValueError:
            pass  # bien : le zip est en dehors

        ret = QMessageBox.warning(
            self,
            "Archiver et supprimer",
            f"⚠️ Cette action va :\n\n"
            f"1. Créer une archive ZIP de {len(convs)} conversation(s) :\n   {zip_path}\n"
            f"2. Puis SUPPRIMER définitivement le projet « {project_name} » "
            f"(dossier disque + conversations Antigravity).\n\n"
            f"Continuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        self.status_bar.showMessage(f"🗃️ Archivage de « {project_name} »…")
        QApplication.processEvents()
        ok, result = archive_project(project_name, convs, zip_path)
        if not ok:
            QMessageBox.critical(self, "Échec de l'archivage",
                                 f"{result}\n\nLe projet N'A PAS été supprimé.")
            return

        # Archive OK -> suppression en cascade.
        del_ok, del_msg = delete_project_cascade(
            project_name, [c.conv_id for c in convs]
        )
        if del_ok:
            QMessageBox.information(
                self, "Projet archivé et supprimé",
                f"Archive créée :\n{result}\n\n{del_msg}",
            )
            self.reload_data()
        else:
            QMessageBox.warning(
                self, "Archive créée, suppression partielle",
                f"Archive OK :\n{result}\n\nMais la suppression a rencontré des "
                f"erreurs :\n{del_msg}",
            )
            self.reload_data()

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
def _crash_log_path() -> Path:
    """Chemin de crash.log : à côté du .exe (frozen) ou du script (dev)."""
    base = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    return base / "crash.log"


def _append_crash_log(header: str, body: str) -> None:
    """Ajoute une entrée horodatée à crash.log (append, pas d'écrasement)."""
    import datetime
    try:
        with _crash_log_path().open("a", encoding="utf-8") as fh:
            fh.write(f"\n[{datetime.datetime.now()}] {header}\n{body}\n")
    except Exception:
        pass


def _install_global_excepthooks() -> None:
    """Capture les exceptions non gérées — y compris celles levées DANS les
    slots Qt (clics, timers, threads worker) que la boucle d'événements avale
    normalement en silence — et les écrit dans crash.log.

    Ne bloque jamais l'application : on logue puis on laisse le comportement
    par défaut suivre son cours.
    """
    import traceback

    _prev_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            _append_crash_log(
                "EXCEPTION NON GÉRÉE",
                "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
            )
        try:
            _prev_hook(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _hook

    # threading.excepthook : exceptions dans les threads Python (dont QRunnable
    # exécutés par QThreadPool passent par le C++ Qt, mais un thread pur Python
    # y transiterait).
    try:
        import threading

        def _thread_hook(args):
            _append_crash_log(
                f"EXCEPTION THREAD ({args.thread.name})",
                "".join(
                    traceback.format_exception(
                        args.exc_type, args.exc_value, args.exc_traceback
                    )
                ),
            )

        threading.excepthook = _thread_hook
    except Exception:
        pass

    # Messages du moteur Qt (qWarning / qCritical / qFatal) : on ne garde que
    # les niveaux sérieux pour ne pas polluer le log.
    try:
        from PyQt6.QtCore import qInstallMessageHandler, QtMsgType

        def _qt_handler(mode, context, message):
            if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                loc = ""
                if context and context.file:
                    loc = f" ({context.file}:{context.line})"
                _append_crash_log(f"QT {mode.name}{loc}", message)

        qInstallMessageHandler(_qt_handler)
    except Exception:
        pass


def main():
    import traceback
    import datetime

    _log_path = _crash_log_path()
    # Marqueur de démarrage (confirme que main() est bien atteinte).
    try:
        _log_path.write_text(
            f"[{datetime.datetime.now()}] main() démarrée\n", encoding="utf-8"
        )
    except Exception:
        pass

    _install_global_excepthooks()

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
        _append_crash_log("CRASH (démarrage)", traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
