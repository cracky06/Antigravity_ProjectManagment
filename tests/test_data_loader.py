"""test_data_loader.py — Tests unitaires pour data_loader.py."""

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import pytest

from data_loader import (
    _decode_varint,
    _encode_proto_field,
    _parse_proto_fields,
    _clean_path_string,
    _update_ide_sqlite_db_workspace,
    _resolve_target_project_id_and_uris,
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


# ---------------------------------------------------------------------------
# Synchronisation conversation_summaries.db et IDE DB (move_conversation)
# ---------------------------------------------------------------------------
def test_move_conversation_updates_sqlite_summaries_db(tmp_path, monkeypatch):
    """Vérifie la mise à jour de conversation_summaries.db lors du déplacement."""
    import sqlite3
    from data_loader import move_conversation, _parse_proto_fields

    parent = tmp_path / ".gemini"
    ag = parent / "antigravity"
    ag.mkdir(parents=True)
    (tmp_path / "DEV").mkdir(parents=True)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: ag)
    monkeypatch.setattr("data_loader.get_projects_root", lambda: tmp_path / "DEV")

    cid = "11111111-2222-3333-4444-555555555555"
    db_path = ag / "conversation_summaries.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE conversation_summaries ("
        "conversation_id TEXT PRIMARY KEY, title TEXT, project_id TEXT, "
        "workspace_uris TEXT, raw_summary BLOB)"
    )
    conn.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?)",
        (cid, "Old Title", "old-project-uuid", '["file:///d:/DEV/OldProject"]', None),
    )
    conn.commit()
    conn.close()

    ok, _ = move_conversation(cid, "NewProjectTarget")
    assert ok is True

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT project_id, workspace_uris, raw_summary, title FROM conversation_summaries WHERE conversation_id = ?",
        (cid,),
    ).fetchone()
    conn.close()

    assert row is not None
    new_pid, new_uris, new_raw, saved_title = row
    assert new_pid != "old-project-uuid"
    assert "NewProjectTarget" in new_uris
    assert saved_title == "Old Title"
    # Vérifie que raw_summary contient le nouveau project_id et l'URI
    assert new_raw is not None
    sub = _parse_proto_fields(new_raw)
    assert 4 in sub
    assert sub[4][0][1].decode("utf-8") == new_pid


def test_move_conversation_updates_ide_trajectory_and_proto_field4(summaries_tree, tmp_path, monkeypatch):
    """Vérifie la mise à jour de trajectory_metadata_blob et du champ 4 protobuf."""
    import sqlite3
    from data_loader import move_conversation, _parse_proto_fields, _encode_proto_field

    cid = "aaaaaaaa-1111-2222-3333-444444444444"
    ag, pb = summaries_tree([(cid, "file:///d:/DEV/InitialProject")])
    (ag / "brain" / cid).mkdir(parents=True)

    # Créer une base conversations/<cid>.db au format IDE
    ide_conv_db = ag / "conversations" / f"{cid}.db"
    conn = sqlite3.connect(ide_conv_db)
    conn.execute("CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB)")
    # data contient sub1.field1 = workspace uri
    sub1 = _encode_proto_field(1, 2, b"file:///d:/DEV/InitialProject")
    data_blob = _encode_proto_field(1, 2, sub1)
    conn.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (data_blob,))
    conn.commit()
    conn.close()

    ok, _ = move_conversation(cid, "TargetAlpha")
    assert ok is True

    # 1. Vérifier champ 4 dans agyhub_summaries_proto.pb
    top = _parse_proto_fields(pb.read_bytes())
    f = _parse_proto_fields(top[1][0][1])
    sub2 = _parse_proto_fields(f[2][0][1])
    assert 4 in sub2
    assigned_pid = sub2[4][0][1].decode("utf-8")
    assert len(assigned_pid) == 36

    # 2. Vérifier trajectory_metadata_blob dans conversations/<cid>.db
    conn = sqlite3.connect(ide_conv_db)
    row = conn.execute("SELECT data FROM trajectory_metadata_blob WHERE id='main'").fetchone()
    conn.close()
    assert row is not None
    top_ide = _parse_proto_fields(row[0])
    sub_ide = _parse_proto_fields(top_ide[1][0][1])
    assert b"TargetAlpha" in sub_ide[1][0][1]
    assert 18 in top_ide
    assert top_ide[18][0][1].decode("utf-8") == assigned_pid


