"""test_data_loader.py — Tests unitaires pour data_loader.py."""

from datetime import datetime, timezone
from pathlib import Path
import json
import pytest

from data_loader import (
    _decode_varint,
    _parse_proto_fields,
    _clean_path_string,
    workspace_to_project,
    relative_time,
    load_chat_messages,
    build_project_map,
    delete_conversation,
    ConversationInfo,
)


def test_clean_path_string():
    """Vérifie le nettoyage robuste des chaînes d'URLs et chemins Windows."""
    assert _clean_path_string("") == ""
    assert _clean_path_string("file:///e:/Dev/MonProjet") == "E:\\Dev\\MonProjet"
    assert _clean_path_string("file:///e:/Dev/MonProjet\x12\x1aother_data") == "E:\\Dev\\MonProjet"
    assert _clean_path_string("file:///e:/Dev/MonProjet\"branch_name") == "E:\\Dev\\MonProjet"
    assert _clean_path_string("file:///d:/DEV/SubFolder/App") == "D:\\DEV\\SubFolder\\App"


def test_workspace_to_project():
    """Vérifie l'extraction du nom de projet depuis divers formats de workspace."""
    assert workspace_to_project(r"E:\Dev\MonProjet") == "MonProjet"
    assert workspace_to_project(r"E:\Dev\MonProjet\SousDossier") == "MonProjet"
    assert workspace_to_project(r"D:\DEV\ProjetAlpha") == "ProjetAlpha"
    assert workspace_to_project(r"file:///E:/Dev/ProjetBeta") == "ProjetBeta"
    assert workspace_to_project(r"E:\Dev\Naturalchimie2\components\GameBoard.tsx`") == "Naturalchimie2"
    assert workspace_to_project(r"c:\Users\Manu\OneDrive\Private\scripts\Simpsons_Zombie_Apocalypse") == "Simpsons_Zombie_Apocalypse"
    assert workspace_to_project("n") == ""
    assert workspace_to_project("nLast") == ""
    assert workspace_to_project("") == ""


def test_relative_time():
    """Vérifie le formattage des durées relatives."""
    assert relative_time(None) == ""
    now = datetime.now(timezone.utc)
    assert relative_time(now) == "now"


def test_decode_varint():
    """Vérifie le décodage varint protobuf de base."""
    data = bytes([0x08])  # Varint 8
    val, pos = _decode_varint(data, 0)
    assert val == 8
    assert pos == 1


def test_parse_proto_fields():
    """Vérifie le parser protobuf wire-format."""
    # tag 0x08 = field 1, wire_type 0 (varint). Val = 42 (0x2a)
    data = bytes([0x08, 0x2A])
    fields = _parse_proto_fields(data)
    assert 1 in fields
    assert fields[1][0] == (0, 42)


def test_load_chat_messages_empty_or_nonexistent():
    """Vérifie qu'un conv_id inexistant retourne une liste vide sans planter."""
    msgs = load_chat_messages("00000000-0000-0000-0000-000000000000")
    assert isinstance(msgs, list)
    assert len(msgs) == 0


def test_encode_varint_and_proto_field():
    """Vérifie l'encodage de champs et varints protobuf."""
    from data_loader import _encode_varint, _encode_proto_field

    assert _encode_varint(42) == bytes([42])
    field_bytes = _encode_proto_field(1, 0, 42)
    assert field_bytes == bytes([0x08, 0x2A])


def test_move_conversation_nonexistent():
    """Vérifie que move_conversation s'exécute sans erreur même si l'ID n'existe pas."""
    from data_loader import move_conversation

    ok, msg = move_conversation("00000000-0000-0000-0000-000000000000", "TestProject")
    assert ok is True


