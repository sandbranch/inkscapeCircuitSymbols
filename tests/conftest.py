# Copyright 2026 David
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Run this extension the way Inkscape does: a fresh Python with the
dialog's default values from the .inx, inkscapeMadeEasy importable as a
package, and no TexText (plain text labels). Set INKSCAPE_MADEEASY to
inkscapeMadeEasy's latest/ folder; by default a checkout next to this
one (../inkscapeMadeEasy). Needs inkex 1.4.
"""

import io
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import inkex
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = os.path.join(ROOT, "latest")
NS = "{http://www.inkscape.org/namespace/inkscape/extension}"

# the same 100 mm line in a document drawn in mm (Inkscape 1.x A4), in px
# (Inkscape 0.92) and in 2 mm per user unit
DOCS = {
    "mm": ('width="210mm" height="297mm" viewBox="0 0 210 297"', "mm", 96 / 25.4, "M 20,50 L 120,50 L 120,120"),
    "px": ('width="793.7" height="1122.5" viewBox="0 0 793.7 1122.5"', "px", 1.0,
           "M 75.590551,188.97638 L 453.54331,188.97638 L 453.54331,453.54331"),
    "half": ('width="200mm" height="100mm" viewBox="0 0 100 50"', "mm", 2 * 96 / 25.4, "M 10,10 L 60,10 L 60,45"),
}


def document(kind, two_points=False):
    attrs, unit, _, d = DOCS[kind]
    if two_points:
        d = d.rsplit(" L ", 1)[0]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
        f' xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" {attrs}>'
        f'<sodipodi:namedview id="nv" inkscape:document-units="{unit}"/>'
        '<g inkscape:groupmode="layer" id="layer1" inkscape:label="Layer 1">'
        f'<path id="ln" d="{d}" style="stroke:#000;fill:none"/></g></svg>'
    )


def px_per_unit(kind):
    return DOCS[kind][2]


def inx_args(inx, **overrides):
    """The arguments Inkscape's dialog passes by default."""
    args = {}
    for p in ET.parse(os.path.join(LATEST, inx)).iter(NS + "param"):
        kind = p.get("type")
        if kind == "notebook":
            pages = p.findall(NS + "page")
            value = pages[0].get("name") if pages else ""
        elif kind in ("optiongroup", "enum"):
            options = p.findall(NS + "option") + p.findall(NS + "item")
            value = (p.text or "").strip() or (options[0].get("value") if options else "")
        else:
            value = (p.text or "").strip()
        args[p.get("name")] = value
    args.update(overrides)
    return [f"--{k}={v}" for k, v in args.items()]


def tabs(inx):
    """(tab, {subnotebook: page} or {}) for every page of the dialog."""
    out = []
    root = ET.parse(os.path.join(LATEST, inx)).getroot()
    tab = next(p for p in root.iter(NS + "param") if p.get("name") == "tab")
    for page in tab.findall(NS + "page"):
        subs = [p for p in page.iter(NS + "param") if p.get("type") == "notebook"]
        if subs:
            out += [(page.get("name"), {subs[0].get("name"): sp.get("name")}) for sp in subs[0].findall(NS + "page")]
        else:
            out.append((page.get("name"), {}))
    return out


@pytest.fixture(scope="session")
def ext_path(tmp_path_factory):
    madeeasy = os.environ.get("INKSCAPE_MADEEASY") or os.path.join(ROOT, "..", "inkscapeMadeEasy", "latest")
    if not os.path.isdir(madeeasy):
        pytest.skip("inkscapeMadeEasy not found: set INKSCAPE_MADEEASY")
    folder = tmp_path_factory.mktemp("ext")
    os.symlink(os.path.abspath(madeeasy), folder / "inkscapeMadeEasy")
    return str(folder)


@pytest.fixture
def run(ext_path, tmp_path):
    def run(script, svg_text, args):
        src = tmp_path / "in.svg"
        src.write_text(svg_text)
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([ext_path, LATEST, os.environ.get("PYTHONPATH", "")]))
        r = subprocess.run(
            [sys.executable, "-W", "error::SyntaxWarning", os.path.join(LATEST, script), *args, str(src)],
            capture_output=True, cwd=LATEST, env=env,
        )
        out = inkex.load_svg(io.BytesIO(r.stdout or svg_text.encode())).getroot() if r.returncode == 0 else None
        return r.returncode, r.stderr.decode(), out

    return run


