"""test_conv_labels.py — Détection de dialogue et libellé des conversations (v2.0)."""

import pytest

import data_loader as dl


@pytest.fixture(autouse=True)
def clear_caches():
    dl._DIALOGUE_CACHE.clear()
    yield
    dl._DIALOGUE_CACHE.clear()


def _make_transcript(tmp_path, name, content):
    logs = tmp_path / name / ".system_generated" / "logs"
    logs.mkdir(parents=True)
    f = logs / "transcript.jsonl"
    f.write_text(content, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# conversation_has_dialogue
# ---------------------------------------------------------------------------
def test_has_dialogue_true_on_user_input(tmp_path, monkeypatch):
    f = _make_transcript(
        tmp_path, "c1",
        '{"type":"USER_INPUT","source":"USER_EXPLICIT","content":"salut"}\n',
    )
    monkeypatch.setattr(dl, "_find_transcript_file", lambda cid: f)
    assert dl.conversation_has_dialogue("c1") is True


def test_has_dialogue_true_on_planner_response(tmp_path, monkeypatch):
    f = _make_transcript(tmp_path, "c1", '{"type":"PLANNER_RESPONSE","source":"MODEL"}\n')
    monkeypatch.setattr(dl, "_find_transcript_file", lambda cid: f)
    assert dl.conversation_has_dialogue("c1") is True


def test_has_dialogue_false_on_technical_transcript(tmp_path, monkeypatch):
    f = _make_transcript(tmp_path, "c2", '{"type":"TOOL_CALL","name":"read"}\n{"type":"TOOL_RESULT"}\n')
    monkeypatch.setattr(dl, "_find_transcript_file", lambda cid: f)
    assert dl.conversation_has_dialogue("c2") is False


def test_has_dialogue_false_when_no_transcript(monkeypatch):
    monkeypatch.setattr(dl, "_find_transcript_file", lambda cid: None)
    assert dl.conversation_has_dialogue("c3") is False


def test_has_dialogue_cached_by_mtime(tmp_path, monkeypatch):
    f = _make_transcript(tmp_path, "c1", '{"type":"TOOL_CALL"}\n')
    monkeypatch.setattr(dl, "_find_transcript_file", lambda cid: f)
    assert dl.conversation_has_dialogue("c1") is False
    # Réécrit AVEC un dialogue mais on garde le même mtime -> cache renvoie False.
    import os
    st = f.stat()
    f.write_text('{"type":"USER_INPUT","source":"USER_EXPLICIT"}\n', encoding="utf-8")
    os.utime(f, (st.st_atime, st.st_mtime))
    assert dl.conversation_has_dialogue("c1") is False  # servi par le cache
    # mtime différent -> re-scan -> True
    os.utime(f, None)
    assert dl.conversation_has_dialogue("c1") is True


# ---------------------------------------------------------------------------
# derive_conv_label
# ---------------------------------------------------------------------------
def test_label_prefers_official_title(monkeypatch):
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: None)
    assert dl.derive_conv_label("abcdef123456", "Mon Titre Officiel") == "Mon Titre Officiel"


def test_label_id_only_when_nothing(monkeypatch):
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: None)
    assert dl.derive_conv_label("abcdef1234567890", "") == "abcdef123456"


def test_label_id_plus_artifact_first_line(tmp_path, monkeypatch):
    (tmp_path / "task.md").write_text("# Refactorer le module X\n\nDétails.", encoding="utf-8")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: tmp_path)
    label = dl.derive_conv_label("abcdef1234567890", "")
    assert label == "abcdef123456 — Refactorer le module X"


def test_label_artifact_priority_task_over_walkthrough(tmp_path, monkeypatch):
    (tmp_path / "task.md").write_text("Tâche prioritaire", encoding="utf-8")
    (tmp_path / "walkthrough.md").write_text("Synthèse secondaire", encoding="utf-8")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: tmp_path)
    assert dl.derive_conv_label("abcdef1234", "").endswith("Tâche prioritaire")


def test_label_skips_empty_lines_in_artifact(tmp_path, monkeypatch):
    (tmp_path / "task.md").write_text("\n\n   \n## Vrai titre\n", encoding="utf-8")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: tmp_path)
    assert dl.derive_conv_label("abcdef1234", "").endswith("Vrai titre")