def test_move_conversation_reuses_existing_project_id(tmp_path, monkeypatch):
    """Si d'autres conversations existent sur le projet cible, le même project_id est réutilisé."""
    import sqlite3
    from data_loader import move_conversation

    parent = tmp_path / ".gemini"
    ag = parent / "antigravity"
    ag.mkdir(parents=True)
    (tmp_path / "DEV").mkdir(parents=True)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: ag)
    monkeypatch.setattr("data_loader.get_projects_root", lambda: tmp_path / "DEV")

    known_pid = "99998888-7777-6666-5555-444433332222"
    db_path = ag / "conversation_summaries.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE conversation_summaries ("
        "conversation_id TEXT PRIMARY KEY, title TEXT, project_id TEXT, "
        "workspace_uris TEXT, raw_summary BLOB)"
    )
    # Conversation existante déjà sur SharedProject
    conn.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?)",
        ("conv-existing-1", "Existing", known_pid, '["file:///d:/DEV/SharedProject"]', None),
    )
    # Conversation à déplacer
    cid_to_move = "conv-to-move-2"
    conn.execute(
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?)",
        (cid_to_move, "To Move", "other-pid", '["file:///d:/DEV/OtherProject"]', None),
    )
    conn.commit()
    conn.close()

    ok, _ = move_conversation(cid_to_move, "SharedProject")
    assert ok is True

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT project_id FROM conversation_summaries WHERE conversation_id = ?",
        (cid_to_move,),
    ).fetchone()
    conn.close()

    assert row[0] == known_pid


def test_move_conversation_inserts_missing_summary_and_syncs_desktop(tmp_path, monkeypatch):
    """Vérifie que move_conversation insère les conversations absentes dans conversation_summaries.db
    et que f17[18] (project_id reconnu par Antigravity Desktop) et f17[7] (URI) sont bien définis."""
    import sqlite3
    from data_loader import move_conversation, _parse_proto_fields

    parent = tmp_path / ".gemini"
    ag = parent / "antigravity"
    ag.mkdir(parents=True)
    (tmp_path / "DEV").mkdir(parents=True)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: ag)
    monkeypatch.setattr("data_loader.get_projects_root", lambda: tmp_path / "DEV")

    # Base summaries initialement vide pour ce cid
    db_path = ag / "conversation_summaries.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE conversation_summaries ("
        "conversation_id TEXT PRIMARY KEY, title TEXT, preview TEXT, step_count INTEGER, "
        "last_modified_time DATETIME, workspace_uris TEXT, status TEXT, source TEXT, "
        "project_id TEXT, agent_name TEXT, parent_conversation_id TEXT, nesting_depth INTEGER, "
        "battle_id TEXT, winning_conversation_id TEXT, not_fully_idle NUMERIC, killed NUMERIC, "
        "last_user_input_time DATETIME, last_user_input_step_index INTEGER, app_data_dir TEXT, "
        "raw_summary BLOB, group_id TEXT)"
    )
    conn.commit()
    conn.close()

    cid = "conv-new-ide-origin-1234"
    ok, _ = move_conversation(cid, "DesktopTargetProject")
    assert ok is True

    # Vérifie que la ligne a été insérée
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT title, project_id, workspace_uris, raw_summary FROM conversation_summaries WHERE conversation_id = ?",
        (cid,),
    ).fetchone()
    conn.close()

    assert row is not None
    title, pid, uris, raw_summary = row
    assert "DesktopTargetProject" in uris
    assert pid and len(pid) > 10
    assert raw_summary is not None

    top = _parse_proto_fields(raw_summary)
    assert 17 in top
    sub17 = _parse_proto_fields(top[17][0][1])
    assert 18 in sub17
    # Le champ 18 dans submessage 17 doit correspondre exactement au project_id de la table !
    assert sub17[18][0][1].decode("utf-8") == pid
    assert 7 in sub17
    assert "DesktopTargetProject" in sub17[7][0][1].decode("utf-8")


