"""test_config.py — Tests unitaires pour le module de configuration."""

import json
from pathlib import Path
import pytest

from config import (
    load_config,
    save_config,
    get_projects_root,
    get_antigravity_root,
    get_claude_root,
    CONFIG_FILE,
    DEFAULT_PROJECTS_ROOT,
    DEFAULT_ANTIGRAVITY_ROOT,
    DEFAULT_CLAUDE_ROOT,
)


def test_default_roots():
    """Vérifie que les racines par défaut retournent des chemins valides."""
    p_root = get_projects_root()
    ag_root = get_antigravity_root()

    assert isinstance(p_root, Path)
    assert isinstance(ag_root, Path)
    assert len(str(p_root)) > 0
    assert len(str(ag_root)) > 0


def test_save_and_load_config(tmp_path, monkeypatch):
    """Vérifie que la sauvegarde et la relecture de configuration fonctionnent fidèlement."""
    dummy_config_file = tmp_path / "config.json"
    monkeypatch.setattr("config.CONFIG_FILE", dummy_config_file)

    test_data = {
        "projects_root": str(tmp_path / "Projects"),
        "antigravity_root": str(tmp_path / "Gemini"),
        "theme": "dark",
    }
    save_config(test_data)
    assert dummy_config_file.is_file()

    loaded = load_config()
    assert loaded["projects_root"] == test_data["projects_root"]
    assert loaded["antigravity_root"] == test_data["antigravity_root"]
    assert loaded["theme"] == "dark"


def test_get_roots_with_custom_config(tmp_path, monkeypatch):
    """Vérifie que get_projects_root et get_antigravity_root respectent config.json."""
    dummy_config_file = tmp_path / "config.json"
    monkeypatch.setattr("config.CONFIG_FILE", dummy_config_file)

    custom_p = tmp_path / "CustomProjects"
    custom_ag = tmp_path / "CustomAntigravity"
    custom_p.mkdir()
    custom_ag.mkdir()

    save_config({
        "projects_root": str(custom_p),
        "antigravity_root": str(custom_ag),
    })

    assert get_projects_root() == custom_p
    assert get_antigravity_root() == custom_ag


def test_claude_root_default_is_literal_userprofile(tmp_path, monkeypatch):
    """Le défaut de claude_root est stocké LITTÉRALEMENT (%USERPROFILE%…) et
    résolu seulement à la lecture par get_claude_root()."""
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    assert DEFAULT_CLAUDE_ROOT == r"%USERPROFILE%\.claude\projects"
    assert load_config()["claude_root"] == DEFAULT_CLAUDE_ROOT
    # get_claude_root résout la variable d'environnement.
    resolved = get_claude_root()
    assert "%USERPROFILE%" not in str(resolved)
    assert str(resolved).replace("\\", "/").endswith(".claude/projects")


def test_antigravity_root_default_is_literal_userprofile(tmp_path, monkeypatch):
    """Le défaut d'antigravity_root est stocké LITTÉRALEMENT (%USERPROFILE%…),
    comme claude_root : sinon la variable disparaît à la 1ère sauvegarde des
    Paramètres et le champ affiche un chemin résolu figé."""
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    assert DEFAULT_ANTIGRAVITY_ROOT.startswith("%USERPROFILE%")
    assert load_config()["antigravity_root"] == DEFAULT_ANTIGRAVITY_ROOT
    resolved = get_antigravity_root()
    assert "%USERPROFILE%" not in str(resolved)
    assert str(resolved).replace("\\", "/").endswith(".gemini/antigravity-ide") \
        or str(resolved).replace("\\", "/").endswith(".gemini/antigravity")


def test_antigravity_root_var_survives_save(tmp_path, monkeypatch):
    """Une valeur saisie avec %USERPROFILE% dans les Paramètres est ré-écrite
    telle quelle par save_config (aucune résolution au passage)."""
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    cfg = load_config()
    cfg["antigravity_root"] = r"%USERPROFILE%\.gemini\antigravity-ide"
    save_config(cfg)
    assert load_config()["antigravity_root"] == r"%USERPROFILE%\.gemini\antigravity-ide"


def test_get_claude_root_respects_custom_config(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    custom = tmp_path / "ailleurs" / "claude"
    save_config({"claude_root": str(custom)})
    assert get_claude_root() == custom


def test_get_claude_root_expands_vars_in_custom_config(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setenv("MYVAR", str(tmp_path))
    save_config({"claude_root": r"%MYVAR%\sub"})
    assert get_claude_root() == tmp_path / "sub"


def test_theme_functions(tmp_path, monkeypatch):
    """Vérifie le comportement de detect_system_theme et get_active_theme."""
    from config import detect_system_theme, get_active_theme

    dummy_config_file = tmp_path / "config.json"
    monkeypatch.setattr("config.CONFIG_FILE", dummy_config_file)

    # 1. Thème forcé clair
    save_config({"theme": "light"})
    assert get_active_theme() == "light"

    # 2. Thème forcé sombre
    save_config({"theme": "dark"})
    assert get_active_theme() == "dark"

    # 3. Thème système
    save_config({"theme": "system"})
    sys_theme = detect_system_theme()
    assert sys_theme in ("light", "dark")
    assert get_active_theme() == sys_theme


def test_version_and_changelog(tmp_path, monkeypatch):
    """Vérifie le chargement de la version et du changelog."""
    from config import get_app_version, get_last_seen_version, set_last_seen_version, get_changelog_data

    dummy_config_file = tmp_path / "config.json"
    monkeypatch.setattr("config.CONFIG_FILE", dummy_config_file)

    # Version par défaut ou depuis VERSION
    v = get_app_version()
    assert isinstance(v, str)
    assert len(v) > 0

    # Gestion de last_seen_version
    assert get_last_seen_version() == ""
    set_last_seen_version("1.0")
    assert get_last_seen_version() == "1.0"

    # Données du changelog
    ch = get_changelog_data()
    assert isinstance(ch, dict)
    assert "v1.1" in ch
    assert "v1.0" in ch
    assert "✨ Nouvelles fonctionnalités (feat)" in ch["v1.1"]
    assert "✨ Nouvelles fonctionnalités (feat)" in ch["v1.0"]


