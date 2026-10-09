import site_config


def test_normalize_drops_invalid_values():
    cfg = site_config.normalize_config({
        "theme": {"preset": "nope", "primary": "red;}</style>", "accent": "#ABCDEF", "font": "comic", "hero_style": "light"},
        "texts": {"hero_title": "x" * 500, "unknown": "y"},
        "home_sections": ["contact", "bogus", "contact", "intro"],
        "worship_schedule": [{"name": "주일 예배", "time": "11시"}, {"name": "", "time": "버려짐"}, "bad"],
        "logo_path": "https://evil.example/x.png",
        "about_images": ["/uploads/3/about_ab.png", "/uploads/../etc/passwd"],
    })
    assert cfg["theme"]["preset"] == "classic"
    assert cfg["theme"]["primary"] == site_config.DEFAULT_CONFIG["theme"]["primary"]
    assert cfg["theme"]["accent"] == "#abcdef"
    assert cfg["theme"]["font"] == "noto-sans"
    assert cfg["theme"]["hero_style"] == "light"
    assert len(cfg["texts"]["hero_title"]) == site_config.TEXT_LIMITS["hero_title"]
    assert "unknown" not in cfg["texts"]
    assert cfg["home_sections"] == ["contact", "intro"]
    assert cfg["worship_schedule"] == [{"name": "주일 예배", "time": "11시"}]
    assert cfg["logo_path"] == ""
    assert cfg["about_images"] == ["/uploads/3/about_ab.png"]


def test_catalog_theme_keeps_church_texts():
    base = site_config.normalize_config({"texts": {"hero_title": "우리 교회"}, "worship_schedule": [{"name": "새벽기도", "time": "5시"}]})
    cfg = site_config.apply_catalog_theme(base, "forest")
    assert cfg["theme"]["preset"] == "forest"
    assert cfg["home_sections"] == site_config.THEME_PRESETS["forest"]["home_sections"]
    assert cfg["texts"]["hero_title"] == "우리 교회"
    assert cfg["worship_schedule"] == [{"name": "새벽기도", "time": "5시"}]


def test_catalog_entries_are_valid():
    for key, item in site_config.THEME_PRESETS.items():
        cfg = site_config.apply_catalog_theme(site_config.normalize_config(None), key)
        assert cfg["theme"]["primary"] == item["primary"]
        assert cfg["theme"]["font"] == item["font"]
        assert set(cfg["home_sections"]) == set(site_config.HOME_SECTIONS)


def test_theme_css_only_contains_hex_colors():
    css = site_config.theme_css(site_config.normalize_config({"theme": {"primary": "#123456"}}))
    assert "--primary-color:#123456" in css
    assert "</style" not in css


def test_ai_schema_matches_normalizer():
    schema = site_config.AI_CONFIG_SCHEMA
    assert set(schema["properties"]["texts"]["required"]) == set(site_config.TEXT_LIMITS) - {"concept"}
    assert schema["properties"]["theme"]["properties"]["preset"]["enum"] == list(site_config.THEME_PRESETS)
