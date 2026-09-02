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
    dlg.close()
