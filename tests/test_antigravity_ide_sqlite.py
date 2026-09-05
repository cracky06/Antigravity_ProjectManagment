"""test_antigravity_ide_sqlite.py — Lecteur SQLite des conversations Antigravity IDE.

Les bases réelles de la machine ne sont pas disponibles en CI : on fabrique
ici des `.db` synthétiques avec des `step_payload` protobuf encodés à la main,
selon le format documenté (f1=step_type, f5.f1.f1=epoch, f19.f2=texte user,
f20.f1=texte model).
"""

import sqlite3
from datetime import timezone
from pathlib import Path

from antigravity_ide_sqlite import (
    _decode_proto_fields,
    ide_sqlite_has_dialogue,
    load_ide_sqlite_conversation,
    extract_workspace,
    find_ide_db,
)


# --- helpers d'encodage protobuf (wire format) ---------------------------------
def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return _varint((field << 3) | wire)


def _fld_varint(field: int, value: int) -> bytes:
    return _tag(field, 0) + _varint(value)


def _fld_bytes(field: int, value: bytes) -> bytes:
    return _tag(field, 2) + _varint(len(value)) + value


def _fld_str(field: int, value: str) -> bytes:
    return _fld_bytes(field, value.encode("utf-8"))


def _timestamp_submsg(epoch: int) -> bytes:
    # f5 -> { f1 -> { f1 = epoch(varint) } }
    inner = _fld_varint(1, epoch)
    f1 = _fld_bytes(1, inner)
    return _fld_bytes(5, f1)


def _user_payload(text: str, epoch: int) -> bytes:
    # f1 step_type, f5 timestamp, f19 { f2 = text }
    body = _fld_varint(1, 14)
    body += _timestamp_submsg(epoch)
    body += _fld_bytes(19, _fld_str(2, text))
    return body


def _model_payload(text: str, epoch: int) -> bytes:
    body = _fld_varint(1, 15)
    body += _timestamp_submsg(epoch)
    body += _fld_bytes(20, _fld_str(1, text))
    return body


def _model_toolonly_payload(epoch: int) -> bytes:
    # step_type 15 mais aucun f20.f1 (le modèle n'a produit aucun texte visible)
    body = _fld_varint(1, 15)
    body += _timestamp_submsg(epoch)
    body += _fld_bytes(20, _fld_str(7, "list_dir"))  # f20.f7 = tool call
    return body


def _noise_payload(step_type: int, epoch: int) -> bytes:
    body = _fld_varint(1, step_type)
    body += _timestamp_submsg(epoch)
    return body


def _metadata_blob(workspace_uri: str) -> bytes:
    # trajectory_metadata_blob.data : f1 -> { f1 = workspace_uri }
    return _fld_bytes(1, _fld_str(1, workspace_uri))


def _make_db(path: Path, steps: list[tuple[int, bytes]], workspace_uri: str | None = None):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE steps (idx integer, step_type integer, status integer, "
        "step_payload blob, PRIMARY KEY (idx))"
    )
    conn.execute(
        "CREATE TABLE trajectory_metadata_blob (id text DEFAULT 'main', data blob, "
        "PRIMARY KEY (id))"
    )
    for i, (stype, payload) in enumerate(steps):
        conn.execute(
            "INSERT INTO steps (idx, step_type, status, step_payload) VALUES (?,?,?,?)",
            (i, stype, 3, payload),
        )
    if workspace_uri is not None:
        conn.execute(
            "INSERT INTO trajectory_metadata_blob (id, data) VALUES ('main', ?)",
            (_metadata_blob(workspace_uri),),
        )
    conn.commit()
    conn.close()


# --- tests --------------------------------------------------------------------
def test_decode_proto_fields_basic():
    data = _fld_varint(1, 14) + _fld_str(2, "hello")
    fields = _decode_proto_fields(data)
    assert fields[1][0] == ("varint", 14)
    assert fields[2][0][0] == "bytes"
    assert fields[2][0][1] == b"hello"


