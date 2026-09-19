"""conftest.py — fixtures partagées.

Isole l'index de recherche plein-texte dans un fichier temporaire par test :
sans cela, chaque `AntigravityManagerWindow` instanciée lancerait une
synchronisation sur le vrai `search_index.db` (threads de fond + I/O disque),
ce qui rendait la suite lente et pouvait faire crasher le teardown Qt.
"""

import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# L'archivage automatique (archive.py) parcourt le vrai `.gemini/` et écrit sur
# disque : à désactiver dans toute la suite pour ne pas polluer ni ralentir les
# tests d'interface. Les tests dédiés (test_archive.py) appellent archive_all()
# directement, sans passer par ce garde-fou.
os.environ["ANTIGRAVITY_MANAGER_NO_ARCHIVE"] = "1"


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path, monkeypatch):
    """Les tests ne doivent ni lire ni modifier les historiques de l'utilisateur."""
    import config

    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "DEFAULT_PROJECTS_ROOT", str(tmp_path / "projects"))
    monkeypatch.setattr(config, "DEFAULT_CODEX_ROOT", str(tmp_path / ".codex"))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _drain_thread_pool():
    try:
        from PyQt6.QtCore import QThreadPool
        from PyQt6.QtWidgets import QApplication

        pool = QThreadPool.globalInstance()
        pool.waitForDone(5000)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def isolated_search_index(tmp_path, monkeypatch):
    """Redirige l'index de recherche vers un fichier jetable et garantit qu'aucun
    thread d'indexation d'un test précédent ne tourne encore (les signaux d'un
    runnable survivant émis pendant la construction d'une nouvelle fenêtre
    provoquaient un access violation)."""
    import search_index

    _drain_thread_pool()  # avant : plus aucun runnable d'un test précédent en vol

    db_path = tmp_path / "search_index.db"
    monkeypatch.setattr(search_index, "get_index_path", lambda: db_path)
    search_index.close_thread_connection()

    import claude_search_index
    import codex_search_index

    monkeypatch.setattr(claude_search_index, "get_index_path", lambda: tmp_path / "claude_index.db")
    monkeypatch.setattr(codex_search_index, "get_index_path", lambda: tmp_path / "codex_index.db")
    claude_search_index.close_thread_connection()
    codex_search_index.close_thread_connection()

    yield

    _drain_thread_pool()  # après : ne pas laisser de thread survivre au test
    search_index.close_thread_connection()
    claude_search_index.close_thread_connection()
    codex_search_index.close_thread_connection()