# ---------------------------------------------------------------------------
# Robustesse de la réécriture de agyhub_summaries_proto.pb (move_conversation)
# Régression : un déplacement a déjà réinitialisé l'index de 14 -> 1 entrée.
# ---------------------------------------------------------------------------
def _build_summaries_pb(conv_specs):
    """Fabrique un agyhub_summaries_proto.pb minimal mais valide.

    conv_specs : liste de (conv_id, workspace_uri). Structure reproduite :
      field 1 (repeated) = entrée conversation
        entrée.field 1 = conv_id (string)
        entrée.field 2 = sous-message
          sub.field 1 = titre (string)
          sub.field 9 = sous-message { field 1 = workspace uri }
    """
    from data_loader import _encode_proto_field

    out = bytearray()
    for cid, ws in conv_specs:
        sub9 = _encode_proto_field(1, 2, ws.encode("utf-8"))
        sub = (
            _encode_proto_field(1, 2, f"Titre {cid[:4]}".encode("utf-8"))
            + _encode_proto_field(9, 2, sub9)
        )
        entry = _encode_proto_field(1, 2, cid.encode("utf-8")) + _encode_proto_field(2, 2, sub)
        out += _encode_proto_field(1, 2, bytes(entry))
    return bytes(out)


@pytest.fixture
def summaries_tree(tmp_path, monkeypatch):
    """.gemini/antigravity/ avec un agyhub_summaries_proto.pb à N conversations."""
    parent = tmp_path / ".gemini"
    ag = parent / "antigravity"
    (ag / "brain").mkdir(parents=True)
    (ag / "conversations").mkdir(parents=True)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: ag)
    monkeypatch.setattr("data_loader.get_projects_root", lambda: tmp_path / "DEV")
    (tmp_path / "DEV").mkdir()

    def setup(conv_specs):
        pb = ag / "agyhub_summaries_proto.pb"
        pb.write_bytes(_build_summaries_pb(conv_specs))
        return ag, pb

    return setup


def test_move_conversation_preserves_all_index_entries(summaries_tree):
    """Déplacer une conv ne doit JAMAIS réduire le nombre d'entrées de l'index."""
    from data_loader import move_conversation, _parse_proto_fields

    specs = [
        ("aaaaaaaa-0000-0000-0000-000000000001", "file:///d:/DEV/PlayVibe"),
        ("bbbbbbbb-0000-0000-0000-000000000002", "file:///d:/DEV/Comfyui"),
        ("cccccccc-0000-0000-0000-000000000003", "file:///d:/DEV/MAESTRO"),
    ]
    ag, pb = summaries_tree(specs)
    (ag / "brain" / specs[0][0]).mkdir()

    ok, _ = move_conversation(specs[0][0], "LocalIA-Extension")
    assert ok is True

    entries = _parse_proto_fields(pb.read_bytes()).get(1, [])
    assert len(entries) == 3, "aucune entrée ne doit disparaître lors d'un move"

    # La conv déplacée pointe désormais vers le nouveau projet.
    blob = pb.read_bytes()
    assert b"LocalIA-Extension" in blob
    # Les deux autres workspaces sont intacts.
    assert b"Comfyui" in blob and b"MAESTRO" in blob


def test_move_conversation_aborts_on_entry_loss(summaries_tree, monkeypatch):
    """Si la relecture du .pb reconstruit montre moins d'entrées, on n'écrit pas.

    Reproduit le mode de panne réel : `_parse_proto_fields` s'arrête sur un octet
    inattendu (wire-type 3/4, troncature) et ne « voit » plus qu'une fraction des
    entrées — l'index officiel ne doit pas être remplacé par cette version.
    """
    import data_loader
    from data_loader import move_conversation, _parse_proto_fields as real_parse

    specs = [
        ("aaaaaaaa-0000-0000-0000-000000000001", "file:///d:/DEV/PlayVibe"),
        ("bbbbbbbb-0000-0000-0000-000000000002", "file:///d:/DEV/Comfyui"),
        ("cccccccc-0000-0000-0000-000000000003", "file:///d:/DEV/MAESTRO"),
    ]
    ag, pb = summaries_tree(specs)
    (ag / "brain" / specs[0][0]).mkdir()
    original = pb.read_bytes()

    # La 1re passe (lecture de l'original) doit être fidèle ; seule la passe de
    # validation du buffer reconstruit renvoie un résultat tronqué.
    seen = {"n": 0}

    def flaky_parse(data):
        res = real_parse(data)
        seen["n"] += 1
        if seen["n"] >= 2 and 1 in res and len(res[1]) > 1:
            res[1] = res[1][:1]  # simule une troncature du décodage
        return res

    monkeypatch.setattr(data_loader, "_parse_proto_fields", flaky_parse)

    ok, _ = move_conversation(specs[0][0], "LocalIA-Extension")
    assert ok is True  # pas de crash
    assert pb.read_bytes() == original, "le .pb officiel doit rester intact en cas de perte d'entrées"
    assert not (ag / "agyhub_summaries_proto.pb.tmp").exists()


