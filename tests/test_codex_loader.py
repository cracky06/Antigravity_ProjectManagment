import json
import sqlite3
from pathlib import Path

from codex_loader import CodexConv, build_codex_project_map, load_codex_messages

ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def rollout(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def event(kind, **payload):
    return {"type": "event_msg", "timestamp": "2026-09-19T10:00:00Z", "payload": {"type": kind, **payload}}


def item(kind, text, ident="message"):
    value = {"type": kind, "id": ident}
    if kind == "UserMessage":
        value["content"] = [{"type": "text", "text": text}]
    else:
        value["text"] = text
    return event("item_completed", item=value)


def response(role, text, **extra):
    return {"type": "response_item", "timestamp": "2026-09-19T10:00:00Z",
            "payload": {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}], **extra}}


def state_db(root, rows):
    conn = sqlite3.connect(root / "state_5.sqlite")
    conn.executescript("""CREATE TABLE threads (id TEXT,rollout_path TEXT,cwd TEXT,title TEXT,name TEXT,project_id TEXT,archived INTEGER,source TEXT,updated_at INTEGER);
        CREATE TABLE projects (id TEXT,name TEXT);
        CREATE TABLE project_roots (project_id TEXT,position INTEGER,path TEXT);""")
    conn.executemany("INSERT INTO threads VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def test_visible_items_win_without_duplicate_or_internal_text(tmp_path):
    p = rollout(tmp_path / "session.jsonl", [event("task_started"),
        response("developer", "secret rules"), response("user", "question"),
        item("UserMessage", "question", "u"), response("assistant", "answer"),
        item("AgentMessage", "answer", "a"), response("assistant", "private", channel="analysis"),
        event("item_completed", item={"type": "Reasoning", "text": "private"})])
    messages = load_codex_messages(CodexConv(ID, "p", p))
    assert [(m["role"], m["text"]) for m in messages] == [("user", "question"), ("assistant", "answer")]


def test_old_new_turns_and_repeated_real_messages_preserved(tmp_path):
    p = rollout(tmp_path / "session.jsonl", [event("task_started"), response("user", "OK"), response("assistant", "A"),
        event("task_started"), item("UserMessage", "OK", "u2"), item("AgentMessage", "B", "a2")])
    with p.open("a", encoding="utf8") as f: f.write('{"unfinished":')
    assert [m["text"] for m in load_codex_messages(CodexConv(ID, "p", p))] == ["OK", "A", "OK", "B"]


def test_legacy_agent_event_does_not_hide_response_user(tmp_path):
    p = rollout(tmp_path / "s.jsonl", [response("user", "bonjour"), event("agent_message", message="salut"), response("assistant", "salut")])
    assert [m["text"] for m in load_codex_messages(CodexConv(ID, "", p))] == ["bonjour", "salut"]


def test_project_assignment_overrides_original_cwd(tmp_path):
    p = rollout(tmp_path / "sessions" / f"rollout-{ID}.jsonl", [item("UserMessage", "hi")])
    conn = state_db(tmp_path, [(ID, str(p), str(tmp_path / 'old'), 'first prompt', 'Renamed', None, 0, 'vscode', 1789770000)])
    conn.close()
    (tmp_path / '.codex-global-state.json').write_text(json.dumps({
        'local-projects': {'new': {'name': 'Real project', 'rootPaths': [str(tmp_path / 'new')]}},
        'thread-project-assignments': {ID: {'projectKind': 'local', 'projectId': 'new'}}}), encoding='utf8')
    result = build_codex_project_map(tmp_path)
    conv = result['Real project'][0]
    assert conv.title == 'Renamed'
    assert conv.project_root == tmp_path / 'new'
    assert conv.cwd == str(tmp_path / 'old')


def test_sqlite_project_archived_and_explicit_projectless(tmp_path):
    conn = state_db(tmp_path, [(ID, '', '/old', 'archived', '', 'p', 1, 'cli', 1789770000),
        ('other', '', '/scratch', 'orphan', '', None, 0, 'cli', 1789770000)])
    conn.execute('INSERT INTO projects VALUES (?,?)', ('p', 'Project'))
    conn.execute('INSERT INTO project_roots VALUES (?,?,?)', ('p', 0, str(tmp_path / 'project')))
    conn.commit(); conn.close()
    (tmp_path / '.codex-global-state.json').write_text(json.dumps({'projectless-thread-ids': ['other']}))
    result = build_codex_project_map(tmp_path)
    assert result['Project'][0].archived
    assert result[''][0].project_root is None


def test_rollout_only_and_corrupt_state_fallback(tmp_path):
    p = tmp_path / 'archived_sessions' / f'rollout-{ID}.jsonl'
    rollout(p, [{'type': 'session_meta', 'payload': {'id': ID, 'cwd': str(tmp_path / 'proj'), 'source': 'cli'}}, item('UserMessage', 'Title')])
    (tmp_path / 'state_99.sqlite').write_bytes(b'not sqlite')
    result = build_codex_project_map(tmp_path)
    assert result['proj'][0].title == 'Title'
    assert result['proj'][0].archived


def test_sqlite_history_without_rollout(tmp_path):
    db = tmp_path / 'thread_history_1.sqlite'
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE thread_items(thread_id TEXT,rollout_ordinal INTEGER,created_at_ms INTEGER,item_json TEXT)')
    for i, msg in enumerate([{'type': 'userMessage', 'id': 'u', 'content': [{'type': 'text', 'text': 'Hello'}]},
                             {'type': 'agentMessage', 'id': 'a', 'text': 'World'},
                             {'type': 'reasoning', 'text': 'hidden'}]):
        conn.execute('INSERT INTO thread_items VALUES (?,?,?,?)', (ID, i, 1789770000000, json.dumps(msg)))
    conn.commit(); conn.close()
    before = db.read_bytes()
    messages = load_codex_messages(CodexConv(ID, '', None, history_path=db))
    assert [m['text'] for m in messages] == ['Hello', 'World']
    assert db.read_bytes() == before


def test_image_only_message_is_not_lost_or_base64_indexed(tmp_path):
    entry = event('item_completed', item={'type': 'UserMessage', 'content': [{'type': 'image', 'url': 'data:image/png;base64,SECRET'}]})
    p = rollout(tmp_path / 's.jsonl', [entry])
    assert load_codex_messages(CodexConv(ID, '', p))[0]['text'] == '[Image jointe]'


def test_same_project_names_remain_separate(tmp_path):
    rows = [(ID, '', str(tmp_path / 'a' / 'app'), 'one', '', None, 0, 'cli', 1789770000),
            ('other', '', str(tmp_path / 'b' / 'app'), 'two', '', None, 0, 'cli', 1789770000)]
    state_db(tmp_path, rows).close()
    result = build_codex_project_map(tmp_path)
    assert len(result) == 2
    assert all(len(v) == 1 for v in result.values())


def test_legacy_internal_context_filtered(tmp_path):
    p = rollout(tmp_path / 's.jsonl', [response('user', '<environment_context>private</environment_context>'),
        response('user', '# AGENTS.md instructions for project\nsecret'), response('user', 'real question'), response('assistant', 'answer')])
    assert [m['text'] for m in load_codex_messages(CodexConv(ID, '', p))] == ['real question', 'answer']
