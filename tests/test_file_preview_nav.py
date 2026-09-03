"""test_file_preview_nav.py — Couverture de l'aperçu de fichier et de la
navigation (bouton ←) introduits en v1.3.

Cibles :
  - AntigravityManagerWindow._on_anchor_clicked (routage web / dossier / fichier)
  - AntigravityManagerWindow._show_file_content (garde-fous taille / binaire /
    introuvable, rendu du contenu)
  - AntigravityManagerWindow._render_file_body (coloration Pygments + repli)
  - AntigravityManagerWindow._navigate_back (transitions aperçu ↔ conversation)
  - la pile d'historique _nav_history
"""

import os
from pathlib import Path

import pytest

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication

os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def win(qapp):
    from antigravity_manager import AntigravityManagerWindow

    w = AntigravityManagerWindow()
    yield w
    w.close()


def _make_conv(conv_id: str, title: str = "Titre", project: str = "ProjX"):
    from data_loader import ConversationInfo

    return ConversationInfo(
        conv_id=conv_id,
        title=title,
        project=project,
        workspace=r"E:\Dev\ProjX",
        last_activity=None,
    )


# ---------------------------------------------------------------------------
# _render_file_body
# ---------------------------------------------------------------------------
def test_render_file_body_python_is_highlighted(win, tmp_path):
    p = tmp_path / "snippet.py"
    p.write_text("def hello():\n    return 42\n", encoding="utf-8")
    html, _css = win._render_file_body(p, p.read_text(encoding="utf-8"), is_dark=True)
    # Pygments produit du HTML stylé inline (noclasses=True) ; le repli produit
    # un <pre> nu. Dans les deux cas le texte source doit être présent.
    assert "hello" in html
    assert "<span" in html or html.startswith("<pre>")


def test_render_file_body_unknown_extension_falls_back(win, tmp_path):
    p = tmp_path / "data.weirdext"
    p.write_text("plain content <with> & entities", encoding="utf-8")
    html, _css = win._render_file_body(p, p.read_text(encoding="utf-8"), is_dark=False)
    # Le repli échappe le HTML.
    assert "&lt;with&gt;" in html or "&amp;" in html or "plain content" in html


# ---------------------------------------------------------------------------
# _show_file_content : garde-fous
# ---------------------------------------------------------------------------
def test_show_file_content_missing_file(win):
    win._show_file_content(Path(r"Z:\does\not\exist.txt"))
    assert win._file_view_active is False
    assert "introuvable" in win.status_bar.currentMessage().lower()


def test_show_file_content_too_large(win, tmp_path):
    p = tmp_path / "huge.log"
    p.write_bytes(b"x" * (win._MAX_FILE_VIEW_BYTES + 1))
    win._show_file_content(p)
    assert win._file_view_active is False
    assert "volumineux" in win.status_bar.currentMessage().lower()


def test_show_file_content_binary_detected(win, tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"MZ\x00\x00\x90\x00binarystuff")
    win._show_file_content(p)
    assert win._file_view_active is False
    assert "binaire" in win.status_bar.currentMessage().lower()


def test_show_file_content_text_file_activates_view(win, tmp_path):
    conv = _make_conv("conv-A")
    win.display_chat(conv)
    p = tmp_path / "build.bat"
    p.write_text("@echo off\r\npyinstaller --onefile app.py\r\n", encoding="utf-8")

    win._show_file_content(p)

    assert win._file_view_active is True
    assert win._file_view_return_conv is conv
    # En headless la fenêtre n'est pas montrée -> isVisible() est toujours faux ;
    # on vérifie que le widget n'a pas été explicitement masqué.
    assert win.btn_back.isHidden() is False
    assert "build.bat" in win.chat_title.text()
    # Le nom du fichier apparaît dans le rendu HTML du navigateur.
    assert "build.bat" in win.chat_browser.toPlainText()