# ---------------------------------------------------------------------------
# Origine App vs IDE d'une conversation Antigravity
# ---------------------------------------------------------------------------
@pytest.fixture
def gemini_tree(tmp_path, monkeypatch):
    """Arborescence .gemini/ factice ; renvoie un helper pour peupler les sous-dossiers."""
    parent = tmp_path / ".gemini"
    (parent / "antigravity-ide").mkdir(parents=True)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: parent / "antigravity-ide")

    def place(sub: str, conv_id: str, *, brain: bool = False, db: bool = False, pb: bool = False):
        base = parent / sub
        if brain:
            (base / "brain" / conv_id).mkdir(parents=True, exist_ok=True)
        if db or pb:
            (base / "conversations").mkdir(parents=True, exist_ok=True)
        if db:
            (base / "conversations" / f"{conv_id}.db").write_bytes(b"x")
        if pb:
            (base / "conversations" / f"{conv_id}.pb").write_bytes(b"x")

    return place


def test_detect_origin_ide_only(gemini_tree):
    from data_loader import _detect_origin

    cid = "11111111-1111-1111-1111-111111111111"
    gemini_tree("antigravity-ide", cid, db=True)
    assert _detect_origin(cid) == "ide"


def test_detect_origin_app_only(gemini_tree):
    from data_loader import _detect_origin

    cid = "22222222-2222-2222-2222-222222222222"
    gemini_tree("antigravity", cid, brain=True)
    assert _detect_origin(cid) == "app"


def test_detect_origin_both_same_richness_is_ide_plus_app(gemini_tree):
    from data_loader import _detect_origin

    cid = "33333333-3333-3333-3333-333333333333"
    gemini_tree("antigravity-ide", cid, brain=True)
    gemini_tree("antigravity", cid, brain=True)
    assert _detect_origin(cid) == "ide+app"


def test_detect_origin_brain_wins_over_orphan_pb(gemini_tree):
    """Les 3 conversations historiques : brain/ côté app, simple .pb côté IDE."""
    from data_loader import _detect_origin

    cid = "44444444-4444-4444-4444-444444444444"
    gemini_tree("antigravity", cid, brain=True, pb=True)
    gemini_tree("antigravity-ide", cid, pb=True)
    assert _detect_origin(cid) == "app"


def test_detect_origin_backup_only_maps_to_app(gemini_tree):
    from data_loader import _detect_origin

    cid = "55555555-5555-5555-5555-555555555555"
    gemini_tree("antigravity-backup", cid, pb=True)
    assert _detect_origin(cid) == "app"


def test_detect_origin_absent_is_empty(gemini_tree):
    from data_loader import _detect_origin

    assert _detect_origin("99999999-9999-9999-9999-999999999999") == ""


def test_conversation_info_origin_label():
    base = dict(conv_id="c", title="t", project="p", workspace="w", last_activity=None)
    assert ConversationInfo(**base, origin="ide").origin_label == "IDE"
    assert ConversationInfo(**base, origin="app").origin_label == "App"
    assert ConversationInfo(**base, origin="ide+app").origin_label == "IDE+App"
    assert ConversationInfo(**base).origin_label == ""
    assert ConversationInfo(**base, origin="bogus").origin_label == ""