def test_update_ide_sqlite_db_workspace_injects_field_1_when_missing(tmp_path, monkeypatch):
    """Vérifie que _update_ide_sqlite_db_workspace injecte le champ 1 (workspace)
    même si la conversation a été créée hors projet et n'avait aucun champ 1."""
    antigravity_dir = tmp_path / "antigravity"
    convs_dir = antigravity_dir / "conversations"
    convs_dir.mkdir(parents=True)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: antigravity_dir)

    cid = "test-conv-no-field-1-uuid"
    db_path = convs_dir / f"{cid}.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE trajectory_metadata_blob (id TEXT PRIMARY KEY, data BLOB)")

    # Créer un blob sans champ 1 (comme les conversations créées hors projet)
    top_initial = {
        6: [(2, cid.encode("utf-8"))],
        18: [(2, b"outside-of-project")],
    }
    rb = bytearray()
    for f, items in top_initial.items():
        for w, v in items:
            rb.extend(_encode_proto_field(f, w, v))
    conn.execute("INSERT INTO trajectory_metadata_blob VALUES ('main', ?)", (bytes(rb),))
    conn.commit()
    conn.close()

    uri_std = b"file:///e:/Dev/TargetProj"
    uri_enc = b"file:///e%3A/Dev/TargetProj"
    pid = "target-proj-uuid-1234"

    ok = _update_ide_sqlite_db_workspace(cid, uri_std, uri_enc, pid)
    assert ok is True

    # Vérifier que le champ 1 a été correctement créé et injecté
    conn = sqlite3.connect(db_path)
    r = conn.execute("SELECT data FROM trajectory_metadata_blob WHERE id='main'").fetchone()
    conn.close()
    assert r and r[0]

    top_after = _parse_proto_fields(r[0])
    assert 1 in top_after, "Le champ 1 (workspace) doit être injecté"
    sub1 = _parse_proto_fields(top_after[1][0][1])
    assert sub1[1][0][1] == uri_std
    assert sub1[2][0][1] == uri_std
    assert top_after[18][0][1] == pid.encode("utf-8")
    assert top_after[7][0][1] == uri_enc


def test_resolve_target_project_id_reads_config_projects(tmp_path, monkeypatch):
    """Vérifie que _resolve_target_project_id_and_uris lit prioritairement
    les fichiers officiels .gemini/config/projects/*.json."""
    antigravity_dir = tmp_path / "antigravity"
    antigravity_dir.mkdir(parents=True)
    config_proj_dir = tmp_path / "config" / "projects"
    config_proj_dir.mkdir(parents=True)
    monkeypatch.setattr("data_loader.get_antigravity_root", lambda: antigravity_dir)

    # Créer un faux projet dans config/projects
    p_uuid = "proj-uuid-official-9999"
    p_json = {
        "id": p_uuid,
        "name": "MyOfficialProject",
        "projectResources": {
            "resources": [
                {
                    "gitFolder": {
                        "folderUri": "file:///c%3A/Custom/Path/To/MyOfficialProject"
                    }
                }
            ]
        }
    }
    (config_proj_dir / f"{p_uuid}.json").write_text(json.dumps(p_json), encoding="utf-8")

    dummy_target_dir = Path("E:/Dev/MyOfficialProject")
    pid, can_uri, uri_std_b, uri_enc_b, uris_json = _resolve_target_project_id_and_uris(
        "MyOfficialProject", dummy_target_dir
    )

    assert pid == p_uuid
    assert can_uri == "file:///c%3A/Custom/Path/To/MyOfficialProject"
    assert uri_enc_b == b"file:///c%3A/Custom/Path/To/MyOfficialProject"
    assert uri_std_b == b"file:///c:/Custom/Path/To/MyOfficialProject"
    assert "file:///c%3A/Custom/Path/To/MyOfficialProject" in uris_json