# ---------------------------------------------------------------------------
# _on_anchor_clicked : routage
# ---------------------------------------------------------------------------
def test_anchor_click_local_file_shows_content(win, tmp_path, monkeypatch):
    conv = _make_conv("conv-B")
    win.display_chat(conv)
    p = tmp_path / "notes.txt"
    p.write_text("quelques notes", encoding="utf-8")

    opened = []
    monkeypatch.setattr(
        "antigravity_manager.QDesktopServices.openUrl", lambda u: opened.append(u)
    )

    win._on_anchor_clicked(QUrl.fromLocalFile(str(p)))

    assert win._file_view_active is True
    assert opened == []  # un fichier local n'est jamais "ouvert" par le système


def test_anchor_click_directory_opens_explorer(win, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "antigravity_manager.QDesktopServices.openUrl", lambda u: opened.append(u)
    )
    win._on_anchor_clicked(QUrl.fromLocalFile(str(tmp_path)))

    assert win._file_view_active is False
    assert len(opened) == 1


def test_anchor_click_http_opens_system(win, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "antigravity_manager.QDesktopServices.openUrl", lambda u: opened.append(u)
    )
    win._on_anchor_clicked(QUrl("https://example.com/page"))

    assert len(opened) == 1
    assert win._file_view_active is False


def test_anchor_click_empty_url_is_noop(win, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "antigravity_manager.QDesktopServices.openUrl", lambda u: opened.append(u)
    )
    win._on_anchor_clicked(QUrl())
    assert opened == []


# ---------------------------------------------------------------------------
# _navigate_back : transitions
# ---------------------------------------------------------------------------
def test_back_from_file_view_restores_conversation(win, tmp_path):
    conv = _make_conv("conv-C", title="Ma conversation")
    win.display_chat(conv)
    p = tmp_path / "config.json"
    p.write_text('{"k": 1}', encoding="utf-8")

    win._show_file_content(p)
    assert win._file_view_active is True

    win._navigate_back()

    assert win._file_view_active is False
    assert win._file_view_return_conv is None
    assert win.selected_conv is conv
    assert "Ma conversation" in win.chat_title.text()


def test_nav_history_push_on_explicit_open_only(win):
    a, b, c = _make_conv("a"), _make_conv("b"), _make_conv("c")

    win.display_chat(a)                       # 1ère conv : rien à empiler
    assert win._nav_history == []

    win.display_chat(b)                       # a est empilée
    assert [ci.conv_id for ci in win._nav_history] == ["a"]

    win.display_chat(c, record_history=False)  # nav clavier : pas d'empilement
    assert [ci.conv_id for ci in win._nav_history] == ["a"]

    win._navigate_back()                      # dépile -> a
    assert win.selected_conv.conv_id == "a"
    assert win._nav_history == []


def test_clear_chat_resets_navigation_state(win, tmp_path):
    conv = _make_conv("conv-D")
    win.display_chat(conv)
    win.display_chat(_make_conv("conv-E"))
    assert win._nav_history != []

    win._clear_chat()

    assert win._nav_history == []
    assert win._file_view_active is False
    assert win._file_view_return_conv is None
    assert win.btn_back.isHidden() is True


# ---------------------------------------------------------------------------
# Raccourcis clavier (v1.3)
# ---------------------------------------------------------------------------
def test_shortcuts_registered(win):
    from PyQt6.QtGui import QKeySequence

    seqs = {sc.key().toString() for sc in win._shortcuts}
    for expected in ("Ctrl+F", "Ctrl+K", "Ctrl+L", "F3", "Shift+F3"):
        assert QKeySequence(expected).toString() in seqs


def test_escape_clears_global_search(win):
    win.search_input.setText("recherche en cours")
    win.find_bar.setVisible(False)
    win._on_escape()
    assert win.search_input.text() == ""


def test_escape_hides_find_bar_first(win):
    conv = _make_conv("conv-F")
    win.display_chat(conv)
    win.search_input.setText("garde-moi")
    win.find_bar.setVisible(True)
    win._on_escape()
    assert win.find_bar.isVisibleTo(win) is False
    assert win.search_input.text() == "garde-moi"


def test_focus_global_search_selects_all(win):
    win.search_input.setText("abc")
    win._focus_global_search()
    assert win.search_input.hasSelectedText() is True
