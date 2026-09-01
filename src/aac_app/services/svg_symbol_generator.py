"""
LLM-driven SVG symbol generation (Path 2: structured shapes, not raw markup).

A language model cannot natively generate images, but it can reliably emit a
small structured *shape spec* (JSON). We render that spec with ``drawsvg``,
which means we only ever write SVG tags and attributes we control — there is
no untrusted XML to sanitize, no ``<script>``/``on*``/external-URL injection
surface, and output is always well-formed.

Pipeline: label -> LLM JSON spec -> strict validation -> ``drawsvg`` render
-> SVG string. The caller persists the file and creates the symbol row.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from loguru import logger

# --- Allowed rendering vocabulary ----------------------------------------
# Only these shape kinds may appear in a spec. Each maps to a small set of
# numeric/color attributes; anything else in the model output is dropped.
_ALLOWED_KINDS = frozenset(
    {"circle", "ellipse", "rect", "line", "polygon", "polyline", "path"}
)

# Hex colors only (plus "none"). Named CSS colors are rejected so the model
# cannot smuggle e.g. ``url(javascript:...)`` through a fill value.
_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# AAC-appropriate meaning for ambiguous/homonym words, used when no learning
# topic is available to disambiguate (e.g. the home Smartbar). Without this
# the model deterministically picks its training prior: "cola" -> a soda
# bottle, "banco" -> a bank building, "beta" -> the Greek letter. A real
# topic context always wins over these defaults (see
# ``build_shape_spec_prompt``). Keys are normalized labels (stripped,
# lowercased, no accents stripped).
AAC_MEANING_HINTS: dict[str, str] = {
    "banco": "a bench to sit on",
    "beta": "a betta fish (small colorful aquarium fish)",
    "cola": "the tail of an animal",
    "copa": "a drinking cup or glass",
    "delta": "the triangular delta where a river meets the sea",
    "gato": "a cat (the pet animal)",
    "lima": "a green lime fruit",
    "llave": "a door key",
    "mango": "a mango fruit",
    "muñeca": "a doll",
    "pico": "a bird's beak",
    "ratón": "a small mouse (the animal, not a computer mouse)",
    "vela": "a candle",
}

# Unified drawing canvas: everything is centered in a 512x512 viewBox.
CANVAS = 512.0
_CENTER = CANVAS / 2.0

# Sanity bounds on geometry so a single runaway coordinate cannot produce a
# giant/blank canvas. Values are in canvas units.
_MAX_SHAPES = 24
_MAX_COORD = 1024.0
_MAX_RADIUS = CANVAS
_MAX_STROKE_WIDTH = 40.0


class ShapeSpecError(ValueError):
    """Raised when an LLM shape spec fails structural validation."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _parse_color(value: Any, default: str = "#333333") -> str:
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    if candidate.lower() == "none":
        return "none"
    if _COLOR_RE.match(candidate):
        return candidate
    logger.debug("Discarding invalid SVG color {!r}", value)
    return default


_PATH_COMMANDS = frozenset("MmLlHhVvCcSsQqTtAaZz")


