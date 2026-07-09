"""P2: vision extraction config slots (v0.22.0, SCHEMA §2.5)."""

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
