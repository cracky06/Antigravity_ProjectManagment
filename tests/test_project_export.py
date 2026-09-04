"""test_project_export.py — Export & archivage au niveau projet (v2.4)."""

import datetime
import zipfile
from pathlib import Path

import pytest

import data_loader as dl


class _Conv:
    def __init__(self, cid, title=""):
        self.conv_id = cid
        self.title = title


@pytest.fixture
def stub_convs(monkeypatch):
    monkeypatch.setattr(
        dl, "load_chat_messages",
        lambda cid: [
            {"role": "user", "text": f"q {cid}", "timestamp": "10:00", "epoch": 0.0},
            {"role": "model", "text": f"r {cid}", "timestamp": "10:01", "epoch": 0.0},
        ],
    )
    monkeypatch.setattr(
        dl, "get_transcript_info",
        lambda cid: (f"T-{cid}", datetime.datetime(2026, 1, 1)),
    )
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: None)
    return [_Conv("c1", "Titre A"), _Conv("c2", "Titre B"), _Conv("c3")]


# ---------------------------------------------------------------------------
# export_project_conversations
# ---------------------------------------------------------------------------
def test_export_project_default_dir(stub_convs, tmp_path, monkeypatch):
    monkeypatch.setattr(dl, "get_projects_root", lambda: tmp_path)
    ok, fail, dest = dl.export_project_conversations("MonProjet", stub_convs)
    assert (ok, fail) == (3, 0)
    assert dest == tmp_path / "MonProjet" / "_conversations"
    md_files = sorted(p.name for p in dest.glob("*.md"))
    assert md_files == [
        "20260101_T-c3_c3.md",
        "20260101_Titre-A_c1.md",
        "20260101_Titre-B_c2.md",
    ]
    assert (dest / "20260101_Titre-A_c1.md").read_text(encoding="utf-8").startswith("# Titre A")


def test_export_project_custom_dir(stub_convs, tmp_path):
    dest = tmp_path / "ailleurs"
    ok, fail, out = dl.export_project_conversations("P", stub_convs, dest_dir=dest)
    assert (ok, fail) == (3, 0)
    assert out == dest
    assert len(list(dest.glob("*.md"))) == 3


def test_export_project_reports_failures(stub_convs, tmp_path, monkeypatch):
    calls = {"n": 0}

    def flaky(conv_id, out_path, title, project):
        calls["n"] += 1
        if calls["n"] == 2:
            return False, "boom"
        return True, str(out_path)

    monkeypatch.setattr(dl, "_write_export", flaky)
    ok, fail, _dest = dl.export_project_conversations(
        "P", stub_convs, dest_dir=tmp_path / "x"
    )
    assert ok == 2 and fail == 1


def test_export_project_progress_callback(stub_convs, tmp_path):
    seen = []
    dl.export_project_conversations(
        "P", stub_convs, dest_dir=tmp_path / "x",
        progress_cb=lambda i, total, cid: seen.append((i, total, cid)),
    )
    assert [s[0] for s in seen] == [1, 2, 3]
    assert all(s[1] == 3 for s in seen)


# ---------------------------------------------------------------------------
# archive_project
# ---------------------------------------------------------------------------
def test_archive_project_creates_zip(stub_convs, tmp_path):
    zip_path = tmp_path / "arch.zip"
    ok, res = dl.archive_project("MonProjet", stub_convs, zip_path)
    assert ok is True
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = sorted(zf.namelist())
    assert names == [
        "MonProjet/20260101_T-c3_c3.md",
        "MonProjet/20260101_Titre-A_c1.md",
        "MonProjet/20260101_Titre-B_c2.md",
    ]


def test_archive_project_includes_images(stub_convs, tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "img_1.png").write_bytes(b"PNG")
    monkeypatch.setattr(dl, "_find_brain_path", lambda cid: brain)
    monkeypatch.setattr(dl, "_image_generation_times", lambda cid: {})  # -> section fin

    zip_path = tmp_path / "arch.zip"
    ok, _res = dl.archive_project("P", stub_convs[:1], zip_path)
    assert ok
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    assert any(n.endswith(".md") for n in names)
    assert any("_images/img_1.png" in n for n in names)


def test_archive_project_reports_failure(stub_convs, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("disque plein")

    monkeypatch.setattr(dl, "export_project_conversations", boom)
    ok, msg = dl.archive_project("P", stub_convs, tmp_path / "x.zip")
    assert ok is False
    assert "Échec de l'archivage" in msg


def test_archive_project_creates_parent_dirs(stub_convs, tmp_path):
    zip_path = tmp_path / "sub" / "dir" / "arch.zip"
    ok, _res = dl.archive_project("P", stub_convs, zip_path)
    assert ok and zip_path.is_file()