def _apply_path_data(path: Any, d: str) -> Any:
    """Feed an SVG path ``d`` string into a drawsvg Path object.

    drawsvg exposes per-command methods (M/L/C/...) but no ``d`` parser, so
    we tokenize the (already length-/content-validated) string and dispatch
    each command. Only standard commands are accepted.
    """
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|-?\d*\.?\d+(?:[eE][+-]?\d+)?", d)
    if not tokens:
        return path
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok not in _PATH_COMMANDS:
            i += 1
            continue
        command = tok
        i += 1

        def take(count: int) -> list[float]:
            nonlocal i
            got: list[float] = []
            while i < len(tokens) and len(got) < count:
                t = tokens[i]
                if t in _PATH_COMMANDS:
                    break
                try:
                    got.append(float(t))
                except ValueError:
                    break
                i += 1
            return got

        try:
            if command in "Mm" or command in "Ll":
                n = take(2)
                if len(n) == 2:
                    getattr(path, command)(n[0], n[1])
            elif command in "Hh" or command in "Vv":
                n = take(1)
                if n:
                    getattr(path, command)(n[0])
            elif command in "Cc":
                n = take(6)
                if len(n) == 6:
                    getattr(path, command)(*n)
            elif command in "SsQqTt":
                args = 4 if command in "Qq" else 2
                n = take(args)
                if len(n) == args:
                    getattr(path, command)(*n)
            elif command in "Aa":
                n = take(7)
                if len(n) == 7:
                    rx, ry, rot, large, sweep, x, y = n
                    getattr(path, command)(rx, ry, rot, large, sweep, x, y)
            elif command in "Zz":
                path.Z()
        except (ValueError, TypeError):
            # A malformed segment ends the path gracefully instead of raising.
            break
    return path


def _point_pairs(value: Any, max_points: int = 32) -> list[tuple[float, float]] | None:
    """Validate a polygon/polyline points list: [[x, y], ...] within bounds.

    Points pass through in canvas-relative coordinates, exactly like every
    other shape's ``cx``/``cy``: the renderer's ``origin="center"`` applies
    the single +CENTER shift. Never shift them here — doing so double-shifts
    every polygon (+CENTER here, +CENTER again at render time), which pinned
    all polygon content to the bottom-right corner and clipped it at the
    canvas edge (the deterministic corner 'delta').
    """
    if not isinstance(value, list) or not value or len(value) > max_points:
        return None
    points: list[tuple[float, float]] = []
    for pair in value:
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not _is_number(pair[0])
            or not _is_number(pair[1])
        ):
            return None
        points.append(
            (
                _clamp(float(pair[0]), -_MAX_COORD, _MAX_COORD),
                _clamp(float(pair[1]), -_MAX_COORD, _MAX_COORD),
            )
        )
    return points


def _validate_one_shape(entry: Any) -> dict | None:
    """Validate one shape entry; returns the normalized dict or None.

    Unknown kinds and malformed geometry are dropped (never fatal) so one
    bad entry cannot poison the whole pictogram.
    """
    if not isinstance(entry, dict):
        return None
    kind = entry.get("kind")
    if kind not in _ALLOWED_KINDS:
        logger.debug("Discarding unsupported shape kind {!r}", kind)
        return None
    shape: dict = {
        "kind": kind,
        "fill": _parse_color(entry.get("fill"), "#d8d8d8"),
        "stroke": _parse_color(entry.get("stroke"), "none"),
    }
    sw = entry.get("stroke_width", 2)
    if isinstance(sw, (int, float)) and not isinstance(sw, bool):
        shape["stroke_width"] = _clamp(float(sw), 0.0, _MAX_STROKE_WIDTH)
    else:
        shape["stroke_width"] = 2.0

    def num(key: str, default: float) -> float:
        value = entry.get(key, default)
        if not _is_number(value):
            raise ShapeSpecError(f"shape {kind!r} attribute {key!r} is not numeric")
        # drawsvg uses ``origin="center"``, so the model's coordinates are
        # already relative to the canvas center — never re-shift them.
        return _clamp(float(value), -_MAX_COORD, _MAX_COORD)

    try:
        if kind == "circle":
            shape.update(
                cx=num("cx", 0.0),
                cy=num("cy", 0.0),
                r=_clamp(num("r", 50.0), 1.0, _MAX_RADIUS),
            )
        elif kind == "ellipse":
            shape.update(
                cx=num("cx", 0.0),
                cy=num("cy", 0.0),
                rx=_clamp(num("rx", 40.0), 1.0, _MAX_RADIUS),
                ry=_clamp(num("ry", 40.0), 1.0, _MAX_RADIUS),
            )
        elif kind == "rect":
            shape.update(
                x=num("x", -80.0),
                y=num("y", -80.0),
                w=_clamp(num("w", 120.0), 1.0, _MAX_COORD),
                h=_clamp(num("h", 120.0), 1.0, _MAX_COORD),
            )
        elif kind == "line":
            shape.update(
                x1=num("x1", -100.0),
                y1=num("y1", -100.0),
                x2=num("x2", 100.0),
                y2=num("y2", 100.0),
            )
        elif kind in {"polygon", "polyline"}:
            points = _point_pairs(entry.get("points"))
            if not points or len(points) < (3 if kind == "polygon" else 2):
                raise ShapeSpecError(f"shape {kind!r} has invalid points")
            shape["points"] = points
        elif kind == "path":
            d = entry.get("d")
            if not isinstance(d, str) or not (10 <= len(d) <= 4000):
                raise ShapeSpecError("path has invalid d attribute")
            # Path data is numeric commands only — reject letters outside
            # the SVG command set so no handler/text can sneak through.
            if re.search(r"(?i)<|script|onerror|href|url\(", d):
                raise ShapeSpecError("path contains forbidden tokens")
            shape["d"] = d
    except ShapeSpecError as exc:
        logger.debug("Discarding shape {}: {}", kind, exc)
        return None
    return shape


