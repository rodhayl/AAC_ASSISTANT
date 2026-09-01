"""Unit tests for LLM-driven SVG symbol generation (Path 2)."""

import io
from unittest.mock import patch

import pytest

from src.aac_app.services.svg_symbol_generator import (
    ShapeSpecError,
    build_shape_spec_prompt,
    parse_spec_response,
    rasterize_svg_text,
    render_spec_to_svg,
    validate_shape_spec,
    write_generated_symbol_image,
)

# --- spec validation ------------------------------------------------------


def test_validate_shape_spec_accepts_all_supported_kinds():
    spec = {
        "background": "#ffffff",
        "shapes": [
            {"kind": "circle", "cx": 0, "cy": 0, "r": 40, "fill": "#FFD166"},
            {"kind": "ellipse", "cx": 0, "cy": 0, "rx": 30, "ry": 20, "fill": "#4A90E2"},
            {"kind": "rect", "x": -40, "y": -40, "w": 80, "h": 40, "fill": "#8A9DA8"},
            {"kind": "line", "x1": -60, "y1": -60, "x2": 60, "y2": 60, "stroke": "#333333", "stroke_width": 4},
            {"kind": "polygon", "points": [[0, 40], [30, 80], [0, 120], [-30, 80]], "fill": "#4C9F70"},
            {"kind": "polyline", "points": [[-80, -80], [-40, -120], [0, -80]], "stroke": "#333333", "stroke_width": 2},
            {"kind": "path", "d": "M -100,-100 C -50,150 50,150 100,-100 Z", "fill": "#66CC99"},
        ],
    }
    normalized = validate_shape_spec(spec)
    assert [s["kind"] for s in normalized["shapes"]] == [
        "circle",
        "ellipse",
        "rect",
        "line",
        "polygon",
        "polyline",
        "path",
    ]
    # Colors are enforced; canvas-relative coords pass through unshifted.
    assert normalized["background"] == "#ffffff"
    assert normalized["shapes"][0]["cx"] == 0


def test_validate_shape_spec_rejects_injection_vectors():
    # Executable/event-handler tags are not in the allowed kind set.
    with pytest.raises(ShapeSpecError, match="no valid shapes"):
        validate_shape_spec({"shapes": [{"kind": "script", "content": "alert(1)"}]})
    # javascript: URLs are not hex colors -> sanitized to default, not kept.
    normalized = validate_shape_spec(
        {"shapes": [{"kind": "circle", "cx": 0, "cy": 0, "r": 10, "fill": "url(javascript:alert(1))"}]}
    )
    assert normalized["shapes"][0]["fill"] == "#d8d8d8"
    # Path data cannot smuggle markup or handlers -> the shape is discarded
    # and, with nothing left to render, the whole spec is rejected.
    with pytest.raises(ShapeSpecError, match="no valid shapes"):
        validate_shape_spec({"shapes": [{"kind": "path", "d": "M 0,0 <script> alert(2)"}]})
    with pytest.raises(ShapeSpecError, match="no valid shapes"):
        validate_shape_spec({"shapes": [{"kind": "path", "d": "M 0,0 L 1,1 url(https://x)"}]})


def test_validate_shape_spec_rejects_structural_nonsense():
    with pytest.raises(ShapeSpecError, match="not an object"):
        validate_shape_spec("[]")
    with pytest.raises(ShapeSpecError, match="empty shapes list"):
        validate_shape_spec({"shapes": []})
    with pytest.raises(ShapeSpecError, match="too many shapes"):
        validate_shape_spec(
            {
                "shapes": [
                    {"kind": "circle", "cx": 0, "cy": 0, "r": 10}
                    for _ in range(50)
                ]
            }
        )
    # Non-numeric geometry drops the shape, and if nothing survives it fails.
    with pytest.raises(ShapeSpecError, match="no valid shapes"):
        validate_shape_spec({"shapes": [{"kind": "circle", "cx": "x", "cy": 0, "r": 10}]})


