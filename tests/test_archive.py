"""test_archive.py — Archivage incrémental des conversations (archive.py)."""

import json
import zipfile
from types import SimpleNamespace

import pytest

import archive


# ---------------------------------------------------------------------------
# Fixture : arborescence .gemini/ + racine projets, toutes deux redirigées
# ---------------------------------------------------------------------------
@pytest.fixture
def env(tmp_path, monkeypatch):
    gemini = tmp_path / ".gemini"
    ide = gemini / "antigravity-ide"
    (ide / "conversations").mkdir(parents=True)
    (ide / "brain").mkdir(parents=True)
    projects_root = tmp_path / "DEV"
    projects_root.mkdir()

    monkeypatch.setattr(archive, "get_projects_root", lambda: projects_root)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: ide)
    monkeypatch.setattr("data_loader.get_projects_root", lambda: projects_root)
    # L'export Markdown dépend du transcript ; on le neutralise pour ces tests
    # (il est testé ailleurs) et on vérifie juste qu'il est bien appelé.
    calls = {"export": 0}

    def fake_md(conv_id, title="", project="", images=None):
        calls["export"] += 1
        return f"# {title or conv_id}\n"

    monkeypatch.setattr(archive, "build_conversation_markdown", fake_md)

    def make_conv(conv_id, project, *, db_body=b"DB", brain_files=None):
        (ide / "conversations" / f"{conv_id}.db").write_bytes(db_body)
        bdir = ide / "brain" / conv_id
        bdir.mkdir(parents=True, exist_ok=True)
        for rel, body in (brain_files or {"task.md": "tâche"}).items():
            p = bdir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(body, bytes):
                p.write_bytes(body)
            else:
                p.write_text(body, encoding="utf-8")
        return SimpleNamespace(conv_id=conv_id, title=f"Titre {conv_id}", project=project)

    return SimpleNamespace(
        projects_root=projects_root, ide=ide, make_conv=make_conv, calls=calls
    )


def _archive_dir(env, project):
    return env.projects_root / project / archive.ARCHIVE_DIRNAME


# ---------------------------------------------------------------------------
def test_first_run_archives_every_project(env):
    convs = [
        env.make_conv("aaaa-1", "PlayVibe"),
        env.make_conv("bbbb-2", "PlayVibe"),
        env.make_conv("cccc-3", "Comfyui"),
    ]
    summary = archive.archive_all(convs)

    assert summary["PlayVibe"]["updated"] == 2
    assert summary["Comfyui"]["updated"] == 1

    pv = _archive_dir(env, "PlayVibe")
    assert (pv / "conversations.zip").is_file()
    assert (pv / "store" / "aaaa-1" / "aaaa-1.db").read_bytes() == b"DB"
    assert (pv / "store" / "aaaa-1" / "aaaa-1.md").is_file()          # export MD appelé
    assert (pv / "store" / "aaaa-1" / "brain" / "task.md").is_file()

    names = zipfile.ZipFile(pv / "conversations.zip").namelist()
    assert "aaaa-1/aaaa-1.db" in names and "bbbb-2/brain/task.md" in names


def test_second_run_is_noop_when_nothing_changed(env):
    convs = [env.make_conv("aaaa-1", "PlayVibe")]
    archive.archive_all(convs)
    zip_mtime = (_archive_dir(env, "PlayVibe") / "conversations.zip").stat().st_mtime_ns

    summary = archive.archive_all(convs)
    assert summary["PlayVibe"]["updated"] == 0
    # Le zip n'a pas été réécrit.
    assert (_archive_dir(env, "PlayVibe") / "conversations.zip").stat().st_mtime_ns == zip_mtime


def test_only_modified_project_is_rearchived(env):
    a = env.make_conv("aaaa-1", "PlayVibe")
    b = env.make_conv("cccc-3", "Comfyui")
    archive.archive_all([a, b])

    cf_zip = _archive_dir(env, "Comfyui") / "conversations.zip"
    cf_mtime = cf_zip.stat().st_mtime_ns

    # Modifier seulement la conv de PlayVibe (taille du .db change).
    (env.ide / "conversations" / "aaaa-1.db").write_bytes(b"DB-MODIFIED-LONGER")

    summary = archive.archive_all([a, b])
    assert summary["PlayVibe"]["updated"] == 1
    assert summary["Comfyui"]["updated"] == 0
    # Zip de Comfyui intact.
    assert cf_zip.stat().st_mtime_ns == cf_mtime
    # Nouveau contenu dans le store de PlayVibe.
    assert (
        _archive_dir(env, "PlayVibe") / "store" / "aaaa-1" / "aaaa-1.db"
    ).read_bytes() == b"DB-MODIFIED-LONGER"