def validate_shape_spec(raw: Any) -> dict:
    """Validate and normalize a raw LLM shape spec into a renderable dict.

    Raises ``ShapeSpecError`` on structural failure; silently drops unknown
    keys/shapes so one weird entry cannot poison the whole picture.
    """
    if not isinstance(raw, dict):
        raise ShapeSpecError("spec is not an object")
    shapes_raw = raw.get("shapes")
    if not isinstance(shapes_raw, list):
        raise ShapeSpecError("spec has no shapes list")
    if not shapes_raw:
        raise ShapeSpecError("spec has an empty shapes list")
    if len(shapes_raw) > _MAX_SHAPES:
        raise ShapeSpecError(f"too many shapes: {len(shapes_raw)} > {_MAX_SHAPES}")

    shapes: list[dict] = []
    for entry in shapes_raw:
        shape = _validate_one_shape(entry)
        if shape is not None:
            shapes.append(shape)

    if not shapes:
        raise ShapeSpecError("no valid shapes survived validation")
    return {
        "background": _parse_color(raw.get("background"), "#ffffff"),
        "shapes": shapes,
    }


def render_spec_to_svg(spec: dict) -> str:
    """Render a validated shape spec into an SVG document string."""
    import drawsvg as draw  # Local import: generation is an optional feature.

    drawing = draw.Drawing(CANVAS, CANVAS, origin="center")
    drawing.append(draw.Rectangle(-_CENTER, -_CENTER, CANVAS, CANVAS, fill=spec["background"]))
    for shape in spec["shapes"]:
        kind = shape["kind"]
        common = {
            "fill": shape["fill"],
            "stroke": shape["stroke"],
            "stroke_width": shape["stroke_width"],
        }
        if kind == "circle":
            drawing.append(
                draw.Circle(shape["cx"], shape["cy"], shape["r"], **common)
            )
        elif kind == "ellipse":
            drawing.append(
                draw.Ellipse(shape["cx"], shape["cy"], shape["rx"], shape["ry"], **common)
            )
        elif kind == "rect":
            drawing.append(
                draw.Rectangle(shape["x"], shape["y"], shape["w"], shape["h"], **common)
            )
        elif kind == "line":
            drawing.append(
                draw.Line(shape["x1"], shape["y1"], shape["x2"], shape["y2"], **common)
            )
        elif kind == "polygon":
            path = draw.Path(**common)
            # Points are canvas-relative (see _point_pairs); origin="center"
            # on the Drawing applies the single shift to every shape alike.
            first = shape["points"][0]
            path.M(first[0], first[1])
            for x, y in shape["points"][1:]:
                path.L(x, y)
            path.Z()
            drawing.append(path)
        elif kind == "polyline":
            path = draw.Path(**common)
            first = shape["points"][0]
            path.M(first[0], first[1])
            for x, y in shape["points"][1:]:
                path.L(x, y)
            drawing.append(path)
        elif kind == "path":
            drawing.append(_apply_path_data(draw.Path(**common), shape["d"]))
    return drawing.as_svg()