def test_polygon_points_stay_relative_and_render_centered():
    """Regression: polygon/polyline points were shifted by +CENTER in
    validation while the renderer's origin="center" shifts them again,
    double-moving every polygon 256px down-right and clipping it to the
    canvas corner. This was the deterministic corner-pinned 'delta': the
    model drew a perfectly centered triangle and the renderer butchered it.
    Points must pass through relative (like cx/cy) so the single render-time
    shift lands them centered."""
    from PIL import Image

    spec = validate_shape_spec(
        {
            "background": "#ffffff",
            "shapes": [
                {
                    "kind": "polygon",
                    "points": [[-100, 80], [100, 80], [0, -120]],
                    "fill": "#EF476F",
                },
            ],
        }
    )
    # Unit level: validation keeps points relative to the canvas center.
    assert spec["shapes"][0]["points"] == [(-100.0, 80.0), (100.0, 80.0), (0.0, -120.0)]
    # End to end: the rendered raster has the triangle centered, not pinned
    # to the corner (256px render of the 512px SVG halves pixel units).
    png = rasterize_svg_text(render_spec_to_svg(spec), size=256)
    assert png is not None
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    w, h = im.size
    px = im.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 40 and not (r > 235 and g > 235 and b > 235):
                xs.append(x)
                ys.append(y)
    assert xs, "polygon should be visible"
    size = max(max(xs) - min(xs), max(ys) - min(ys))
    cx = (min(xs) + max(xs)) / 2 - w / 2
    cy = (min(ys) + max(ys)) / 2 - h / 2
    assert size > 60, f"polygon clipped by double-shift (size={size})"
    assert abs(cx) <= 25 and abs(cy) <= 25, (
        f"polygon corner-pinned: offset=({cx:.0f},{cy:.0f})"
    )


def test_render_spec_produces_well_formed_safe_svg():
    import xml.etree.ElementTree as ET

    spec = {
        "background": "#ffffff",
        "shapes": [
            {"kind": "circle", "cx": 0, "cy": 0, "r": 60, "fill": "#FFD166"},
            {"kind": "rect", "x": -80, "y": 40, "w": 160, "h": 40, "fill": "#4A90E2"},
            {"kind": "path", "d": "M -100,-100 C -50,150 50,150 100,-100 Z", "fill": "#66CC99"},
        ],
    }
    svg = render_spec_to_svg(validate_shape_spec(spec))
    root = ET.fromstring(svg)  # well-formed XML
    tags = {el.tag.split("}")[-1] for el in root.iter()}
    assert tags <= {"svg", "defs", "rect", "circle", "path", "line", "ellipse", "polyline", "polygon"}
    assert "script" not in svg
    assert "onerror" not in svg


def test_parse_spec_response_handles_fences_and_prose():
    fenced = '```json\n{"background":"#fff","shapes":[{"kind":"circle","cx":0,"cy":0,"r":30,"fill":"#FFD166"}]}\n```'
    spec = parse_spec_response(fenced)
    assert spec["shapes"][0]["kind"] == "circle"
    assert spec["background"].startswith("#")

    with_prose = (
        'Here is your pictogram:\n{"background": "#ffffff",'
        '"shapes": [{"kind": "circle", "cx": 0, "cy": 0, "r": 20, "fill": "#000000"}]}'
    )
    assert parse_spec_response(with_prose)["shapes"][0]["r"] == 20

    with pytest.raises(ShapeSpecError):
        parse_spec_response("no json here at all")


def test_build_shape_spec_prompt_constrains_output():
    prompt = build_shape_spec_prompt("black hole", "en")
    # Every quality-critical element must survive: the JSON schema anchor,
    # the coordinate system, the allowed kinds, and the style rules.
    for required in (
        '"background"',
        '"shapes"',
        '"kind"',
        "circle",
        "ellipse",
        "polyline",
        "#FFD166",
        "512",
        "-200",
        "no text",
        "black hole",
    ):
        assert required in prompt
    # Spanish hint for es locales.
    es_prompt = build_shape_spec_prompt("agujero negro", "es")
    assert "Spanish" in es_prompt


def test_build_shape_spec_prompt_is_concept_driven():
    """The prompt must force a per-concept decision before the shapes: a
    ``draws:`` plan line plus a composed example (a heart built from parts),
    never a bare primitive anchor. Without these, abstract words collapsed
    into the same generic blob — measured as near-identical images for
    unrelated concepts ("energía del vacío" vs "teoría de cuerdas")."""
    prompt = build_shape_spec_prompt("materia oscura", "es")
    assert "draws:" in prompt
    assert "ONE concrete image" in prompt
    # The example must teach composition (2 circles + 1 polygon heart), not
    # anchor a single primitive.
    assert prompt.count('"kind": "circle"') >= 2
    assert '"kind": "polygon"' in prompt
    assert "[[-50,-5],[50,-5],[0,70]]" in prompt
    # Real outlines via path/polygon are pushed over bare primitives.
    assert "Use path or polygon for real outlines" in prompt
    assert "umbrella canopy" in prompt


