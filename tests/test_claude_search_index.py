"""test_claude_search_index.py — Index plein-texte de la source Claude Code
/ Desktop (v2.5).

Fichier d'index redirigé vers `tmp_path` (jamais le vrai `claude_search_index.db`)
et `_concat_body` / `_session_mtime` monkeypatchés — comme test_search_index.py
côté Antigravity, mais entièrement isolé (module séparé, index séparé).
"""

import re

import pytest

import claude_search_index as csi


class _Conv:
    def __init__(self, conv_id, project, title, path="dummy.jsonl"):
        self.conv_id = conv_id
        self.project = project
        self.title = title
        self.path = path


@pytest.fixture(autouse=True)
def isolated_claude_search_index(tmp_path, monkeypatch):
    """Redirige l'index vers un fichier jetable, ferme la connexion entre
    tests (une connexion par thread est mise en cache dans le module)."""
    db_path = tmp_path / "claude_search_index.db"
    monkeypatch.setattr(csi, "get_index_path", lambda: db_path)
    csi.close_thread_connection()
    yield
    csi.close_thread_connection()


@pytest.fixture
def sample_corpus(monkeypatch):
    bodies = {
        "c1": "Le chat mange une pomme rouge.\ndef hello():\n    return 42",
        "c2": "PowerShell : build.ps1 lance Get-ChildItem puis Remove-Item -Force",
        "c3": "Petite régression sur la régularité des requêtes réseau, corrigée.",
        "c4": "Rien à voir : liste de courses, lait, pain, café.",
    }
    mtimes = {cid: 100.0 for cid in bodies}
    monkeypatch.setattr(csi, "_concat_body", lambda path: bodies[path])
    monkeypatch.setattr(csi, "_session_mtime", lambda path: mtimes[path])
    convs = [
        _Conv("c1", "ProjA", "Chat", path="c1"),
        _Conv("c2", "ProjB", "Build", path="c2"),
        _Conv("c3", "ProjA", "Réseau", path="c3"),
        _Conv("c4", "ProjC", "Courses", path="c4"),
    ]
    return convs, bodies, mtimes


def test_rebuild_and_status(sample_corpus):
    convs, _b, _m = sample_corpus
    updated, deleted = csi.rebuild_index(convs)
    assert updated == 4
    assert deleted == 0
    st = csi.check_status()
    assert st.ok is True
    assert st.doc_count == 4


def test_substring_is_case_insensitive(sample_corpus):
    convs, _b, _m = sample_corpus
    csi.rebuild_index(convs)
    assert csi.search_substring("pomme") == {"c1"}
    assert csi.search_substring("POMME") == {"c1"}
    assert csi.search_substring("introuvable-xyz") == set()


def test_words_mode_matches_prefixes_and_diacritics(sample_corpus):
    convs, _b, _m = sample_corpus
    csi.rebuild_index(convs)
    assert csi.search_words("regularite") == {"c3"}
    assert csi.search_words("requ") == {"c3"}
    assert csi.search_words("chat pomme") == {"c1"}
    assert csi.search_words("chat café") == set()


def test_regex_mode(sample_corpus):
    convs, _b, _m = sample_corpus
    csi.rebuild_index(convs)
    assert csi.search_regex(r"def \w+\(\):") == {"c1"}
    assert csi.search_regex(r"(Get|Remove)-\w+") == {"c2"}
    assert csi.search_regex(r"^Rien à voir") == {"c4"}


def test_regex_invalid_raises(sample_corpus):
    convs, _b, _m = sample_corpus
    csi.rebuild_index(convs)
    with pytest.raises(re.error):
        csi.search_regex(r"[unclosed")


def test_scope_restriction(sample_corpus):
    convs, _b, _m = sample_corpus
    csi.rebuild_index(convs)
    got = csi.search_substring("e", conv_ids={"c2", "c4"})
    assert got == {"c2", "c4"}
    got_words = csi.search_words("build", conv_ids={"c1"})
    assert got_words == set()


def test_incremental_sync_updates_changed_and_removes_orphans(sample_corpus):
    convs, bodies, mtimes = sample_corpus
    csi.rebuild_index(convs)

    updated, deleted = csi.sync_index(convs)
    assert (updated, deleted) == (0, 0)

    bodies["c2"] = "nouveau contenu avec le mot licorne"
    mtimes["c2"] = 200.0
    updated, deleted = csi.sync_index(convs)
    assert updated == 1
    assert csi.search_substring("licorne") == {"c2"}
    assert csi.search_substring("PowerShell") == set()

    updated, deleted = csi.sync_index(convs[:3])
    assert deleted == 1
    assert csi.check_status().doc_count == 3


def test_touch_conversation(sample_corpus):
    convs, bodies, mtimes = sample_corpus
    csi.rebuild_index([convs[0]])
    assert csi.check_status().doc_count == 1

    # Rien n'a changé -> pas de mise à jour.
    assert csi.touch_conversation(convs[0]) is False

    # Nouvelle conversation jamais indexée -> mise à jour.
    assert csi.touch_conversation(convs[1]) is True
    assert csi.check_status().doc_count == 2


def test_search_dispatch(sample_corpus):
    convs, _b, _m = sample_corpus
    csi.rebuild_index(convs)
    assert csi.search("pomme", mode="substring") == {"c1"}
    assert csi.search("regularite", mode="words") == {"c3"}
    assert csi.search(r"Get-\w+", mode="regex") == {"c2"}


def test_drop_index(sample_corpus):
    convs, _b, _m = sample_corpus
    csi.rebuild_index(convs)
    assert csi.get_index_path().is_file()
    csi.drop_index()
    assert not csi.get_index_path().is_file()


def test_index_separate_from_antigravity_search_index(tmp_path, monkeypatch):
    """Garde-fou explicite : les deux index ne doivent JAMAIS pointer sur le
    même fichier (deux formats de conv_id/schéma de données différents)."""
    import search_index

    monkeypatch.setattr(search_index, "get_index_path", lambda: tmp_path / "antigravity.db")
    assert csi.get_index_path() != search_index.get_index_path()
    assert csi.get_index_path().name == "claude_search_index.db"