def added(svg):
    """What the extension drew: everything but the test line, the layer
    and the document's own elements."""
    skip = {inkex.addNS("defs", "svg"), inkex.addNS("namedview", "sodipodi"), inkex.addNS("metadata", "svg")}
    top = [n for n in svg if n.tag not in skip and n.get("id") != "layer1"]
    layer = svg.getElementById("layer1")
    return top + [n for n in (layer if layer is not None else []) if n.get("id") != "ln"]


def arc_points(x0, y0, rx, ry, phi, large, sweep, x1, y1, n=64):
    """Points along an SVG arc, by the spec's centre parametrisation
    (inkex's own arc handling is off when radii are scaled)."""
    import math

    if rx == 0 or ry == 0:
        return [(x1, y1)]
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    xp, yp = c * dx + s * dy, -s * dx + c * dy
    rx, ry = abs(rx), abs(ry)
    lam = xp**2 / rx**2 + yp**2 / ry**2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = max(0.0, rx**2 * ry**2 - rx**2 * yp**2 - ry**2 * xp**2)
    k = math.sqrt(num / (rx**2 * yp**2 + ry**2 * xp**2)) * (-1 if large == sweep else 1)
    cxp, cyp = k * rx * yp / ry, -k * ry * xp / rx
    cx, cy = c * cxp - s * cyp + (x0 + x1) / 2, s * cxp + c * cyp + (y0 + y1) / 2
    t0 = math.atan2((yp - cyp) / ry, (xp - cxp) / rx)
    t1 = math.atan2((-yp - cyp) / ry, (-xp - cxp) / rx)
    dt = t1 - t0
    if sweep and dt < 0:
        dt += 2 * math.pi
    elif not sweep and dt > 0:
        dt -= 2 * math.pi
    out = []
    for i in range(1, n + 1):
        t = t0 + dt * i / n
        out.append((cx + c * rx * math.cos(t) - s * ry * math.sin(t), cy + s * rx * math.cos(t) + c * ry * math.sin(t)))
    return out


def shape_box(leaf):
    """Bounding box in document units, with arcs measured exactly."""
    transform = leaf.getparent().composed_transform()
    if not isinstance(leaf, inkex.PathElement) or not any(isinstance(c, inkex.paths.Arc) for c in leaf.path.to_absolute()):
        return leaf.bounding_box(transform)
    pts, cur = [], (0.0, 0.0)
    for cmd in leaf.path.to_absolute().to_non_shorthand():
        if isinstance(cmd, inkex.paths.Arc):
            pts += arc_points(cur[0], cur[1], cmd.rx, cmd.ry, cmd.x_axis_rotation, cmd.large_arc, cmd.sweep, cmd.x, cmd.y)
        elif cmd.args:
            pts += [tuple(cmd.args[i : i + 2]) for i in range(0, len(cmd.args) - 1, 2)]
        if cmd.args:
            cur = tuple(cmd.args[-2:])
        pts.append(cur)
    t = leaf.composed_transform()
    pts = [t.apply_to_point(p) for p in pts]
    return inkex.BoundingBox((min(p.x for p in pts), max(p.x for p in pts)), (min(p.y for p in pts), max(p.y for p in pts)))


def new_drawing_px(svg):
    """Width and height in px (1/96 in) of the shapes the extension drew,
    and the font sizes of its text in px. inkex only guesses text boxes
    (and misreads a font-size in px when user units are not px), so text
    is measured by its font size."""
    boxes, fonts = [], []
    for node in added(svg):
        for leaf in node.iter():
            if not isinstance(leaf, inkex.ShapeElement) or isinstance(leaf, inkex.Group):
                continue
            if isinstance(leaf, (inkex.TextElement, inkex.Tspan)):
                size = leaf.style.get("font-size")
                if size and isinstance(leaf, inkex.TextElement):
                    t = leaf.composed_transform()
                    fonts.append(round(float(size.replace("px", "")) * (abs(t.a * t.d - t.b * t.c) ** 0.5) * svg.scale, 3))
                continue
            box = shape_box(leaf)
            if box is not None:
                boxes.append(box)
    assert boxes or fonts, "nothing drawn"
    if not boxes:
        return 0.0, 0.0, sorted(fonts)
    total = boxes[0]
    for b in boxes[1:]:
        total = total + b
    return round(total.width * svg.scale, 2), round(total.height * svg.scale, 2), sorted(fonts)
