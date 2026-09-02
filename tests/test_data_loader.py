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


def test_build_project_map_returns_valid_structure():
    """Vérifie que build_project_map retourne bien des dictionnaires et listes valides."""
    proj_map, all_sorted = build_project_map()
    assert isinstance(proj_map, dict)
    assert isinstance(all_sorted, list)
    for p_name, c_list in proj_map.items():
        assert isinstance(p_name, str)
        assert isinstance(c_list, list)
