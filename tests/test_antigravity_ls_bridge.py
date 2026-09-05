"""test_antigravity_ls_bridge.py — Passerelle language_server (conversations legacy).

Les appels réseau / PowerShell réels ne sont pas exerçables en CI : on teste
le parseur Markdown (pur) et la dégradation quand la découverte du serveur
échoue.
"""

import antigravity_ls_bridge as b


# --- parse_trajectory_markdown ----------------------------------------------
_SAMPLE = """# Chat Conversation

Note: _This is purely the output of the chat conversation and does not contain any raw data, codebase snippets, etc. used to generate the output._

### User Input

crée cette structure
### sous-titre dans le message
- a
- b

### Planner Response

Voici la structure demandée.

```python
print("ok")
```

### User Input

merci

### Planner Response

De rien.
"""


def test_parse_splits_on_role_headers_only():
    msgs = b.parse_trajectory_markdown(_SAMPLE)
    assert [m["role"] for m in msgs] == ["user", "model", "user", "model"]
    # un "###" à l'intérieur d'un message ne coupe pas le tour
    assert "sous-titre dans le message" in msgs[0]["text"]
    assert msgs[0]["text"].startswith("crée cette structure")
    assert "```python" in msgs[1]["text"]
    assert msgs[2]["text"] == "merci"
    assert msgs[3]["text"] == "De rien."
    # pas d'horodatage dans ce rendu
    assert all(m["timestamp"] == "" for m in msgs)


def test_parse_drops_intro_and_note():
    msgs = b.parse_trajectory_markdown(_SAMPLE)
    joined = "\n".join(m["text"] for m in msgs)
    assert "Chat Conversation" not in joined
    assert "purely the output" not in joined


def test_parse_empty_or_no_headers():
    assert b.parse_trajectory_markdown("") == []
    assert b.parse_trajectory_markdown("just some text, no headers") == []


def test_parse_skips_empty_turns():
    md = "### User Input\n\n\n### Planner Response\n\nune réponse\n"
    msgs = b.parse_trajectory_markdown(md)
    assert msgs == [{"role": "model", "text": "une réponse", "timestamp": ""}]


# --- dégradation quand le serveur est absent -------------------------------
def test_bridge_returns_none_when_discovery_fails(monkeypatch):
    monkeypatch.setattr(b, "_discovery_cache", {})
    monkeypatch.setattr(b, "_discover", lambda adir: None)
    assert b.bridge_convert_trajectory("whatever") is None
    assert b.load_bridge_messages("whatever") == []
    assert b.bridge_first_user_title("whatever") == ""
    assert b.is_server_available() is False


def test_load_bridge_messages_parses_discovered_markdown(monkeypatch):
    monkeypatch.setattr(b, "_discovery_cache", {})
    monkeypatch.setattr(b, "bridge_convert_trajectory", lambda cid, adir="antigravity": _SAMPLE)
    msgs = b.load_bridge_messages("cid")
    assert [m["role"] for m in msgs] == ["user", "model", "user", "model"]


def test_bridge_first_user_title_first_nonempty_line(monkeypatch):
    md = "### User Input\n\n\n\nMa vraie question\nsuite\n\n### Planner Response\n\nok\n"
    monkeypatch.setattr(b, "bridge_convert_trajectory", lambda cid, adir="antigravity": md)
    assert b.bridge_first_user_title("cid") == "Ma vraie question"


def test_discover_rejects_bad_app_data_dir(monkeypatch):
    # un app_data_dir non alphanumérique ne doit jamais atteindre subprocess
    called = []
    monkeypatch.setattr(b.subprocess, "run", lambda *a, **k: called.append(a) or None)
    monkeypatch.setattr(b, "_discovery_cache", {})
    assert b._discover("../evil; rm -rf") is None
    assert called == []


def test_discovery_result_is_cached(monkeypatch):
    calls = []

    def fake_run(*a, **k):
        calls.append(1)

        class R:
            stdout = '{"Token":"tok","Ports":"1,2"}'
            returncode = 0

        return R()

    monkeypatch.setattr(b.subprocess, "run", fake_run)
    monkeypatch.setattr(b, "_discovery_cache", {})
    a1 = b._discover("antigravity")
    a2 = b._discover("antigravity")
    assert a1 == ("tok", [1, 2])
    assert a2 == a1
    assert len(calls) == 1  # 2e appel servi par le cache
