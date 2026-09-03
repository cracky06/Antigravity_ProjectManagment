"""test_search_ui.py — Intégration UI de la recherche v1.5.

Vérifie les toggles de mode [.*] / [Ab], l'exclusion mutuelle, le mode
effectif renvoyé, et le repli quand l'index n'est pas prêt.
"""

import pytest

from PyQt6.QtWidgets import QApplication


@pytest.fixture
def win(qapp):
    from antigravity_manager import AntigravityManagerWindow

    w = AntigravityManagerWindow()
    # Draine la synchro d'index lancée par reload_data().
    w._thread_pool.waitForDone(3000)
    yield w
    w.close()
    w._thread_pool.waitForDone(3000)


def test_default_mode_is_substring(win):
    assert win.btn_mode_regex.isChecked() is False
    assert win.btn_mode_words.isChecked() is False
    assert win._current_search_mode() == "substring"


def test_toggles_are_mutually_exclusive(win):
    win.btn_mode_regex.setChecked(True)
    assert win._current_search_mode() == "regex"
    assert win.btn_mode_words.isChecked() is False

    win.btn_mode_words.setChecked(True)
    assert win._current_search_mode() == "words"
    assert win.btn_mode_regex.isChecked() is False

    win.btn_mode_words.setChecked(False)
    assert win._current_search_mode() == "substring"


def test_mode_label_helper(win):
    assert win._mode_label("regex") == "regex"
    assert win._mode_label("words") == "mots"
    assert win._mode_label("substring") == "contient"


def test_query_error_toggles_property(win):
    win._set_query_error(True)
    assert win.search_input.property("queryError") == "true"
    win._set_query_error(False)
    assert win.search_input.property("queryError") == "false"


def test_regex_failure_sets_error_border(win):
    win.btn_mode_regex.setChecked(True)
    win.search_input.setText("[unterminated")
    win._do_search()
    win._thread_pool.waitForDone(3000)
    QApplication.processEvents()
    assert win.search_input.property("queryError") == "true"


def test_words_mode_without_index_falls_back(win, monkeypatch):
    import search_index

    # Simule un index absent : le mode effectif doit rétrograder en substring.
    monkeypatch.setattr(win, "_index_ready", False)
    win.btn_mode_words.setChecked(True)
    # _do_search calcule effective_mode ; on le vérifie indirectement en
    # s'assurant qu'aucune exception n'est levée et que la recherche se lance.
    win.search_input.setText("test")
    win._do_search()
    win._thread_pool.waitForDone(3000)
    QApplication.processEvents()
    # Pas d'erreur de requête (le fallback substring n'échoue pas).
    assert win.search_input.property("queryError") in (None, "false")


def test_stale_search_result_ignored(win):
    # Un résultat portant une génération ancienne ne doit pas repeupler l'arbre.
    win._search_generation = 5
    before = win.tree.topLevelItemCount()
    win._on_search_finished(3, {"whatever"})  # génération périmée
    assert win.tree.topLevelItemCount() == before
