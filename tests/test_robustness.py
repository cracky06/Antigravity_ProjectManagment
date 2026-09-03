"""test_robustness.py — Robustesse v1.7 : backup protobuf, logging, persistance UI."""

import time

import pytest


# ---------------------------------------------------------------------------
# _backup_pb_file : sauvegarde horodatée + rotation
# ---------------------------------------------------------------------------
def test_backup_creates_timestamped_copy(tmp_path):
    import data_loader as dl

    pb = tmp_path / "agyhub_summaries_proto.pb"
    pb.write_bytes(b"ORIGINAL")
    backup = dl._backup_pb_file(pb)

    assert backup is not None
    assert backup.exists()
    assert backup.name.startswith("agyhub_summaries_proto.pb.bak-")
    assert backup.read_bytes() == b"ORIGINAL"


def test_backup_absent_file_returns_none(tmp_path):
    import data_loader as dl

    assert dl._backup_pb_file(tmp_path / "does_not_exist.pb") is None


def test_backup_rotation_keeps_only_n(tmp_path, monkeypatch):
    import data_loader as dl

    monkeypatch.setattr(dl, "_PB_BACKUP_KEEP", 3)
    pb = tmp_path / "agyhub_summaries_proto.pb"
    pb.write_bytes(b"V0")
    for i in range(7):
        time.sleep(0.02)
        dl._backup_pb_file(pb)
        pb.write_bytes(f"V{i + 1}".encode())

    backups = sorted(tmp_path.glob("agyhub_summaries_proto.pb.bak-*"),
                     key=lambda p: p.stat().st_mtime)
    assert len(backups) == 3
    # Ce sont les plus récentes qui restent (V4, V5, V6 au moment de la copie).
    assert [b.read_bytes().decode() for b in backups] == ["V4", "V5", "V6"]


# ---------------------------------------------------------------------------
# Logger : silencieux par défaut
# ---------------------------------------------------------------------------
def test_logger_is_silent_by_default():
    import data_loader as dl

    # Sans ANTIGRAVITY_MANAGER_DEBUG, un NullHandler et aucun fichier de log.
    handler_types = {type(h).__name__ for h in dl.logger.handlers}
    assert "FileHandler" not in handler_types
    # NullHandler attendu (ajouté à l'import).
    assert "NullHandler" in handler_types


# ---------------------------------------------------------------------------
# config : ui_state
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    import config

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    return config


def test_ui_state_roundtrip(temp_config):
    temp_config.save_ui_state(
        {"geometry": "QQ==", "splitter": [321, 987], "project_filter": "ProjX"}
    )
    state = temp_config.get_ui_state()
    assert state == {"geometry": "QQ==", "splitter": [321, 987], "project_filter": "ProjX"}


def test_ui_state_partial_merge(temp_config):
    temp_config.save_ui_state({"geometry": "AA==", "splitter": [100, 200]})
    temp_config.save_ui_state({"splitter": [300, 400]})  # merge, ne perd pas geometry
    state = temp_config.get_ui_state()
    assert state["geometry"] == "AA=="
    assert state["splitter"] == [300, 400]


def test_ui_state_absent_returns_empty(temp_config):
    assert temp_config.get_ui_state() == {}


def test_ui_state_survives_other_config_keys(temp_config):
    temp_config.save_config({"theme": "dark", "projects_root": "E:\\Dev"})
    temp_config.save_ui_state({"splitter": [1, 2]})
    cfg = temp_config.load_config()
    assert cfg["theme"] == "dark"
    assert cfg["ui_state"]["splitter"] == [1, 2]


# ---------------------------------------------------------------------------
# Fenêtre : restauration / persistance
# ---------------------------------------------------------------------------
def test_window_applies_saved_splitter_sizes(qapp, tmp_path, monkeypatch):
    """__init__ doit passer les tailles sauvegardées à splitter.setSizes()."""
    import config
    import antigravity_manager as am

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(am, "get_ui_state", lambda: {"splitter": [280, 800]})

    captured = []
    real_setsizes = am.QSplitter.setSizes
    monkeypatch.setattr(
        am.QSplitter, "setSizes",
        lambda self, sizes: (captured.append(list(sizes)), real_setsizes(self, sizes))[1],
    )

    win = am.AntigravityManagerWindow()
    win._thread_pool.waitForDone(3000)
    try:
        # La dernière application de tailles au splitter principal doit être
        # celle qu'on a sauvegardée (et non le défaut [340, 920]).
        assert [280, 800] in captured
        assert captured[-1] == [280, 800]
    finally:
        win.close()
        win._thread_pool.waitForDone(3000)


def test_window_falls_back_to_default_splitter(qapp, tmp_path, monkeypatch):
    import config
    import antigravity_manager as am

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(am, "get_ui_state", lambda: {})  # rien de sauvegardé

    captured = []
    real_setsizes = am.QSplitter.setSizes
    monkeypatch.setattr(
        am.QSplitter, "setSizes",
        lambda self, sizes: (captured.append(list(sizes)), real_setsizes(self, sizes))[1],
    )

    win = am.AntigravityManagerWindow()
    win._thread_pool.waitForDone(3000)
    try:
        assert captured[-1] == [340, 920]
    finally:
        win.close()
        win._thread_pool.waitForDone(3000)


def test_persist_ui_state_writes_current_values(qapp, tmp_path, monkeypatch):
    import config
    import antigravity_manager as am

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")

    win = am.AntigravityManagerWindow()
    win._thread_pool.waitForDone(3000)
    try:
        # On force des valeurs lisibles côté API (indépendamment du rendu Qt).
        monkeypatch.setattr(win.splitter, "sizes", lambda: [250, 750])
        win._persist_ui_state()

        state = config.get_ui_state()
        assert state.get("splitter") == [250, 750]
        assert isinstance(state.get("geometry"), str) and state["geometry"]
    finally:
        win.close()
        win._thread_pool.waitForDone(3000)
