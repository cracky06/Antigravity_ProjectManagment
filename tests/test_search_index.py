"""test_search_index.py — Couverture du module d'index plein-texte (v1.5).

L'index réel est déjà redirigé vers un fichier jetable par la fixture
`isolated_search_index` de conftest.py. Ici on neutralise en plus l'accès
disque aux transcripts en monkeypatchant `_concat_body` / `_transcript_mtime`.
"""

import re

import pytest

import search_index


class _Conv:
    def __init__(self, conv_id, project, title):
        self.conv_id = conv_id
        self.project = project
        self.title = title


@pytest.fixture
def sample_corpus(monkeypatch):
    bodies = {
        "c1": "Le chat mange une pomme rouge.\ndef hello():\n    return 42",
        "c2": "PowerShell : build.ps1 lance Get-ChildItem puis Remove-Item -Force",
        "c3": "Petite régression sur la régularité des requêtes réseau, corrigée.",
        "c4": "Rien à voir : liste de courses, lait, pain, café.",
    }
    mtimes = {cid: 100.0 for cid in bodies}
    monkeypatch.setattr(search_index, "_concat_body", lambda cid: bodies[cid])
    monkeypatch.setattr(search_index, "_transcript_mtime", lambda cid: mtimes[cid])
    convs = [
        _Conv("c1", "ProjA", "Chat"),
        _Conv("c2", "ProjB", "Build"),
        _Conv("c3", "ProjA", "Réseau"),
        _Conv("c4", "ProjC", "Courses"),
    ]
    return convs, bodies, mtimes


def test_rebuild_and_status(sample_corpus):
    convs, _b, _m = sample_corpus
    updated, deleted = search_index.rebuild_index(convs)
    assert updated == 4
    assert deleted == 0
    st = search_index.check_status()
    assert st.ok is True
    assert st.doc_count == 4


def test_substring_is_case_insensitive(sample_corpus):
    convs, _b, _m = sample_corpus
    search_index.rebuild_index(convs)
    assert search_index.search_substring("pomme") == {"c1"}
    assert search_index.search_substring("POMME") == {"c1"}
    assert search_index.search_substring("introuvable-xyz") == set()


def test_substring_escapes_like_metacharacters(sample_corpus):
    convs, bodies, _m = sample_corpus
    bodies["c1"] = "valeur = 100% garantie"
    search_index.rebuild_index(convs)
    # Le '%' doit être traité littéralement, pas comme joker LIKE.
    assert search_index.search_substring("100%") == {"c1"}
    assert search_index.search_substring("abc%") == set()


def test_words_mode_matches_prefixes_and_diacritics(sample_corpus):
    convs, _b, _m = sample_corpus
    search_index.rebuild_index(convs)
    # 'regularite' (sans accent) doit retrouver 'régularité' (remove_diacritics).
    assert search_index.search_words("regularite") == {"c3"}
    # préfixe : 'requ' -> 'requêtes'
    assert search_index.search_words("requ") == {"c3"}
    # plusieurs termes = ET logique
    assert search_index.search_words("chat pomme") == {"c1"}
    assert search_index.search_words("chat café") == set()


def test_regex_mode(sample_corpus):
    convs, _b, _m = sample_corpus
    search_index.rebuild_index(convs)
    assert search_index.search_regex(r"def \w+\(\):") == {"c1"}
    assert search_index.search_regex(r"(Get|Remove)-\w+") == {"c2"}
    assert search_index.search_regex(r"^Rien à voir") == {"c4"}


def test_regex_invalid_raises(sample_corpus):
    convs, _b, _m = sample_corpus
    search_index.rebuild_index(convs)
    with pytest.raises(re.error):
        search_index.search_regex(r"[unclosed")


def test_scope_restriction(sample_corpus):
    convs, _b, _m = sample_corpus
    search_index.rebuild_index(convs)
    # 'e' est présent partout ; on restreint la portée.
    got = search_index.search_substring("e", conv_ids={"c2", "c4"})
    assert got == {"c2", "c4"}
    got_words = search_index.search_words("build", conv_ids={"c1"})
    assert got_words == set()


def test_incremental_sync_updates_changed_and_removes_orphans(sample_corpus):
    convs, bodies, mtimes = sample_corpus
    search_index.rebuild_index(convs)

    # Rien n'a changé -> 0 mise à jour.
    updated, deleted = search_index.sync_index(convs)
    assert (updated, deleted) == (0, 0)

    # c2 change (mtime + contenu) -> 1 mise à jour.
    bodies["c2"] = "nouveau contenu avec le mot licorne"
    mtimes["c2"] = 200.0
    updated, deleted = search_index.sync_index(convs)
    assert updated == 1
    assert search_index.search_substring("licorne") == {"c2"}
    assert search_index.search_substring("PowerShell") == set()

    # c4 disparaît de la liste -> supprimé de l'index.
    updated, deleted = search_index.sync_index(convs[:3])
    assert deleted == 1
    assert search_index.check_status().doc_count == 3


def test_search_dispatch(sample_corpus):
    convs, _b, _m = sample_corpus
    search_index.rebuild_index(convs)
    assert search_index.search("pomme", mode="substring") == {"c1"}
    assert search_index.search("regularite", mode="words") == {"c3"}
    assert search_index.search(r"Get-\w+", mode="regex") == {"c2"}


def test_drop_index(sample_corpus):
    convs, _b, _m = sample_corpus
    search_index.rebuild_index(convs)
    assert search_index.get_index_path().is_file()
    search_index.drop_index()
    assert not search_index.get_index_path().is_file()
    # check_status ne doit pas planter sur un index absent.
    st = search_index.check_status()
    assert st.ok is False