def test_images_are_excluded_from_archive(env):
    conv = env.make_conv(
        "img-1",
        "PlayVibe",
        brain_files={
            "task.md": "tâche",
            "screenshot.png": b"\x89PNG fake",
            "diagram.jpg": b"JPEG fake",
        },
    )
    archive.archive_all([conv])

    store = _archive_dir(env, "PlayVibe") / "store" / "img-1" / "brain"
    assert (store / "task.md").is_file()
    assert not (store / "screenshot.png").exists()
    assert not (store / "diagram.jpg").exists()


def test_disappeared_conversation_is_never_removed(env):
    conv = env.make_conv("keep-me", "PlayVibe")
    archive.archive_all([conv])
    assert (_archive_dir(env, "PlayVibe") / "store" / "keep-me" / "keep-me.db").is_file()

    # La conversation disparaît d'Antigravity ET de la liste passée à archive_all.
    (env.ide / "conversations" / "keep-me.db").unlink()
    import shutil as _sh
    _sh.rmtree(env.ide / "brain" / "keep-me")

    other = env.make_conv("other", "PlayVibe")
    archive.archive_all([other])

    # keep-me reste dans le store ET dans le zip.
    assert (_archive_dir(env, "PlayVibe") / "store" / "keep-me" / "keep-me.db").is_file()
    names = zipfile.ZipFile(_archive_dir(env, "PlayVibe") / "conversations.zip").namelist()
    assert any(n.startswith("keep-me/") for n in names)


def test_archived_conv_kept_when_sources_vanish_but_still_listed(env):
    """Sources disparues mais conv encore passée à archive_all : la copie
    déjà archivée ne doit PAS être écrasée/vidée."""
    conv = env.make_conv("vanish-1", "PlayVibe", brain_files={"task.md": "important"})
    archive.archive_all([conv])
    store_conv = _archive_dir(env, "PlayVibe") / "store" / "vanish-1"
    assert (store_conv / "vanish-1.db").read_bytes() == b"DB"
    assert (store_conv / "brain" / "task.md").read_text(encoding="utf-8") == "important"

    # Les fichiers source disparaissent, mais la conv reste dans la liste.
    (env.ide / "conversations" / "vanish-1.db").unlink()
    import shutil as _sh
    _sh.rmtree(env.ide / "brain" / "vanish-1")

    summary = archive.archive_all([conv])
    assert summary["PlayVibe"]["updated"] == 0
    # La copie archivée est toujours là, intacte.
    assert (store_conv / "vanish-1.db").read_bytes() == b"DB"
    assert (store_conv / "brain" / "task.md").read_text(encoding="utf-8") == "important"


def test_no_project_conversations_go_to_bucket(env):
    conv = env.make_conv("orphan-1", "")
    summary = archive.archive_all([conv])

    assert archive.NO_PROJECT_BUCKET in summary
    bucket_dir = env.projects_root / archive.NO_PROJECT_BUCKET / archive.ARCHIVE_DIRNAME
    assert (bucket_dir / "store" / "orphan-1" / "orphan-1.db").is_file()


def test_manifest_tracks_signatures(env):
    conv = env.make_conv("sig-1", "PlayVibe")
    archive.archive_all([conv])

    mf = json.loads((_archive_dir(env, "PlayVibe") / "manifest.json").read_text(encoding="utf-8"))
    assert "sig-1" in mf
    assert "sig-1.db" in mf["sig-1"]
    mtime_ns, size = mf["sig-1"]["sig-1.db"]
    assert size == 2  # len(b"DB")
    assert isinstance(mtime_ns, int)


def test_db_sidecars_are_archived(env):
    conv = env.make_conv("wal-1", "PlayVibe")
    (env.ide / "conversations" / "wal-1.db-wal").write_bytes(b"WAL")
    (env.ide / "conversations" / "wal-1.db-shm").write_bytes(b"SHM")

    archive.archive_all([conv])
    store = _archive_dir(env, "PlayVibe") / "store" / "wal-1"
    assert (store / "wal-1.db-wal").read_bytes() == b"WAL"
    assert (store / "wal-1.db-shm").read_bytes() == b"SHM"
