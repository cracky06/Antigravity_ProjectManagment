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


# ---------------------------------------------------------------------------
# Find bar : compteur d'occurrences & surlignage (v1.5)
# ---------------------------------------------------------------------------
def _load_conv_with_text(win, text: str):
    """Injecte un document HTML simple dans le chat_browser."""
    win.selected_conv = _make_conv("cv-find")
    win.chat_browser.setHtml(f"<html><body><pre>{text}</pre></body></html>")


def test_find_counts_all_occurrences(win):
    _load_conv_with_text(win, "alpha beta alpha gamma alpha delta")
    win._show_find_bar()
    win.find_input.setText("alpha")
    win._recompute_find_matches()
    assert len(win._find_positions) == 3
    assert len(win.chat_browser.extraSelections()) == 3
    assert win.find_result_label.text() == "0 / 3" or win.find_result_label.text() == "1 / 3"


def test_find_navigation_wraps_and_updates_label(win):
    _load_conv_with_text(win, "x TOKEN y TOKEN z TOKEN w")
    win._show_find_bar()
    win.find_input.setText("TOKEN")
    win._on_find_text_changed()          # recompute + va au 1er
    assert win.find_result_label.text() == "1 / 3"

    win._find_next()
    assert win.find_result_label.text() == "2 / 3"
    win._find_next()
    assert win.find_result_label.text() == "3 / 3"
    win._find_next()                     # wrap -> 1
    assert win.find_result_label.text() == "1 / 3"
    win._find_prev()                     # wrap arrière -> 3
    assert win.find_result_label.text() == "3 / 3"


def test_find_no_match_shows_zero(win):
    _load_conv_with_text(win, "hello world")
    win._show_find_bar()
    win.find_input.setText("absent")
    win._on_find_text_changed()
    assert win._find_positions == []
    assert win.find_result_label.text() == "0 résultat"


def test_hide_find_bar_clears_highlight(win):
    _load_conv_with_text(win, "match match match")
    win._show_find_bar()
    win.find_input.setText("match")
    win._recompute_find_matches()
    assert win.chat_browser.extraSelections()

    win._hide_find_bar()
    assert win.chat_browser.extraSelections() == []
    assert win._find_positions == []
    assert win._find_current == -1


# ---------------------------------------------------------------------------
# Find bar : modes regex [.*] et casse [Aa] (v1.6)
# ---------------------------------------------------------------------------
def test_find_case_sensitive_toggle(win):
    _load_conv_with_text(win, "Foo FOO foo Foobar")
    win._show_find_bar()
    win.find_input.setText("foo")

    win.btn_find_case.setChecked(False)
    win._on_find_text_changed()
    assert len(win._find_positions) == 4  # Foo, FOO, foo, Foobar

    win.btn_find_case.setChecked(True)
    win._on_find_text_changed()
    assert len(win._find_positions) == 1  # seul "foo"


def test_find_regex_variable_length_matches(win):
    _load_conv_with_text(win, "abc123 def4567 gh89 zzz")
    win._show_find_bar()
    win.btn_find_regex.setChecked(True)
    win.find_input.setText(r"[a-z]+\d+")
    win._on_find_text_changed()

    text = win.chat_browser.toPlainText()
    matched = [text[s:s + length] for s, length in win._find_positions]
    assert matched == ["abc123", "def4567", "gh89"]


def test_find_regex_invalid_sets_error_and_no_matches(win):
    _load_conv_with_text(win, "some text here")
    win._show_find_bar()
    win.btn_find_regex.setChecked(True)
    win.find_input.setText("[unterminated")
    win._on_find_text_changed()

    assert win._find_positions == []
    assert win.find_input.property("queryError") == "true"

    # Un motif valide efface l'erreur.
    win.find_input.setText("text")
    win._on_find_text_changed()
    assert win.find_input.property("queryError") == "false"


def test_find_regex_navigation_and_label(win):
    _load_conv_with_text(win, "id=1 id=22 id=333 id=4444")
    win._show_find_bar()
    win.btn_find_regex.setChecked(True)
    win.find_input.setText(r"id=\d+")
    win._on_find_text_changed()
    assert win.find_result_label.text() == "1 / 4"
    win._find_next()
    assert win.find_result_label.text() == "2 / 4"
    win._find_prev()
    win._find_prev()  # wrap
    assert win.find_result_label.text() == "4 / 4"


def test_find_regex_ignores_empty_matches(win):
    _load_conv_with_text(win, "aaa bbb")
    win._show_find_bar()
    win.btn_find_regex.setChecked(True)
    win.find_input.setText("a*")  # peut matcher le vide
    win._on_find_text_changed()
    # Seules les correspondances non vides sont retenues.
    text = win.chat_browser.toPlainText()
    assert all(length > 0 for _s, length in win._find_positions)
    assert "aaa" in [text[s:s + length] for s, length in win._find_positions]


def test_hide_find_bar_clears_regex_error(win):
    _load_conv_with_text(win, "content")
    win._show_find_bar()
    win.btn_find_regex.setChecked(True)
    win.find_input.setText("(bad")
    win._on_find_text_changed()
    assert win.find_input.property("queryError") == "true"

    win._hide_find_bar()
    assert win.find_input.property("queryError") == "false"
