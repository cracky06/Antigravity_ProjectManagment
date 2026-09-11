"""test_claude_retention.py — Détection des conversations Claude Code proches
de la purge automatique (claude_retention.py) et son intégration dans l'arbre.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# claude_retention.py — logique pure
# ---------------------------------------------------------------------------
def test_get_retention_days_default_when_absent(tmp_path, monkeypatch):
    import claude_retention as cr

    monkeypatch.setattr(cr, "_claude_settings_path", lambda: tmp_path / "absent.json")
    assert cr.get_retention_days() == cr.DEFAULT_RETENTION_DAYS == 30


def test_get_retention_days_reads_settings(tmp_path, monkeypatch):
    import claude_retention as cr

    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"cleanupPeriodDays": 90}), encoding="utf-8")
    monkeypatch.setattr(cr, "_claude_settings_path", lambda: f)
    assert cr.get_retention_days() == 90


def test_get_retention_days_falls_back_on_invalid_value(tmp_path, monkeypatch):
    import claude_retention as cr

    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"cleanupPeriodDays": 0}), encoding="utf-8")
    monkeypatch.setattr(cr, "_claude_settings_path", lambda: f)
    assert cr.get_retention_days() == cr.DEFAULT_RETENTION_DAYS

    f.write_text("{not json", encoding="utf-8")
    assert cr.get_retention_days() == cr.DEFAULT_RETENTION_DAYS


def test_days_until_purge_and_is_near_expiry():
    import claude_retention as cr

    now = datetime(2026, 9, 11, 12, 0)

    assert cr.days_until_purge(None, 30, now=now) is None
    assert cr.is_near_expiry(None, 30, now=now) is False

    fresh = now - timedelta(days=2)
    assert cr.days_until_purge(fresh, 30, now=now) == 28
    assert cr.is_near_expiry(fresh, 30, now=now) is False

    near = now - timedelta(days=25)  # 5 j restants, marge 7 -> alerte
    assert cr.days_until_purge(near, 30, now=now) == 5
    assert cr.is_near_expiry(near, 30, now=now) is True

    boundary = now - timedelta(days=23)  # exactement 7 j restants -> alerte (<=)
    assert cr.days_until_purge(boundary, 30, now=now) == 7
    assert cr.is_near_expiry(boundary, 30, now=now) is True

    overdue = now - timedelta(days=40)  # purge théorique déjà passée
    assert cr.days_until_purge(overdue, 30, now=now) < 0
    assert cr.is_near_expiry(overdue, 30, now=now) is True


def test_is_near_expiry_custom_margin():
    import claude_retention as cr

    now = datetime(2026, 9, 11, 12, 0)
    conv_dt = now - timedelta(days=27)  # 3 j restants
    assert cr.is_near_expiry(conv_dt, 30, warning_margin_days=1, now=now) is False
    assert cr.is_near_expiry(conv_dt, 30, warning_margin_days=7, now=now) is True


# ---------------------------------------------------------------------------
# Intégration dans l'arbre (AntigravityManagerWindow, source Claude Code)
# ---------------------------------------------------------------------------
@pytest.fixture
def win(qapp):
    from antigravity_manager import AntigravityManagerWindow

    w = AntigravityManagerWindow()
    w._thread_pool.waitForDone(3000)
    yield w
    w.close()
    w._thread_pool.waitForDone(3000)


def _fake_claude_conv(cid, project, days_ago, title="Conv"):
    return SimpleNamespace(
        conv_id=cid, project=project, path=None, title=title,
        last_dt=datetime.now() - timedelta(days=days_ago),
        entrypoints=set(), project_root=None, origin_label="",
    )


def _select_all_projects(win):
    win.project_filter_combo.blockSignals(True)
    win.project_filter_combo.clear()
    win.project_filter_combo.addItem("Tous les projets", "ALL")
    win.project_filter_combo.setCurrentIndex(0)
    win.project_filter_combo.blockSignals(False)


def test_expiring_section_appears_first_and_only_lists_expiring(win, monkeypatch):
    old_conv = _fake_claude_conv("11111111-1111-1111-1111-111111111111", "ProjA", 25)
    fresh_conv = _fake_claude_conv("22222222-2222-2222-2222-222222222222", "ProjA", 2)
    win.claude_project_map = {"ProjA": [old_conv, fresh_conv]}
    win._active_source = "claude_code"
    monkeypatch.setattr("antigravity_manager.get_retention_days", lambda: 30)

    _select_all_projects(win)
    win._populate_tree()

    first = win.tree.topLevelItem(0)
    assert first.text(0).startswith("⏳ EXPIRENT BIENTÔT")
    assert "(1)" in first.text(0)
    assert first.childCount() == 1
    dtype, c_info = first.child(0).data(0, Qt.ItemDataRole.UserRole)
    assert dtype == "claude_conv"
    assert c_info.conv_id == old_conv.conv_id


def test_expiring_conv_colored_and_no_section_when_none_expiring(win, monkeypatch):
    from PyQt6.QtGui import QColor

    fresh_conv = _fake_claude_conv("33333333-3333-3333-3333-333333333333", "ProjA", 1)
    win.claude_project_map = {"ProjA": [fresh_conv]}
    win._active_source = "claude_code"
    monkeypatch.setattr("antigravity_manager.get_retention_days", lambda: 30)

    _select_all_projects(win)
    win._populate_tree()

    top_labels = [win.tree.topLevelItem(i).text(0) for i in range(win.tree.topLevelItemCount())]
    assert not any(t.startswith("⏳") for t in top_labels)


def test_expiring_section_visible_when_project_filtered(win, monkeypatch):
    old_conv = _fake_claude_conv("44444444-4444-4444-4444-444444444444", "ProjA", 28)
    win.claude_project_map = {"ProjA": [old_conv]}
    win._active_source = "claude_code"
    monkeypatch.setattr("antigravity_manager.get_retention_days", lambda: 30)

    win.project_filter_combo.blockSignals(True)
    win.project_filter_combo.clear()
    win.project_filter_combo.addItem("ProjA", "ProjA")
    win.project_filter_combo.setCurrentIndex(0)
    win.project_filter_combo.blockSignals(False)
    win._populate_tree()

    first = win.tree.topLevelItem(0)
    assert first.text(0).startswith("⏳ EXPIRENT BIENTÔT")


def test_chat_meta_shows_expiry_warning(win, monkeypatch):
    conv = _fake_claude_conv("55555555-5555-5555-5555-555555555555", "ProjA", 26)
    monkeypatch.setattr("antigravity_manager.get_retention_days", lambda: 30)
    monkeypatch.setattr("antigravity_manager.load_claude_messages", lambda path: [
        {"role": "user", "text": "hi", "timestamp": ""}
    ])

    win.display_claude_chat(conv)
    assert "purge Claude Code dans" in win.chat_meta.text()


def test_chat_meta_no_warning_when_fresh(win, monkeypatch):
    conv = _fake_claude_conv("66666666-6666-6666-6666-666666666666", "ProjA", 1)
    monkeypatch.setattr("antigravity_manager.get_retention_days", lambda: 30)
    monkeypatch.setattr("antigravity_manager.load_claude_messages", lambda path: [
        {"role": "user", "text": "hi", "timestamp": ""}
    ])

    win.display_claude_chat(conv)
    assert "purge Claude Code" not in win.chat_meta.text()
