"""Tests for config loading and merging."""
from claude_code_talker.config import deep_merge, load_global_config


def test_deep_merge_overrides_leaves():
    a = {"x": 1, "y": {"z": 2}}
    b = {"y": {"z": 3, "w": 4}}
    assert deep_merge(a, b) == {"x": 1, "y": {"z": 3, "w": 4}}


def test_deep_merge_replaces_lists():
    a = {"items": [1, 2]}
    b = {"items": [3]}
    assert deep_merge(a, b) == {"items": [3]}


def test_deep_merge_handles_none_override():
    a = {"x": 1}
    assert deep_merge(a, None) == {"x": 1}
    assert deep_merge(a, {}) == {"x": 1}


def test_load_global_config_applies_preset(tmp_path):
    cfg_path = tmp_path / "tts_config.yaml"
    cfg_path.write_text("preset: brief\nvoice:\n  model: foo\n")
    cfg = load_global_config(cfg_path)
    assert cfg["voice"]["model"] == "foo"
    assert cfg["text"]["max_chars"] == 1000  # from brief preset
    assert cfg["content_filter"]["mode"] == "blacklist"


def test_load_global_config_user_wins_over_preset(tmp_path):
    cfg_path = tmp_path / "tts_config.yaml"
    cfg_path.write_text("preset: brief\ntext:\n  max_chars: 500\n")
    cfg = load_global_config(cfg_path)
    assert cfg["text"]["max_chars"] == 500  # user override beats preset 1000


def test_load_global_config_missing_file_returns_defaults(tmp_path):
    cfg = load_global_config(tmp_path / "nonexistent.yaml")
    assert cfg.get("enabled", True) is True


def test_load_global_config_malformed_yaml_returns_defaults(tmp_path):
    cfg_path = tmp_path / "tts_config.yaml"
    # Tab character inside a block mapping reliably triggers yaml.scanner.ScannerError
    cfg_path.write_text("key:\n\t  bad_indent: value\n")
    cfg = load_global_config(cfg_path)
    assert cfg == {"enabled": True}


def test_load_global_config_non_dict_top_level_returns_defaults(tmp_path):
    cfg_path = tmp_path / "tts_config.yaml"
    cfg_path.write_text("just a string\n")
    cfg = load_global_config(cfg_path)
    assert cfg == {"enabled": True}


from claude_code_talker.config import find_workspace_config, translate_workspace_overrides, load_full_config


def test_find_workspace_config_walks_up(tmp_path):
    # Create nested folder structure with .claude/tts_workspace.yaml at the root
    root = tmp_path / "project"
    nested = root / "src" / "subdir"
    nested.mkdir(parents=True)
    cfg_dir = root / ".claude"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "tts_workspace.yaml"
    cfg_file.write_text("voice: foo\n")

    found = find_workspace_config(str(nested))
    assert found == cfg_file


def test_find_workspace_config_returns_none_when_absent(tmp_path):
    assert find_workspace_config(str(tmp_path)) is None


def test_translate_workspace_voice():
    ws = {"voice": "en_US-test", "rate": 1.2}
    o = translate_workspace_overrides(ws)
    assert o["voice"]["model"] == "en_US-test"
    assert o["voice"]["rate"] == 1.2


def test_translate_workspace_prose_levels():
    assert translate_workspace_overrides({"prose": "none"})["content_filter"]["mode"] == "suppress"
    assert translate_workspace_overrides({"prose": "conclusions"})["content_filter"]["mode"] == "whitelist"
    assert translate_workspace_overrides({"prose": "full"})["content_filter"]["mode"] == "blacklist"


def test_translate_workspace_synopsis_levels():
    assert translate_workspace_overrides({"synopsis": "none"})["synopsis"]["enabled"] is False
    o = translate_workspace_overrides({"synopsis": "full"})
    assert o["synopsis"]["enabled"] is True
    assert o["synopsis"]["style"] == "full"


def test_translate_workspace_todos():
    o = translate_workspace_overrides({"todos": {"completed": "speak"}})
    assert o["todos"]["speak_completed"] is True
    o = translate_workspace_overrides({"todos": {"completed": "skip"}})
    assert o["todos"]["speak_completed"] is False


def test_translate_workspace_elements():
    o = translate_workspace_overrides({
        "code_blocks": "speak",
        "tables": "stub",
        "insight_blocks": "speak",
    })
    assert o["elements"]["code_block"] is True
    assert o["elements"]["table"] is False
    assert o["elements"]["insight_block"] is True


def test_translate_workspace_paths():
    assert translate_workspace_overrides({"file_paths": "omit"})["paths"]["handling"] == "omit"
    assert translate_workspace_overrides({"file_paths": "filename"})["paths"]["handling"] == "filename"


def test_load_full_config_handles_non_dict_workspace_yaml(tmp_path):
    ws_root = tmp_path / "project"
    ws_root.mkdir()
    (ws_root / ".claude").mkdir()
    # Top-level list, not dict — would crash translate_workspace_overrides without guard
    (ws_root / ".claude" / "tts_workspace.yaml").write_text("- voice: foo\n- rate: 1.5\n")

    # Should not raise
    cfg = load_full_config(global_path=tmp_path / "nonexistent.yaml", cwd=str(ws_root))
    assert cfg.get("enabled", True) is True


def test_load_full_config_merges_workspace(tmp_path):
    # Global config
    global_path = tmp_path / "global.yaml"
    global_path.write_text("preset: brief\nvoice:\n  model: global_voice\n")

    # Workspace config nested
    ws_root = tmp_path / "project"
    ws_root.mkdir()
    (ws_root / ".claude").mkdir()
    (ws_root / ".claude" / "tts_workspace.yaml").write_text("voice: workspace_voice\n")

    cfg = load_full_config(global_path=global_path, cwd=str(ws_root))
    assert cfg["voice"]["model"] == "workspace_voice"  # workspace wins
    assert cfg["text"]["max_chars"] == 1000  # preset default still applied