def test_build_shape_spec_prompt_carries_disambiguation_context():
    """A passed context (learning topic) adds a homonym-disambiguation rule
    so "sierra"/"llave"-style words resolve to the student's theme; without
    context the prompt keeps the previous generic-wording behavior."""
    plain = build_shape_spec_prompt("sierra", "es")
    assert "has several meanings" not in plain
    assert "fits this context" not in plain

    prompt = build_shape_spec_prompt("sierra", "es", context="geografía")
    assert 'If "sierra" has several meanings' in prompt
    assert 'fits this context: "geografía"' in prompt
    # The disambiguation line sits before the abstract-concept instruction so
    # concrete meanings win over arbitrary symbols.
    assert prompt.index("has several meanings") < prompt.index("abstract or complex")

    # Long / noisy contexts are truncated to an ~80-char hint so the
    # per-pictogram token budget cannot balloon with the topic string.
    loud = "   " + "carpintería " * 60
    trimmed = build_shape_spec_prompt("sierra", "es", context=loud)
    assert 'fits this context: "carpintería' in trimmed
    nine_words = " ".join(["carpintería"] * 9)
    assert nine_words not in trimmed  # truncated, not echoed in full
    assert len(trimmed) < len(plain) + 240


# --- ambiguous-word AAC meaning regression suite --------------------------
# The ambiguous-word audit (letters + homonyms, 3 live runs each) found the
# model deterministically picks a homonym meaning with no way to know the
# student's theme ("cola" -> soda bottle, "banco" -> bank building, "beta" ->
# the Greek letter). These tests pin the AAC-appropriate meaning for every
# audited word and prove the hint reaches the effective prompt.


def test_aac_meaning_hints_cover_every_audited_ambiguous_word():
    """Every audited ambiguous word has a pinned AAC meaning (or is
    deliberately left to the topic context), so the no-topic Smartbar cannot
    silently drift back to the misleading training prior."""
    from src.aac_app.services.svg_symbol_generator import AAC_MEANING_HINTS

    audited = {
        "banco", "beta", "cola", "copa", "delta", "gato", "lima",
        "llave", "mango", "muñeca", "omega", "pico", "ratón",
        "sierra", "vela",
    }
    # "omega" (the letter itself is the meaning) and "sierra" (mountains vs
    # saw genuinely needs the topic) are intentionally not pinned statically.
    assert audited - {"omega", "sierra"} <= set(AAC_MEANING_HINTS)


def test_each_aac_meaning_hint_reaches_the_no_topic_prompt():
    """The pinned meaning is embedded in the effective prompt for every
    audited word, so the background generation actually receives it."""
    from src.aac_app.services.svg_symbol_generator import AAC_MEANING_HINTS

    for word, meaning in AAC_MEANING_HINTS.items():
        prompt = build_shape_spec_prompt(word, "es")
        assert f'If "{word}" has several meanings' in prompt
        assert f'fits this context: "{meaning}"' in prompt


def test_aac_meaning_spot_checks_pin_appropriate_meanings():
    """The classic offenders resolve to the classroom meaning, not the
    model's training prior (soda / bank / Greek letter / computer)."""
    from src.aac_app.services.svg_symbol_generator import AAC_MEANING_HINTS

    assert "tail" in AAC_MEANING_HINTS["cola"]
    assert "bottle" not in AAC_MEANING_HINTS["cola"]
    assert "bench" in AAC_MEANING_HINTS["banco"]
    assert "bank building" not in AAC_MEANING_HINTS["banco"]
    assert "betta fish" in AAC_MEANING_HINTS["beta"]
    assert "letter" not in AAC_MEANING_HINTS["beta"]
    # The animal meaning is selected; the computer-mouse sense is explicitly
    # excluded, not presented as an option.
    assert "the animal" in AAC_MEANING_HINTS["ratón"]
    assert "not a computer mouse" in AAC_MEANING_HINTS["ratón"]
    assert "door key" in AAC_MEANING_HINTS["llave"]


def test_explicit_topic_overrides_static_meaning_hint():
    """A real learning topic wins over the pinned default, so a tools board
    can still turn "sierra"-style words toward the theme's meaning."""
    prompt = build_shape_spec_prompt("cola", "es", context="animales de la granja")
    assert 'fits this context: "animales de la granja"' in prompt
    assert 'fits this context: "the tail of an animal"' not in prompt


def test_no_meaning_hint_without_ambiguous_word_or_topic():
    """Unambiguous words (and unknown ones) get no disambiguation line, so
    the token budget stays stable outside the pinned set."""
    assert "has several meanings" not in build_shape_spec_prompt("gato feliz", "es")
    assert "has several meanings" not in build_shape_spec_prompt("telescopio", "es")


def test_build_shape_spec_prompt_requires_centered_placement():
    """The prompt must keep telling the model to center the drawing and to
    stay within a sensible radius: corner-placed pictograms (a shape at far
    coordinates surviving validation) are the main output outlier, and the
    constraint is what keeps them rare."""
    prompt = build_shape_spec_prompt("corazón", "es")
    assert "Center the drawing" in prompt
    assert "keep all shapes within" in prompt and "-200" in prompt