def test_load_conversation_user_and_model(tmp_path):
    db = tmp_path / "11111111-1111-1111-1111-111111111111.db"
    _make_db(
        db,
        [
            (14, _user_payload("Première question de l'utilisateur", 1_750_000_000)),
            (15, _model_payload("Réponse **Markdown** du modèle", 1_750_000_060)),
            (9, _noise_payload(9, 1_750_000_070)),  # tool_result : ignoré
            (14, _user_payload("Deuxième question", 1_750_000_120)),
            (15, _model_toolonly_payload(1_750_000_130)),  # pas de texte : ignoré
            (15, _model_payload("Réponse finale", 1_750_000_200)),
        ],
        workspace_uri="file:///e:/Dev/MonProjet",
    )
    data = load_ide_sqlite_conversation(db)

    roles = [(m["role"], m["text"]) for m in data["messages"]]
    assert roles == [
        ("user", "Première question de l'utilisateur"),
        ("model", "Réponse **Markdown** du modèle"),
        ("user", "Deuxième question"),
        ("model", "Réponse finale"),
    ]
    assert data["title"] == "Première question de l'utilisateur"
    assert data["workspace"] == "e:/Dev/MonProjet"
    assert data["last_dt"] is not None
    assert data["last_dt"].tzinfo is timezone.utc
    # dernière activité = epoch du dernier step lu
    assert int(data["last_dt"].timestamp()) == 1_750_000_200


def test_sanitize_user_request_wrapper(tmp_path):
    db = tmp_path / "22222222-2222-2222-2222-222222222222.db"
    raw = "<USER_REQUEST>\nVrai contenu\n</USER_REQUEST><ADDITIONAL_METADATA>bruit</ADDITIONAL_METADATA>"
    _make_db(db, [(14, _user_payload(raw, 1_750_000_000))])
    data = load_ide_sqlite_conversation(db)
    assert data["messages"][0]["text"] == "Vrai contenu"


def test_context_dump_is_skipped(tmp_path):
    db = tmp_path / "33333333-3333-3333-3333-333333333333.db"
    _make_db(
        db,
        [
            (14, _user_payload("The following is a summary of the conversation so far…", 1)),
            (14, _user_payload("Vraie question", 2)),
        ],
    )
    data = load_ide_sqlite_conversation(db)
    assert [m["text"] for m in data["messages"]] == ["Vraie question"]


def test_has_dialogue_true_false(tmp_path):
    live = tmp_path / "44444444-4444-4444-4444-444444444444.db"
    _make_db(live, [(14, _user_payload("q", 1)), (15, _model_payload("a", 2))])
    assert ide_sqlite_has_dialogue(live) is True

    empty = tmp_path / "55555555-5555-5555-5555-555555555555.db"
    _make_db(empty, [(9, _noise_payload(9, 1)), (90, _noise_payload(90, 2))])
    assert ide_sqlite_has_dialogue(empty) is False


def test_extract_workspace_strips_file_scheme(tmp_path):
    db = tmp_path / "66666666-6666-6666-6666-666666666666.db"
    _make_db(db, [(14, _user_payload("q", 1))], workspace_uri="file:///d:/DEV/Autre")
    assert extract_workspace(db) == "d:/DEV/Autre"


def test_missing_metadata_blob_gives_empty_workspace(tmp_path):
    db = tmp_path / "77777777-7777-7777-7777-777777777777.db"
    _make_db(db, [(14, _user_payload("q", 1))])
    assert extract_workspace(db) == ""
    assert load_ide_sqlite_conversation(db)["workspace"] == ""


def test_corrupt_db_returns_empty(tmp_path):
    bad = tmp_path / "88888888-8888-8888-8888-888888888888.db"
    bad.write_bytes(b"not a sqlite file at all")
    data = load_ide_sqlite_conversation(bad)
    assert data["messages"] == []
    assert ide_sqlite_has_dialogue(bad) is False


def test_last_dt_falls_back_to_mtime_when_no_timestamps(tmp_path):
    db = tmp_path / "99999999-9999-9999-9999-999999999999.db"
    # user step valide mais SANS sous-message f5 : aucun epoch lisible dans les steps
    payload = _fld_varint(1, 14) + _fld_bytes(19, _fld_str(2, "question sans horodatage"))
    _make_db(db, [(14, payload)])
    data = load_ide_sqlite_conversation(db)
    assert [m["text"] for m in data["messages"]] == ["question sans horodatage"]
    assert data["messages"][0]["timestamp"] == ""  # pas d'epoch => pas d'affichage
    assert data["last_dt"] is not None  # repli sur le mtime du fichier


def test_find_ide_db(tmp_path, monkeypatch):
    parent = tmp_path / ".gemini"
    convs = parent / "antigravity-ide" / "conversations"
    convs.mkdir(parents=True)
    cid = "abababab-abab-abab-abab-abababababab"
    (convs / f"{cid}.db").write_bytes(b"x")
    monkeypatch.setattr("antigravity_ide_sqlite._gemini_parent", lambda: parent)
    found = find_ide_db(cid)
    assert found is not None and found.name == f"{cid}.db"
    assert find_ide_db("00000000-0000-0000-0000-000000000000") is None
