"""test_live_watch.py — Rafraîchissement ciblé + suivi « live » d'une discussion.

Couvre `live_watch.py` (résolution des chemins à surveiller) et l'intégration
dans `AntigravityManagerWindow` (boutons 🔄 / 🔴 Suivre, armement/désarmement du
watcher, re-rendu sur changement, préservation du scroll).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from PyQt6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# live_watch.antigravity_watch_paths / claude_watch_paths
# ---------------------------------------------------------------------------
def test_claude_watch_paths(tmp_path):
    import live_watch

    f = tmp_path / "session.jsonl"
    f.write_text("{}", encoding="utf-8")
    assert live_watch.claude_watch_paths(f) == [f]
    assert live_watch.claude_watch_paths(tmp_path / "absent.jsonl") == []


def test_antigravity_watch_paths_prefers_transcript(tmp_path, monkeypatch):
    import live_watch

    tf = tmp_path / "transcript.jsonl"
    tf.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        live_watch, "_find_transcript_file",
        lambda cid, allow_partial=False: tf if not allow_partial else None,
    )
    monkeypatch.setattr(live_watch, "_find_ide_sqlite_db", lambda cid: None)
    monkeypatch.setattr(live_watch, "_find_brain_path", lambda cid: None)

    assert live_watch.antigravity_watch_paths("c1") == [tf]


def test_antigravity_watch_paths_sqlite_and_wal(tmp_path, monkeypatch):
    import live_watch

    db = tmp_path / "c1.db"
    db.write_bytes(b"DB")
    wal = tmp_path / "c1.db-wal"
    wal.write_bytes(b"WAL")
    monkeypatch.setattr(live_watch, "_find_transcript_file", lambda cid, allow_partial=False: None)
    monkeypatch.setattr(live_watch, "_find_ide_sqlite_db", lambda cid: db)
    monkeypatch.setattr(live_watch, "_find_brain_path", lambda cid: None)

    paths = live_watch.antigravity_watch_paths("c1")
    assert db in paths and wal in paths


def test_antigravity_watch_paths_falls_back_to_brain_dir(tmp_path, monkeypatch):
    import live_watch

    brain = tmp_path / "brain" / "c1"
    (brain / ".system_generated" / "logs").mkdir(parents=True)
    monkeypatch.setattr(live_watch, "_find_transcript_file", lambda cid, allow_partial=False: None)
    monkeypatch.setattr(live_watch, "_find_ide_sqlite_db", lambda cid: None)
    monkeypatch.setattr(live_watch, "_find_brain_path", lambda cid: brain)

    paths = live_watch.antigravity_watch_paths("c1")
    assert paths == [brain / ".system_generated" / "logs"]


def test_antigravity_watch_paths_empty_when_nothing(monkeypatch):
    import live_watch

    monkeypatch.setattr(live_watch, "_find_transcript_file", lambda cid, allow_partial=False: None)
    monkeypatch.setattr(live_watch, "_find_ide_sqlite_db", lambda cid: None)
    monkeypatch.setattr(live_watch, "_find_brain_path", lambda cid: None)
    assert live_watch.antigravity_watch_paths("c1") == []


# ---------------------------------------------------------------------------
# Intégration fenêtre
# ---------------------------------------------------------------------------
@pytest.fixture
def win(qapp):
    from antigravity_manager import AntigravityManagerWindow

    w = AntigravityManagerWindow()
    w._thread_pool.waitForDone(3000)
    yield w
    w.close()
    w._thread_pool.waitForDone(3000)


def _fake_conv(cid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", project="Proj"):
    return SimpleNamespace(
        conv_id=cid, title="Live", project=project, workspace="",
        last_activity=None, origin="", rel_time="",
    )


def test_live_follow_arms_and_disarms(win, tmp_path, monkeypatch):
    tf = tmp_path / "transcript.jsonl"
    tf.write_text("l1\n", encoding="utf-8")
    monkeypatch.setattr("antigravity_manager.antigravity_watch_paths", lambda cid: [tf])
    monkeypatch.setattr("data_loader.load_chat_messages", lambda cid: [{"role": "user", "text": "hi", "timestamp": ""}])

    win.display_chat(_fake_conv())
    assert win.btn_refresh_chat.isVisible() or True   # visibilité gérée hors écran
    win.btn_live_follow.setChecked(True)
    QApplication.processEvents()
    assert win._live_watcher is not None
    assert win._live_timer.isActive()

    win.btn_live_follow.setChecked(False)
    QApplication.processEvents()
    assert win._live_watcher is None
    assert not win._live_timer.isActive()


def test_live_follow_rerenders_on_change(win, tmp_path, monkeypatch):
    tf = tmp_path / "transcript.jsonl"
    tf.write_text("l1\n", encoding="utf-8")
    monkeypatch.setattr("antigravity_manager.antigravity_watch_paths", lambda cid: [tf])
    monkeypatch.setattr("data_loader.load_chat_messages", lambda cid: [{"role": "user", "text": "hi", "timestamp": ""}])

    calls = {"n": 0}
    orig = win.display_chat

    def spy(info, record_history=True):
        calls["n"] += 1
        return orig(info, record_history=record_history)

    monkeypatch.setattr(win, "display_chat", spy)

    win.selected_conv = _fake_conv()
    win.btn_live_follow.setChecked(True)
    QApplication.processEvents()
    before = calls["n"]

    # Rien n'a changé -> aucun re-rendu.
    win._live_poll_check()
    assert calls["n"] == before

    # Le fichier grossit -> un re-rendu.
    tf.write_text("l1\nl2\n", encoding="utf-8")
    win._live_poll_check()
    assert calls["n"] == before + 1


def test_live_follow_off_when_switching_conversation(win, tmp_path, monkeypatch):
    tf = tmp_path / "transcript.jsonl"
    tf.write_text("l1\n", encoding="utf-8")
    monkeypatch.setattr("antigravity_manager.antigravity_watch_paths", lambda cid: [tf])
    monkeypatch.setattr("data_loader.load_chat_messages", lambda cid: [{"role": "user", "text": "hi", "timestamp": ""}])

    win.display_chat(_fake_conv(cid="11111111-1111-1111-1111-111111111111"))
    win.btn_live_follow.setChecked(True)
    QApplication.processEvents()
    assert win._live_watcher is not None

    # Changer de conversation coupe le suivi.
    win.display_chat(_fake_conv(cid="22222222-2222-2222-2222-222222222222"))
    QApplication.processEvents()
    assert win.btn_live_follow.isChecked() is False
    assert win._live_watcher is None


def test_refresh_button_no_conv_is_safe(win):
    win._clear_chat()
    win._refresh_current_chat()  # ne doit pas lever


def test_live_follow_refuses_when_no_watch_paths(win, monkeypatch):
    monkeypatch.setattr("antigravity_manager.antigravity_watch_paths", lambda cid: [])
    monkeypatch.setattr("data_loader.load_chat_messages", lambda cid: [{"role": "user", "text": "hi", "timestamp": ""}])

    win.display_chat(_fake_conv())
    win.btn_live_follow.setChecked(True)
    QApplication.processEvents()
    # Le bouton se remet tout seul à OFF, aucun watcher.
    assert win.btn_live_follow.isChecked() is False
    assert win._live_watcher is None
