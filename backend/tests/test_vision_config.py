"""P2: vision extraction config slots (v0.22.0, SCHEMA §2.5).

The two model slots plus render/cost knobs must exist in DEFAULT_CONFIG, and the
llm-config migration must preserve the now-canonical top-level `vision_model` while
still clearing the obsolete *nested* `ollama.vision_model` location.
"""

from curator import config as cfg


def test_default_config_has_vision_slots_and_knobs() -> None:
    llm = cfg.DEFAULT_CONFIG["llm"]
    # Two model slots, both empty (= disabled) by default, decoupled from primary/fallback.
    assert llm["vision_model"] == ""
    assert llm["latex_extract_model"] == ""
    # Render/cost knobs with the agreed defaults.
    assert llm["vision_render_dpi"] == 170
    assert llm["vision_max_image_px"] == 1600
    assert llm["vision_max_pages_per_run"] == 300


def test_migration_preserves_top_level_vision_model() -> None:
    config = {
        "llm": {
            "vision_model": "ollama::qwen2.5-vl:7b",
            "latex_extract_model": "claude-code::claude-haiku-4-5-20251001",
            "primary": "ollama::qwen2.5:7b",
        }
    }
    cfg._migrate_llm_config(config)
    # Canonical top-level keys survive migration.
    assert config["llm"]["vision_model"] == "ollama::qwen2.5-vl:7b"
    assert config["llm"]["latex_extract_model"] == "claude-code::claude-haiku-4-5-20251001"


def test_migration_still_strips_legacy_nested_ollama_vision_model() -> None:
    config = {
        "llm": {
            "vision_model": "ollama::qwen2.5-vl:7b",  # canonical, kept
            "ollama": {"vision_model": "legacy", "host": "http://localhost:11434"},
            "model": "obsolete-top-level",  # obsolete, stripped
        }
    }
    cfg._migrate_llm_config(config)
    assert config["llm"]["vision_model"] == "ollama::qwen2.5-vl:7b"  # top-level kept
    assert "vision_model" not in config["llm"]["ollama"]  # nested legacy stripped
    assert "model" not in config["llm"]  # obsolete top-level stripped
