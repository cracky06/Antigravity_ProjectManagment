"""test_export_md.py — Export Markdown d'une conversation (v2.0)."""

import datetime
from pathlib import Path

import pytest

import data_loader as dl


@pytest.fixture
def stub_conv(monkeypatch):
    """Neutralise l'accès disque : messages + infos + brain sont mockés."""
    messages = [
        {"role": "user", "text": "Analyse le projet stp.", "timestamp": "02/09 21:36"},
        {"role": "model", "text": "## Analyse\n\nVoici le **détail**.", "timestamp": "02/09 21:37"},
    ]
    monkeypatch.setattr(dl, "load_chat_messages", lambda cid: list(messages))
    monkeypatch.setattr(
        dl, "get_transcript_info",
        lambda cid: ("Analyse du projet", datetime.datetime(2026, 9, 2, 21, 37)),
    )
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: None)
    return messages


def test_markdown_has_header_and_messages(stub_conv):
    md = dl.build_conversation_markdown(
        "c8557093-604a-4bf1-a6df-87200f4f69a8",
        title="bugs & features:",
        project="MonProjet",
    )
    assert md.startswith("# bugs & features:")
    assert "**Projet :** MonProjet" in md
    assert "`c8557093-604a-4bf1-a6df-87200f4f69a8`" in md
    assert "### 👤 Utilisateur" in md
    assert "### ✨ Antigravity" in md
    assert "Voici le **détail**." in md


def test_markdown_no_messages(monkeypatch):
    monkeypatch.setattr(dl, "load_chat_messages", lambda cid: [])
    monkeypatch.setattr(dl, "get_transcript_info", lambda cid: ("T", None))
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: None)
    md = dl.build_conversation_markdown("cid", title="", project="")
    assert "Aucun message textuel" in md
    assert "**Projet :** (aucun)" in md


def test_markdown_includes_artifacts(monkeypatch, tmp_path):
    (tmp_path / "walkthrough.md").write_text("# WT\n\nRésumé.", encoding="utf-8")
    (tmp_path / "task.md").write_text("Faire X.", encoding="utf-8")
    monkeypatch.setattr(dl, "load_chat_messages", lambda cid: [{"role": "user", "text": "x", "timestamp": ""}])
    monkeypatch.setattr(dl, "get_transcript_info", lambda cid: ("T", None))
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: tmp_path)

    md = dl.build_conversation_markdown("cid", title="T", project="P")
    assert "## Annexe — Artéfacts de session" in md
    assert "Walkthrough & Synthèse" in md and "Résumé." in md
    assert "Tâche" in md and "Faire X." in md
    # implementation_plan.md absent -> pas de section
    assert "Plan d'implémentation" not in md


def test_default_export_filename(stub_conv):
    name = dl.default_export_filename(
        "c8557093-604a-4bf1-a6df-87200f4f69a8", "bugs & features:"
    )
    assert name == "20260902_bugs-features_c8557093.md"
    assert name.endswith(".md")


def test_slugify_edge_cases():
    assert dl._slugify("") == "conversation"
    assert dl._slugify("   ") == "conversation"
    assert dl._slugify("Héllo / World: test!") == "Héllo-World-test"
    assert len(dl._slugify("x" * 200)) <= 60


def test_export_to_path_creates_parents(stub_conv, tmp_path):
    out = tmp_path / "a" / "b" / "conv.md"
    ok, res = dl.export_conversation_to_path("cid", out, title="T", project="P")
    assert ok is True
    assert out.is_file()
    assert res == str(out)
    assert out.read_text(encoding="utf-8").startswith("# T")


def test_export_to_project_layout(stub_conv, tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "get_projects_root", lambda: tmp_path)
    ok, res = dl.export_conversation_to_project(
        "c8557093-604a-4bf1-a6df-87200f4f69a8", "MonProjet", title="bugs & features:"
    )
    assert ok is True
    p = Path(res.split(" (+")[0])  # res peut contenir un suffixe « (+N images) »
    assert p.parent == tmp_path / "MonProjet" / "_conversations"
    assert p.name == "20260902_bugs-features_c8557093.md"
    assert p.is_file()


def test_export_to_path_reports_failure(stub_conv, monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("disque plein")

    monkeypatch.setattr(dl, "build_conversation_markdown", boom)
    ok, msg = dl.export_conversation_to_path("cid", tmp_path / "x.md")
    assert ok is False
    assert "Échec de l'export" in msg


# ---------------------------------------------------------------------------
# Images de session
# ---------------------------------------------------------------------------
@pytest.fixture
def brain_with_images(tmp_path):
    """Un dossier brain fictif : 1 image générée, 1 temp, 1 uploadée."""
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "gen_logo_1.jpg").write_bytes(b"JPG-GEN")
    (brain / ".tempmediaStorage").mkdir()
    (brain / ".tempmediaStorage" / "media_tmp.png").write_bytes(b"PNG-TMP")
    (brain / ".user_uploaded").mkdir()
    (brain / ".user_uploaded" / "reference.png").write_bytes(b"PNG-REF")
    return brain


def test_collect_session_images_order(brain_with_images):
    got = dl._collect_session_images(brain_with_images)
    labels = [lbl for lbl, _p in got]
    names = [p.name for _lbl, p in got]
    assert names == ["gen_logo_1.jpg", "media_tmp.png", "reference.png"]
    assert labels == [
        "Images générées",
        "Médias temporaires",
        "Images fournies par l'utilisateur",
    ]


def test_copy_session_images_creates_files_and_relpaths(brain_with_images, tmp_path):
    dest = tmp_path / "out_images"
    rels = dl._copy_session_images(brain_with_images, dest)
    assert {Path(r).name for _l, r in rels} == {
        "gen_logo_1.jpg", "media_tmp.png", "reference.png"
    }
    assert all(r.startswith("out_images/") for _l, r in rels)
    assert (dest / "gen_logo_1.jpg").read_bytes() == b"JPG-GEN"
    assert (dest / "reference.png").read_bytes() == b"PNG-REF"


def test_copy_session_images_name_collision(tmp_path):
    brain = tmp_path / "brain"
    (brain / ".tempmediaStorage").mkdir(parents=True)
    (brain / ".user_uploaded").mkdir(parents=True)
    (brain / ".tempmediaStorage" / "media.png").write_bytes(b"A")
    (brain / ".user_uploaded" / "media.png").write_bytes(b"B")
    dest = tmp_path / "imgs"
    rels = dl._copy_session_images(brain, dest)
    names = sorted(Path(r).name for _l, r in rels)
    assert names == ["media.png", "media_2.png"]
    assert (dest / "media.png").is_file() and (dest / "media_2.png").is_file()


def test_export_includes_images_section(stub_conv, brain_with_images, monkeypatch, tmp_path):
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain_with_images)
    out = tmp_path / "conv.md"
    ok, res = dl.export_conversation_to_path("cid", out, title="T", project="P")
    assert ok is True
    assert "+3 image" in res
    md = out.read_text(encoding="utf-8")
    assert "## Images" in md
    assert "![gen_logo_1.jpg](conv_images/gen_logo_1.jpg)" in md
    assert "![reference.png](conv_images/reference.png)" in md
    assert (out.parent / "conv_images" / "media_tmp.png").is_file()


def test_build_markdown_lists_images_when_no_copy(stub_conv, brain_with_images, monkeypatch):
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain_with_images)
    md = dl.build_conversation_markdown("cid", title="T", project="P")  # images=None
    assert "## Images" in md
    assert "🖼️ `gen_logo_1.jpg`" in md
    assert "non copiées" in md
