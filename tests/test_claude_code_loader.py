"""test_claude_code_loader.py — Source de données Claude Code / Desktop (v2.5).

Fabrique des .jsonl factices sous un `tmp_path` (jamais les vraies données de
`~/.claude/projects/`) pour tester le scan de projets/sessions et l'extraction
du dialogue, en isolation complète.
"""

import json

import pytest

import claude_code_loader as ccl


def _write_jsonl(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def _user_msg(text, ts, cwd, entrypoint="claude-vscode", is_sidechain=False):
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
        "timestamp": ts,
        "cwd": cwd,
        "entrypoint": entrypoint,
        "isSidechain": is_sidechain,
    }


def _assistant_msg(text, ts, cwd, entrypoint="claude-vscode", is_sidechain=False):
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
        "timestamp": ts,
        "cwd": cwd,
        "entrypoint": entrypoint,
        "isSidechain": is_sidechain,
    }


def _ai_title(title, ts=None):
    d = {"type": "ai-title", "aiTitle": title}
    if ts:
        d["timestamp"] = ts
    return d


# --- get_claude_projects_root -----------------------------------------------
def test_get_claude_projects_root_uses_userprofile(monkeypatch):
    monkeypatch.setenv("USERPROFILE", r"C:\Users\Test")
    root = ccl.get_claude_projects_root()
    assert str(root).replace("\\", "/").endswith("Users/Test/.claude/projects")


# --- build_claude_project_map -----------------------------------------------
def test_build_project_map_basic(tmp_path):
    cwd = str(tmp_path / "MonJeu")
    _write_jsonl(
        tmp_path / "e--Dev-MonJeu" / "s1.jsonl",
        [
            _user_msg("bonjour", "2026-01-15T10:00:00.000Z", cwd),
            _assistant_msg("salut", "2026-01-15T10:00:05.000Z", cwd),
            _ai_title("Discussion de test"),
        ],
    )
    pm = ccl.build_claude_project_map(tmp_path)
    assert "MonJeu" in pm
    assert len(pm["MonJeu"]) == 1
    conv = pm["MonJeu"][0]
    assert conv.title == "Discussion de test"
    assert conv.conv_id == "s1"
    assert "VS Code" in conv.origin_label


def test_build_project_map_empty_root(tmp_path):
    empty = tmp_path / "does_not_exist"
    pm = ccl.build_claude_project_map(empty)
    assert pm == {}


def test_build_project_map_ignores_empty_session(tmp_path):
    """Une session sans cwd exploitable (juste queue-operation/bridge-session)
    est ignorée, pas plantée."""
    _write_jsonl(
        tmp_path / "e--Dev-X" / "empty.jsonl",
        [
            {"type": "bridge-session", "sessionId": "empty"},
            {"type": "queue-operation", "operation": "enqueue"},
        ],
    )
    pm = ccl.build_claude_project_map(tmp_path)
    assert pm == {}


def test_build_project_map_skips_corrupted_lines(tmp_path):
    """Une ligne JSON corrompue ne doit pas faire planter le scan du reste."""
    path = tmp_path / "e--Dev-Y" / "s2.jsonl"
    path.parent.mkdir(parents=True)
    cwd = str(tmp_path / "Y")
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_user_msg("ok", "2026-01-15T10:00:00.000Z", cwd)) + "\n")
        fh.write("{ceci n'est pas du json valide\n")
        fh.write(json.dumps(_assistant_msg("bien reçu", "2026-01-15T10:00:05.000Z", cwd)) + "\n")
    pm = ccl.build_claude_project_map(tmp_path)
    assert "Y" in pm
    msgs = ccl.load_claude_messages(pm["Y"][0].path)
    assert len(msgs) == 2


def test_build_project_map_title_falls_back_to_first_user_message(tmp_path):
    """Sans ai-title, le titre replie sur le début du premier message user,
    en filtrant les blocs système type <ide_opened_file>."""
    cwd = str(tmp_path / "Z")
    _write_jsonl(
        tmp_path / "e--Dev-Z" / "s3.jsonl",
        [
            _user_msg("<ide_opened_file>bruit</ide_opened_file>", "2026-01-15T10:00:00.000Z", cwd),
            _user_msg("quelle est la question réelle ?", "2026-01-15T10:00:01.000Z", cwd),
        ],
    )
    pm = ccl.build_claude_project_map(tmp_path)
    assert pm["Z"][0].title == "quelle est la question réelle ?"


