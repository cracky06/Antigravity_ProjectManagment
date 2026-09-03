"""test_v22_features.py — v2.2 : liens portables dans l'export, indexation au
fil de l'eau, crash hooks."""

import pytest

import data_loader as dl
import search_index as si


# ---------------------------------------------------------------------------
# #5 — _sanitize_message_text : liens fichiers portables
# ---------------------------------------------------------------------------
def test_sanitize_link_under_project_becomes_relative():
    from pathlib import Path

    txt = "Voir [config.py](file:///E:/Dev/Proj/config.py) et [u](file:///E:/Dev/Proj/src/u.py)."
    out = dl._sanitize_message_text(txt, Path("E:/Dev/Proj"))
    assert "[config.py](config.py)" in out
    assert "[u](src/u.py)" in out
    assert "file:///" not in out


def test_sanitize_link_outside_project_becomes_code():
    from pathlib import Path

    txt = "Regarde [autre.py](file:///C:/Windows/autre.py)."
    out = dl._sanitize_message_text(txt, Path("E:/Dev/Proj"))
    assert "`autre.py`" in out
    assert "file:///" not in out


def test_sanitize_leaves_web_links_intact():
    from pathlib import Path

    txt = "Doc [ici](https://example.com/x) et mail [c](mailto:a@b.c)."
    out = dl._sanitize_message_text(txt, Path("E:/Dev/Proj"))
    assert out == txt


def test_sanitize_handles_backslash_paths():
    from pathlib import Path

    txt = r"[x](C:\Users\Manu\Proj\file.txt)"
    out = dl._sanitize_message_text(txt, Path("C:/Users/Manu/Proj"))
    assert out == "[x](file.txt)"


def test_sanitize_noop_without_links():
    from pathlib import Path

    assert dl._sanitize_message_text("juste du texte", Path("E:/x")) == "juste du texte"
    assert dl._sanitize_message_text("", None) == ""


def test_export_sanitizes_links(stub_conv_with_link, tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "get_projects_root", lambda: tmp_path)
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: None)
    ok, res = dl.export_conversation_to_project("cid", "MonProjet", title="T")
    assert ok
    from pathlib import Path

    md = Path(res.split(" (+")[0]).read_text(encoding="utf-8")
    assert "[config.py](config.py)" in md
    assert "file:///" not in md


@pytest.fixture
def stub_conv_with_link(monkeypatch, tmp_path):
    import datetime

    monkeypatch.setattr(
        dl, "load_chat_messages",
        lambda cid: [
            {
                "role": "model",
                "text": f"Modifie [config.py](file:///{tmp_path.as_posix()}/MonProjet/config.py).",
                "timestamp": "10:00",
                "epoch": 0.0,
            }
        ],
    )
    monkeypatch.setattr(dl, "get_transcript_info", lambda cid: ("T", datetime.datetime(2026, 1, 1)))
    return None


# ---------------------------------------------------------------------------
# #4 — search_index.touch_conversation : indexation au fil de l'eau
# ---------------------------------------------------------------------------
@pytest.fixture
def stub_index_body(monkeypatch):
    bodies = {"c1": "contenu initial de la conversation c1"}
    mtimes = {"c1": 100.0}
    monkeypatch.setattr(si, "_concat_body", lambda cid: bodies.get(cid, ""))
    monkeypatch.setattr(si, "_transcript_mtime", lambda cid: mtimes.get(cid, 0.0))
    return bodies, mtimes


def test_touch_conversation_indexes_new(stub_index_body):
    bodies, _m = stub_index_body
    assert si.touch_conversation("c1", project="P", title="T") is True
    assert si.search_substring("initial") == {"c1"}
    si.close_thread_connection()


def test_touch_conversation_skips_unchanged(stub_index_body):
    assert si.touch_conversation("c1") is True
    assert si.touch_conversation("c1") is False  # mtime inchangé
    si.close_thread_connection()


def test_touch_conversation_reindexes_on_change(stub_index_body):
    bodies, mtimes = stub_index_body
    si.touch_conversation("c1")
    bodies["c1"] = "nouveau contenu avec le mot licorne"
    mtimes["c1"] = 200.0
    assert si.touch_conversation("c1") is True
    assert si.search_substring("licorne") == {"c1"}
    assert si.search_substring("initial") == set()
    si.close_thread_connection()


def test_touch_conversation_survives_errors(monkeypatch):
    def boom(_cid):
        raise RuntimeError("transcript illisible")

    monkeypatch.setattr(si, "_concat_body", boom)
    monkeypatch.setattr(si, "_transcript_mtime", lambda cid: 1.0)
    assert si.touch_conversation("cX") is False  # ne lève pas
    si.close_thread_connection()


# ---------------------------------------------------------------------------
# #6 — hooks de crash
# ---------------------------------------------------------------------------
def test_crash_log_append(monkeypatch, tmp_path):
    import antigravity_manager as am

    log = tmp_path / "crash.log"
    monkeypatch.setattr(am, "_crash_log_path", lambda: log)
    am._append_crash_log("TEST A", "corps A")
    am._append_crash_log("TEST B", "corps B")
    content = log.read_text(encoding="utf-8")
    assert "TEST A" in content and "corps A" in content
    assert "TEST B" in content and "corps B" in content
    # append, pas écrasement
    assert content.index("TEST A") < content.index("TEST B")


def test_install_excepthooks_sets_sys_hook(monkeypatch):
    import sys
    import antigravity_manager as am

    original = sys.excepthook
    try:
        am._install_global_excepthooks()
        assert sys.excepthook is not original
    finally:
        sys.excepthook = original