def test_is_antigravity_desktop_running(monkeypatch):
    """Vérifie la détection du processus Antigravity Desktop."""
    import subprocess
    from data_loader import is_antigravity_desktop_running

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout='"Antigravity.exe","1234","Console","1","50000 K"\n'
        ),
    )
    assert is_antigravity_desktop_running() is True

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout='INFO: No tasks running\n'
        ),
    )
    assert is_antigravity_desktop_running() is False


def test_restart_antigravity_desktop_if_running(monkeypatch, tmp_path):
    """Vérifie la séquence de fermeture et réouverture de Desktop."""
    import os
    import subprocess
    from data_loader import restart_antigravity_desktop_if_running

    # Simuler Desktop non actif
    monkeypatch.setattr("data_loader.is_antigravity_desktop_running", lambda: False)
    assert restart_antigravity_desktop_if_running() is False

    # Simuler Desktop actif avec faux exe
    monkeypatch.setattr("data_loader.is_antigravity_desktop_running", lambda: True)
    fake_exe = tmp_path / "Programs" / "Antigravity" / "Antigravity.exe"
    fake_exe.parent.mkdir(parents=True, exist_ok=True)
    fake_exe.write_text("dummy", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    killed = []
    started = []

    def mock_run(args, **kwargs):
        killed.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(os, "startfile", lambda p: started.append(p))
    monkeypatch.setattr("time.sleep", lambda s: None)

    ok = restart_antigravity_desktop_if_running()
    assert ok is True
    assert len(killed) == 2  # Antigravity.exe et language_server.exe
    assert len(started) == 1
    assert started[0] == str(fake_exe)


def test_build_project_map_filters_unrelated_directories(tmp_path, monkeypatch):
    """Vérifie que les répertoires sans marqueurs ni convs sont exclus du panneau Antigravity."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "RandomDevFolder").mkdir()
    (projects_dir / "ValidAntigravityProject" / ".agent").mkdir(parents=True)

    gemini_dir = tmp_path / ".gemini"
    antigravity_dir = gemini_dir / "antigravity"
    antigravity_dir.mkdir(parents=True)
    cfg_proj_dir = gemini_dir / "config" / "projects"
    cfg_proj_dir.mkdir(parents=True)
    (cfg_proj_dir / "proj1.json").write_text(json.dumps({"name": "OfficialProject"}), encoding="utf-8")

    monkeypatch.setattr("data_loader.get_paths", lambda: (projects_dir, antigravity_dir, antigravity_dir / "brain", antigravity_dir / "conversations", antigravity_dir / "agyhub_summaries_proto.pb"))
    monkeypatch.setattr("data_loader._extract_proto_metadata", lambda: {})

    from data_loader import build_project_map
    project_convs, all_convs = build_project_map()

    assert "ValidAntigravityProject" in project_convs
    assert "OfficialProject" in project_convs
    assert "RandomDevFolder" not in project_convs


def test_delete_conversation_cleans_summaries_db(tmp_path, monkeypatch):
    """Vérifie que delete_conversation purge aussi l'enregistrement dans conversation_summaries.db."""
    gemini_dir = tmp_path / ".gemini"
    ag_dir = gemini_dir / "antigravity"
    ag_dir.mkdir(parents=True)
    db_path = ag_dir / "conversation_summaries.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE conversation_summaries (conversation_id TEXT PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO conversation_summaries VALUES ('c1', 'Titre 1')")
    conn.execute("INSERT INTO conversation_summaries VALUES ('c2', 'Titre 2')")
    conn.commit()
    conn.close()

    monkeypatch.setattr("data_loader.get_paths", lambda: (tmp_path, ag_dir, ag_dir / "brain", ag_dir / "conversations", ag_dir / "proto.pb"))
    monkeypatch.setattr("data_loader._find_all_summaries_db", lambda: [db_path])

    from data_loader import delete_conversation
    ok, _ = delete_conversation("c1")
    assert ok is True

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT conversation_id FROM conversation_summaries").fetchall()
    conn.close()
    assert rows == [("c2",)]


