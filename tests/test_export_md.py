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
    assert {Path(r).name for _l, r, _src in rels} == {
        "gen_logo_1.jpg", "media_tmp.png", "reference.png"
    }
    assert all(r.startswith("out_images/") for _l, r, _src in rels)
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
    names = sorted(Path(r).name for _l, r, _src in rels)
    assert names == ["media.png", "media_2.png"]
    assert (dest / "media.png").is_file() and (dest / "media_2.png").is_file()
    # nom source conservé pour la corrélation
    assert sorted(src for _l, _r, src in rels) == ["media.png", "media.png"]


def test_export_without_generate_image_puts_all_in_final_section(
    stub_conv, brain_with_images, monkeypatch, tmp_path
):
    # Pas de lignes GENERATE_IMAGE dans le transcript -> aucune corrélation
    # -> toutes les images vont dans la section « Images » de fin.
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain_with_images)
    monkeypatch.setattr(dl, "_image_generation_times", lambda cid: {})
    out = tmp_path / "conv.md"
    ok, res = dl.export_conversation_to_path("cid", out, title="T", project="P")
    assert ok is True
    assert "+3 image" in res
    md = out.read_text(encoding="utf-8")
    assert "## Images" in md
    tail = md.split("## Images", 1)[1]
    assert "gen_logo_1.jpg" in tail and "reference.png" in tail
    assert "**Images de cet échange :**" not in md


def test_generate_image_places_image_inline(stub_conv, tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "icone_A.png").write_bytes(b"A")
    (brain / "icone_B.png").write_bytes(b"B")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain)
    monkeypatch.setattr(
        dl, "load_chat_messages",
        lambda cid: [
            {"role": "user", "text": "fais icone A", "timestamp": "t1", "epoch": 1000.0},
            {"role": "model", "text": "voici A", "timestamp": "t2", "epoch": 1010.0},
            {"role": "user", "text": "fais icone B", "timestamp": "t3", "epoch": 2000.0},
            {"role": "model", "text": "voici B", "timestamp": "t4", "epoch": 2010.0},
        ],
    )
    # icone_A générée à 1005 (entre msg0 et msg1), icone_B à 2005 (entre msg2/msg3)
    monkeypatch.setattr(
        dl, "_image_generation_times",
        lambda cid: {"icone_A.png": 1005.0, "icone_B.png": 2005.0},
    )
    out = tmp_path / "c.md"
    dl.export_conversation_to_path("cid", out, title="T", project="P")
    body = out.read_text(encoding="utf-8").splitlines()

    def line_of(substr):
        return next(i for i, l in enumerate(body) if substr in l)

    assert line_of("fais icone A") < line_of("icone_A.png") < line_of("fais icone B")
    assert line_of("fais icone B") < line_of("icone_B.png")
    assert "## Images" not in "\n".join(body)  # tout inline
    assert "(images finales)" not in "\n".join(body)


def test_generate_image_after_last_message_stays_with_it(stub_conv, tmp_path, monkeypatch):
    # Une seule discussion : l'image générée après l'unique message est collée
    # à ce message (pas de « images finales » séparées puisqu'il n'y a rien après).
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "tardive.png").write_bytes(b"X")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain)
    monkeypatch.setattr(
        dl, "load_chat_messages",
        lambda cid: [{"role": "user", "text": "go", "timestamp": "t", "epoch": 100.0}],
    )
    monkeypatch.setattr(dl, "_image_generation_times", lambda cid: {"tardive.png": 999.0})
    out = tmp_path / "c.md"
    dl.export_conversation_to_path("cid", out, title="T", project="P")
    md = out.read_text(encoding="utf-8")
    body = md.splitlines()

    def line_of(s):
        return next(i for i, l in enumerate(body) if s in l)

    assert line_of("go") < line_of("tardive.png")
    assert "## Images" not in md


def test_generate_image_between_middle_and_last_message(stub_conv, tmp_path, monkeypatch):
    # 3 messages ; image générée entre msg1 et msg2 -> après msg1, pas en fin.
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "mid.png").write_bytes(b"X")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain)
    monkeypatch.setattr(
        dl, "load_chat_messages",
        lambda cid: [
            {"role": "user", "text": "un", "timestamp": "t", "epoch": 100.0},
            {"role": "model", "text": "deux", "timestamp": "t", "epoch": 200.0},
            {"role": "user", "text": "trois", "timestamp": "t", "epoch": 300.0},
        ],
    )
    monkeypatch.setattr(dl, "_image_generation_times", lambda cid: {"mid.png": 250.0})
    out = tmp_path / "c.md"
    dl.export_conversation_to_path("cid", out, title="T", project="P")
    body = out.read_text(encoding="utf-8").splitlines()

    def line_of(s):
        return next(i for i, l in enumerate(body) if s in l)

    assert line_of("deux") < line_of("mid.png") < line_of("trois")


def test_undated_image_goes_to_final_section(stub_conv, tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "generee.png").write_bytes(b"A")
    (brain / ".user_uploaded").mkdir()
    (brain / ".user_uploaded" / "reference.png").write_bytes(b"B")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain)
    monkeypatch.setattr(
        dl, "load_chat_messages",
        lambda cid: [{"role": "user", "text": "msg", "timestamp": "t", "epoch": 500.0}],
    )
    # seule "generee.png" a une ligne GENERATE_IMAGE
    monkeypatch.setattr(dl, "_image_generation_times", lambda cid: {"generee.png": 400.0})

    out = tmp_path / "c.md"
    dl.export_conversation_to_path("cid", out, title="T", project="P")
    md = out.read_text(encoding="utf-8")
    assert "## Images" in md
    assert "reference.png" in md.split("## Images", 1)[1]      # non corrélée -> fin
    assert "generee.png" in md.split("## Images", 1)[0]         # corrélée -> inline


def test_build_markdown_lists_images_when_no_copy(stub_conv, brain_with_images, monkeypatch):
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain_with_images)
    md = dl.build_conversation_markdown("cid", title="T", project="P")  # images=None
    assert "## Images" in md
    assert "🖼️ `gen_logo_1.jpg`" in md
    assert "non copiées" in md