def build_shape_spec_prompt(
    label: str, language: str, context: str | None = None
) -> str:
    """Prompt the model for a strict JSON shape spec (never raw SVG).

    Concept-driven, not primitive-driven: the model must first commit to ONE
    concrete object to draw (the ``draws:`` line, which the parser tolerates
    before the JSON), then compose shapes for that object. A sole-circle
    example anchors every output to that primitive, and without a per-concept
    decision step abstract words collapse into the same generic blob — the
    measured failure mode was nearly identical images for unrelated concepts
    ("energía del vacío" vs "teoría de cuerdas"). The example is therefore a
    3-shape heart built from parts, and paths/polygons are pushed over
    primitives because circles/rects cannot encode most meanings.

    ``context`` (usually the student's learning topic) disambiguates
    homonyms when present: "sierra" in a geography topic is a mountain
    range, in a tools topic a saw. It must stay a compact hint — the prompt
    is sent once per generated word, so every wasted token multiplies across
    a topic burst. The context affects only the first generation: once a
    word has a pictogram the catalog re-check reuses it regardless of topic.
    """
    lang_hint = "Spanish" if str(language).startswith("es") else "English"
    # An explicit learning topic wins; without one, fall back to the pinned
    # AAC meaning for ambiguous words so the home Smartbar still disambiguates
    # ("cola" -> tail, never a soda bottle).
    topic = (context or "").strip()
    if not topic:
        topic = AAC_MEANING_HINTS.get((label or "").strip().lower(), "")
    context_hint = ""
    if topic:
        concise = " ".join(topic.split())[:80]
        context_hint = (
            f"If \"{label}\" has several meanings, draw the meaning that "
            f"fits this context: \"{concise}\"; otherwise draw the most "
            "common everyday object.\n"
        )
    return (
        "Flat, colorful AAC pictogram for \""
        f"{label}\" ({lang_hint}); simple bold shapes, high contrast, "
        "ARASAAC style; no text, letters, numbers, or photos.\n"
        + context_hint
        + "If the concept is abstract or complex, pick the ONE concrete image "
        'people instantly associate with it (e.g. "materia oscura" -> dark '
        'blob with stars, "tristeza" -> sad face, "amistad" -> linked hands).\n'
        "First output one line starting with 'draws:' naming the object(s) "
        "your shapes will draw (max 10 words), then ONLY the JSON:\n"
        '{\n'
        '  "background": "#ffffff",\n'
        '  "shapes": [\n'
        '    { "kind": "circle", "cx": -45, "cy": -10, "r": 45, '
        '"fill": "#FFD166" },\n'
        '    { "kind": "circle", "cx": 45, "cy": -10, "r": 45, '
        '"fill": "#FFD166" },\n'
        '    { "kind": "polygon", "points": [[-50,-5],[50,-5],[0,70]], '
        '"fill": "#EF476F" }\n'
        "  ]\n"
        "}\n"
        "Canvas 512x512, centered at (0,0). Center the drawing; keep all "
        "shapes within about -200 to +200.\n"
        "Allowed kinds: circle, ellipse, rect, line, polygon, polyline, path. "
        "Use path or polygon for real outlines (umbrella canopy, wings, "
        "bodies, mountains, waves); use circle only for wheels, eyes, sun, "
        'spots. Fill/stroke: hex like "#FFD166" or "none". polygon/polyline '
        '"points" is a list of [x,y] pairs like [[0,0],[10,10]]. Max 8 '
        "shapes."
    )


