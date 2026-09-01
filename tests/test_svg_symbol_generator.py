"""Unit tests for LLM-driven SVG symbol generation (Path 2)."""


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
    assert "JSON object" in prompt
    assert "circle" in prompt
    assert "no text" in prompt.lower() or "no text" in prompt
    # Spanish hint for es locales.
    es_prompt = build_shape_spec_prompt("agujero negro", "es")
    assert "Spanish" in es_prompt


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
