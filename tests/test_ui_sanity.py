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