def test_build_project_map_sorted_by_recency(tmp_path):
    cwd = str(tmp_path / "W")
    _write_jsonl(
        tmp_path / "e--Dev-W" / "old.jsonl",
        [_user_msg("a", "2026-01-01T10:00:00.000Z", cwd)],
    )
    _write_jsonl(
        tmp_path / "e--Dev-W" / "new.jsonl",
        [_user_msg("b", "2026-06-01T10:00:00.000Z", cwd)],
    )
    convs = ccl.build_claude_project_map(tmp_path)["W"]
    assert [c.conv_id for c in convs] == ["new", "old"]


def test_build_project_map_multiple_entrypoints(tmp_path):
    cwd = str(tmp_path / "Multi")
    _write_jsonl(
        tmp_path / "e--Dev-Multi" / "s4.jsonl",
        [
            _user_msg("a", "2026-01-15T10:00:00.000Z", cwd, entrypoint="claude-vscode"),
            _assistant_msg("b", "2026-01-15T10:00:01.000Z", cwd, entrypoint="claude-desktop"),
        ],
    )
    conv = ccl.build_claude_project_map(tmp_path)["Multi"][0]
    assert "VS Code" in conv.origin_label
    assert "Desktop" in conv.origin_label


# --- load_claude_messages ---------------------------------------------------
def test_load_messages_filters_sidechain(tmp_path):
    cwd = str(tmp_path / "Side")
    path = tmp_path / "s5.jsonl"
    _write_jsonl(
        path,
        [
            _user_msg("principal", "2026-01-15T10:00:00.000Z", cwd),
            _assistant_msg("sous-tâche", "2026-01-15T10:00:01.000Z", cwd, is_sidechain=True),
            _assistant_msg("réponse principale", "2026-01-15T10:00:02.000Z", cwd),
        ],
    )
    msgs = ccl.load_claude_messages(path)
    assert len(msgs) == 2
    assert msgs[0]["text"] == "principal"
    assert msgs[1]["text"] == "réponse principale"


def test_load_messages_orders_by_timestamp(tmp_path):
    cwd = str(tmp_path / "Order")
    path = tmp_path / "s6.jsonl"
    _write_jsonl(
        path,
        [
            _assistant_msg("deuxième", "2026-01-15T10:05:00.000Z", cwd),
            _user_msg("premier", "2026-01-15T10:00:00.000Z", cwd),
        ],
    )
    msgs = ccl.load_claude_messages(path)
    assert [m["text"] for m in msgs] == ["premier", "deuxième"]


def test_load_messages_filters_ide_blocks(tmp_path):
    cwd = str(tmp_path / "Ide")
    path = tmp_path / "s7.jsonl"
    _write_jsonl(
        path,
        [{
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<ide_opened_file>bruit</ide_opened_file>"},
                    {"type": "text", "text": "vraie question"},
                ],
            },
            "timestamp": "2026-01-15T10:00:00.000Z",
            "cwd": cwd,
        }],
    )
    msgs = ccl.load_claude_messages(path)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "vraie question"


def test_load_messages_ignores_tool_use_blocks(tmp_path):
    """Seuls les blocs `text` sont gardés — tool_use/tool_result/thinking sont
    du bruit pour la lecture (portée v1, cf. docstring du module)."""
    cwd = str(tmp_path / "Tool")
    path = tmp_path / "s8.jsonl"
    _write_jsonl(
        path,
        [{
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "je réfléchis"},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "x.py"}},
                    {"type": "text", "text": "voici le résultat"},
                ],
            },
            "timestamp": "2026-01-15T10:00:00.000Z",
            "cwd": cwd,
        }],
    )
    msgs = ccl.load_claude_messages(path)
    assert len(msgs) == 1
    assert msgs[0]["text"] == "voici le résultat"


def test_load_messages_empty_session_returns_empty_list(tmp_path):
    path = tmp_path / "s9.jsonl"
    _write_jsonl(path, [{"type": "bridge-session", "sessionId": "x"}])
    assert ccl.load_claude_messages(path) == []


def test_load_messages_missing_file_returns_empty_list(tmp_path):
    assert ccl.load_claude_messages(tmp_path / "does_not_exist.jsonl") == []


# --- Export Markdown (v2.5) --------------------------------------------------
from datetime import datetime