def test_build_shape_spec_prompt_spells_out_polygon_points_format():
    """The model emits polygon points as flat SVG strings ("-120,80 0,-120")
    unless told otherwise, and validation drops those — which is why
    mountain-type pictograms rendered as an off-center leftover circle. The
    prompt must spell out the list-of-pairs format."""
    prompt = build_shape_spec_prompt("montaña", "es")
    assert "[x,y]" in prompt
    assert "[[0,0],[10,10]]" in prompt


def test_build_shape_spec_prompt_stays_under_token_budget():
    """The per-pictogram prompt is the biggest LLM-cost lever (sent once per
    generated word), so it must stay compact. The concept-driven rewrite
    (draws: plan + heart example + outline instruction) measures ~1190 chars
    ≈ ~400 tokens; the cap allows that wording to evolve without silently
    ballooning the cost again."""
    prompt = build_shape_spec_prompt("agujero negro", "es")
    assert len(prompt) <= 1250


# --- rasterization -------------------------------------------------------


def test_rasterize_svg_text_returns_valid_png():
    svg = render_spec_to_svg(
        validate_shape_spec(
            {
                "background": "#ffffff",
                "shapes": [
                    {"kind": "circle", "cx": 0, "cy": 0, "r": 60, "fill": "#FFD166"},
                ],
            }
        )
    )
    png = rasterize_svg_text(svg, size=256)
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_rasterize_svg_text_returns_none_without_resvg():
    with patch.dict("sys.modules", {"resvg_py": None}):
        assert rasterize_svg_text("<svg></svg>") is None
    assert rasterize_svg_text("") is None
    assert rasterize_svg_text("not valid svg at all") is None


def test_write_generated_symbol_image_prefers_png(tmp_path):
    svg = render_spec_to_svg(
        validate_shape_spec(
            {
                "background": "#ffffff",
                "shapes": [
                    {"kind": "circle", "cx": 0, "cy": 0, "r": 60, "fill": "#FFD166"},
                ],
            }
        )
    )
    public_path = write_generated_symbol_image(svg, tmp_path)
    assert public_path.startswith("/uploads/symbols/")
    assert public_path.endswith(".png")
    saved = tmp_path / public_path.rsplit("/", 1)[1]
    assert saved.is_file()
    assert saved.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_write_generated_symbol_image_falls_back_to_svg(tmp_path):
    svg = render_spec_to_svg(
        validate_shape_spec(
            {
                "background": "#ffffff",
                "shapes": [
                    {"kind": "circle", "cx": 0, "cy": 0, "r": 60, "fill": "#FFD166"},
                ],
            }
        )
    )
    with patch(
        "src.aac_app.services.svg_symbol_generator.rasterize_svg_text",
        return_value=None,
    ):
        public_path = write_generated_symbol_image(svg, tmp_path)
    assert public_path.endswith(".svg")
    saved = tmp_path / public_path.rsplit("/", 1)[1]
    assert saved.is_file()
    assert saved.read_text(encoding="utf-8").startswith("<?xml")


# --- endpoint wiring ------------------------------------------------------


def test_generate_svg_symbol_route_creates_symbol_with_svg(
    test_db_session, admin_user, tmp_path, monkeypatch
):
    """A fake provider spec flows through the route and persists an .svg file."""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    import src.api.routers.symbols as symbols_module
    from src import config
    from src.api.deps import get_current_staff_user, get_db
    from src.api.main import app

    # Keep the file out of the real uploads dir and DB out of the real dev DB.
    monkeypatch.setattr(config, "UPLOADS_DIR", tmp_path, raising=False)
    (tmp_path / "symbols").mkdir(parents=True, exist_ok=True)

    class _FakeProvider:
        def generate_sync(self, prompt, **kwargs) -> str:
            return (
                '{"background":"#ffffff",'
                '"shapes":[{"kind":"circle","cx":0,"cy":0,"r":60,"fill":"#FFD166"},'
                '{"kind":"circle","cx":0,"cy":0,"r":30,"fill":"#000000"}]}'
            )

    fake_provider = _FakeProvider()
    # symbols.py binds get_llm_provider into its own namespace at import time.
    patch_target = patch.object(symbols_module, "get_llm_provider", return_value=fake_provider)
    patch_target.start()
    app.dependency_overrides[get_db] = lambda: test_db_session
    app.dependency_overrides[get_current_staff_user] = lambda: admin_user
    try:
        client = TestClient(app)
        response = client.post(
            "/api/boards/symbols/generate-svg",
            data={"label": "agujero negro", "language": "es", "category": "space"},
        )
    finally:
        app.dependency_overrides.clear()
        patch_target.stop()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["label"] == "agujero negro"
    assert body["image_path"].startswith("/uploads/symbols/")
    assert body["image_path"].endswith(".png")
    # The symbol row was created in the test DB, and the PNG file exists.
    saved = (tmp_path / "symbols" / body["image_path"].rsplit("/", 1)[1])
    assert saved.is_file()
    assert saved.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
