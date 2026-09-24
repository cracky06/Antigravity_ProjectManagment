"""test_ui_sanity.py — Test headless de cohérence de l'interface PyQt6."""

import os
import sys
import pytest

from PyQt6.QtWidgets import QApplication

# Configurer Qt en mode headless pour les tests automatisés
os.environ["QT_QPA_PLATFORM"] = "offscreen"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_main_window_instantiation(qapp):
    """Vérifie que la fenêtre principale s'instancie et peuple l'arborescence sans exception."""
    from antigravity_manager import AntigravityManagerWindow

    win = AntigravityManagerWindow()
    assert win.windowTitle().startswith("Antigravity Manager")
    assert win.tree is not None
    assert win.chat_browser is not None
    assert win.tree.topLevelItemCount() >= 2  # Sections "PROJETS" et "CONVERSATIONS RÉCENTES"
    win.close()


def test_settings_dialog_instantiation(qapp):
    """Vérifie que la boîte de dialogue des paramètres s'instancie correctement."""
    from antigravity_manager import SettingsDialog

    dlg = SettingsDialog()
    assert dlg.windowTitle().startswith("Paramètres")
    assert dlg.proj_edit.text() != ""
    assert dlg.ag_edit.text() != ""
    # v2.5 : champ « Dossier Claude Code »
    assert dlg.claude_edit.text() != ""
    dlg._reset_defaults()
    assert dlg.claude_edit.text() == r"%USERPROFILE%\.claude\projects"
    dlg.close()


def test_claude_source_empty_tree_shows_hint(qapp, tmp_path, monkeypatch):
    """Bascule sur la source Claude Code sans données : l'arbre affiche un
    message d'explication, pas 3 sections vides ni un crash."""
    import config
    from antigravity_manager import AntigravityManagerWindow

    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    config.save_config({"claude_root": str(tmp_path / "inexistant")})

    win = AntigravityManagerWindow()
    win.source_combo.setCurrentIndex(1)  # -> claude_code
    labels = [win.tree.topLevelItem(i).text(0) for i in range(win.tree.topLevelItemCount())]
    assert any("introuvable" in lab or "Aucune conversation" in lab for lab in labels)
    # Rebascule Antigravity sans erreur.
    win.source_combo.setCurrentIndex(0)
    assert win._active_source == "antigravity"
    win.close()


def test_changelog_dialog_and_markdown_rendering(qapp):
    """Vérifie l'instanciation de ChangelogDialog et la présence du module markdown."""
    from antigravity_manager import ChangelogDialog
    import markdown

    dlg = ChangelogDialog()
    assert dlg.windowTitle().startswith("Historique")
    assert dlg.tree.topLevelItemCount() >= 1
    dlg.close()

    # Vérification du parseur markdown
    html = markdown.markdown("# Titre\n\n**Texte gras**\n\n- Puce", extensions=["fenced_code", "tables"])
    assert "<h1>Titre</h1>" in html
    assert "<strong>Texte gras</strong>" in html
    assert "<li>Puce</li>" in html


def test_about_dialog_and_splash_asset(qapp):
    """AboutDialog s'instancie ; l'image d'accueil est trouvée dans assets/."""
    from antigravity_manager import AboutDialog, _get_splash_pixmap, GITHUB_URL

    pm = _get_splash_pixmap()
    assert pm is not None and pm.width() > 0

    dlg = AboutDialog()
    assert "propos" in dlg.windowTitle()
    assert GITHUB_URL.startswith("https://github.com/")
    dlg.close()


def test_find_asset_resolves_and_missing(qapp):
    from antigravity_manager import _find_asset

    assert _find_asset("assets/icon.png") is not None
    assert _find_asset("assets/nexiste-pas.xyz") is None


def test_chat_tree_widget_target_resolution(qapp):
    """Vérifie la détection du projet cible sur un dossier ou une conversation enfant."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItem
    from antigravity_manager import _ChatTreeWidget
    from data_loader import ConversationInfo

    tree = _ChatTreeWidget()
    p_item = QTreeWidgetItem(["📁 ProjA"])
    p_item.setData(0, Qt.ItemDataRole.UserRole, ("project", "ProjA", []))
    tree.addTopLevelItem(p_item)

    c_info = ConversationInfo("cid-1", "Discussion 1", "ProjA", "", None)
    c_item = QTreeWidgetItem(["💬 Discussion 1"])
    c_item.setData(0, Qt.ItemDataRole.UserRole, ("conv", c_info))
    p_item.addChild(c_item)

    # Résolution sur le dossier
    assert tree._resolve_target_project(p_item) == "ProjA"
    # Résolution sur une conversation enfant
    assert tree._resolve_target_project(c_item) == "ProjA"
    # Résolution sur un élément nul ou sans métadonnée
    assert tree._resolve_target_project(None) is None
    orphan_header = QTreeWidgetItem(["HORS PROJET"])
    assert tree._resolve_target_project(orphan_header) is None


def test_tree_state_capture_and_restore(qapp):
    """Vérifie la mémorisation et la réouverture automatique des dossiers lors d'un rechargement."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItemIterator
    from antigravity_manager import AntigravityManagerWindow

    win = AntigravityManagerWindow()
    # Trouver le premier dossier projet et le déplier
    target_project_name = None
    it = QTreeWidgetItemIterator(win.tree)
    while it.value():
        item = it.value()
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "project" and item.childCount() > 0:
            target_project_name = data[1]
            item.setExpanded(True)
            break
        it += 1

    if target_project_name:
        expanded, _ = win._capture_tree_state()
        assert target_project_name in expanded

        # Replier manuellement
        it = QTreeWidgetItemIterator(win.tree)
        while it.value():
            item = it.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "project" and data[1] == target_project_name:
                item.setExpanded(False)
                break
            it += 1

        # Restaurer
        win._restore_tree_state(expanded, None)

        # Vérifier qu'il est redéplié
        is_re_expanded = False
        it = QTreeWidgetItemIterator(win.tree)
        while it.value():
            item = it.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "project" and data[1] == target_project_name:
                is_re_expanded = item.isExpanded()
                break
            it += 1
        assert is_re_expanded is True

    # Test de priorisation de _target_select_conv_id
    win._target_select_conv_id = "forced-conv-id-999"
    _, captured_id = win._capture_tree_state()
    assert captured_id == "forced-conv-id-999"
    assert win._target_select_conv_id is None

    win.close()