def parse_spec_response(response: str) -> dict:
    """Extract and validate the JSON spec from an LLM response string."""
    text = (response or "").strip()
    if not text:
        raise ShapeSpecError("empty model response")
    # Strip markdown fences some providers wrap JSON in.
    if text.startswith("```"):
        text = text.strip("`")
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
    try:
        raw = json.loads(text)
    except (ValueError, TypeError) as exc:
        # Fall back to the first balanced {...} block, tolerating prose.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ShapeSpecError(f"no JSON object in response: {exc}") from exc
        try:
            raw = json.loads(text[start : end + 1])
        except (ValueError, TypeError) as inner:
            raise ShapeSpecError(f"invalid JSON spec: {inner}") from inner
    return validate_shape_spec(raw)


def generate_svg_text(
    label: str,
    language: str,
    generate_sync: Callable[..., str],
    context: str | None = None,
) -> str:
    """Ask the LLM for a pictogram shape spec and render it to an SVG string.

    ``generate_sync`` is the provider's synchronous generator (``prompt=``,
    ``temperature=``, ``max_tokens=`` kwargs). ``context`` (the learning
    topic) disambiguates homonyms — see ``build_shape_spec_prompt``. One
    retry is made when the model returns malformed JSON; raises
    ``ShapeSpecError`` when neither attempt was usable.
    """
    svg_text: str | None = None
    for attempt in range(2):
        prompt = build_shape_spec_prompt(label, language, context)
        if attempt > 0:
            prompt += (
                "\nThe previous attempt returned malformed JSON. "
                "Respond with ONLY valid JSON: no markdown, no trailing "
                "commas, no comments, no prose."
            )
        try:
            response = generate_sync(
                prompt=prompt,
                temperature=0.3,
                max_tokens=900,
            )
            spec = parse_spec_response(response)
            svg_text = render_spec_to_svg(spec)
            break
        except ShapeSpecError as exc:
            logger.warning(
                "Generated SVG spec rejected for {!r} (attempt {}): {}",
                label,
                attempt + 1,
                exc,
            )
    if not svg_text:
        raise ShapeSpecError(f"model did not return a valid shape spec for {label!r}")
    return svg_text


def rasterize_svg_text(svg_text: str, size: int | None = None) -> bytes | None:
    """Render an SVG string to PNG bytes via resvg, or None when unavailable.

    resvg-py is a pure-wheel Rust binding with no system cairo dependency. A
    `None` return (missing package, invalid SVG) lets callers fall back to
    storing the SVG itself, so a renderer problem never blocks generation.
    """
    if not isinstance(svg_text, str) or not svg_text.strip():
        return None
    try:
        import resvg_py
    except ImportError:
        return None
    try:
        kwargs: dict = {"svg_string": svg_text}
        if size is not None:
            kwargs["width"] = size
            kwargs["height"] = size
        data = resvg_py.svg_to_bytes(**kwargs)
        return bytes(data) if data else None
    except Exception as exc:
        logger.warning("SVG rasterization failed: {}", exc)
        return None


def write_generated_symbol_image(
    svg_text: str, uploads_dir, size: int = 512
) -> str:
    """Persist a generated pictogram, preferring PNG like other uploads.

    Writes ``<uploads_dir>/<uuid>.png`` when resvg is available and the
    rasterization succeeds; otherwise falls back to ``<uuid>.svg`` so the
    pictogram still works without the renderer. Returns the public path
    (``/uploads/symbols/<name>``) the Symbol row should store.
    """
    uploads_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.png"
    data = rasterize_svg_text(svg_text, size=size)
    if data is None:
        name = f"{uuid.uuid4().hex}.svg"
        data = svg_text.encode("utf-8")
    path = uploads_dir / name
    with path.open("wb") as f:
        f.write(data)
    return f"/uploads/symbols/{name}"