def test_default_claude_export_filename():
    conv = ccl.ClaudeConv(
        conv_id="12345678-abcd-ef00-1122-334455667788",
        project="TestProj",
        path=ccl.Path("dummy.jsonl"),
        title="bugs & features:",
        last_dt=datetime(2026, 3, 14, 15, 30),
    )
    fname = ccl.default_claude_export_filename(conv)
    # _slugify (data_loader) ne touche que la ponctuation -> " & " devient "-",
    # ":" est retiré, mais casse et accents sont conservés tels quels.
    assert fname == "20260314_bugs-features_12345678.md"
    assert fname.endswith(".md")

    # Sans date
    conv_nodate = ccl.ClaudeConv(
        conv_id="abcdef12-0000-0000-0000-000000000000",
        project="P",
        path=ccl.Path("dummy.jsonl"),
        title="Sans Date",
        last_dt=None,
    )
    assert ccl.default_claude_export_filename(conv_nodate).startswith("nodate_Sans-Date_")


def test_build_claude_conversation_markdown(tmp_path):
    cwd = str(tmp_path / "MonProjet")
    jsonl_path = tmp_path / "s10.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _user_msg("Bonjour, peux-tu m'aider ?", "2026-03-14T10:00:00.000Z", cwd),
            _assistant_msg("Bien sûr ! Que souhaites-tu faire ?", "2026-03-14T10:00:05.000Z", cwd),
        ],
    )
    conv = ccl.ClaudeConv(
        conv_id="sess-test-12345678",
        project="MonProjet",
        path=jsonl_path,
        title="Session d'aide",
        last_dt=datetime(2026, 3, 14, 10, 0, 5),
        entrypoints={"claude-vscode"},
        project_root=tmp_path / "MonProjet",
    )
    md = ccl.build_claude_conversation_markdown(conv)
    assert "# Session d'aide" in md
    assert "- **Projet :** MonProjet" in md
    assert "- **Origine :** VS Code" in md
    assert "- **ID de session :** `sess-test-12345678`" in md
    assert "### 👤 Utilisateur" in md
    assert "Bonjour, peux-tu m'aider ?" in md
    assert "### ✳️ Claude" in md
    assert "Bien sûr ! Que souhaites-tu faire ?" in md


def test_build_claude_conversation_markdown_empty_session(tmp_path):
    jsonl_path = tmp_path / "empty_sess.jsonl"
    _write_jsonl(jsonl_path, [{"type": "bridge-session", "sessionId": "x"}])
    conv = ccl.ClaudeConv(
        conv_id="empty-session-id",
        project="Vide",
        path=jsonl_path,
        title="Vide",
    )
    md = ccl.build_claude_conversation_markdown(conv)
    assert "*Aucun message textuel dans cette session.*" in md


def test_export_claude_conversation_to_project(tmp_path):
    proj_root = tmp_path / "ProjetReel"
    proj_root.mkdir()
    jsonl_path = tmp_path / "s11.jsonl"
    _write_jsonl(
        jsonl_path,
        [_user_msg("Hello", "2026-03-14T10:00:00.000Z", str(proj_root))],
    )
    conv = ccl.ClaudeConv(
        conv_id="export-test-1111",
        project="ProjetReel",
        path=jsonl_path,
        title="Test Export Projet",
        last_dt=datetime(2026, 3, 14, 10, 0),
        project_root=proj_root,
    )
    ok, result_path = ccl.export_claude_conversation_to_project(conv)
    assert ok is True
    out_file = ccl.Path(result_path)
    assert out_file.exists()
    assert out_file.parent == proj_root / "_conversations"
    assert "Test Export Projet" in out_file.read_text(encoding="utf-8")

    # Sans project_root
    conv_no_root = ccl.ClaudeConv(
        conv_id="export-no-root",
        project="SansRoot",
        path=jsonl_path,
        project_root=None,
    )
    ok_no, err = ccl.export_claude_conversation_to_project(conv_no_root)
    assert ok_no is False
    assert "Racine de projet inconnue" in err


def test_export_claude_conversation_to_path(tmp_path):
    jsonl_path = tmp_path / "s12.jsonl"
    _write_jsonl(
        jsonl_path,
        [_user_msg("Coucou", "2026-03-14T10:00:00.000Z", str(tmp_path))],
    )
    conv = ccl.ClaudeConv(
        conv_id="export-test-2222",
        project="TestPath",
        path=jsonl_path,
        title="Test Export Path",
    )
    custom_target = tmp_path / "exports" / "custom_name.md"
    ok, result = ccl.export_claude_conversation_to_path(conv, custom_target)
    assert ok is True
    assert custom_target.exists()
    assert "Test Export Path" in custom_target.read_text(encoding="utf-8")

