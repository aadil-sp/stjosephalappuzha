"""
Shared vector icon set for the touchscreen (Qt) and web dashboards.

Icons are drawn on a 24x24 grid as stroked outlines. Each icon is a list of
primitives using only absolute M/L/H/V/C/Z path commands, so the same data can
be emitted as inline SVG for the browser and painted with QPainter on the Pi
(which has no QtSvg module).
"""

import math
import re

# Primitive formats:
#   ("p", d, fill)            path data
#   ("c", cx, cy, r, fill)    circle
#   ("r", x, y, w, h, rx)     rounded rectangle (stroked)


def _gear_teeth():
    parts = []
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        x1, y1 = 12 + 7 * math.cos(a), 12 + 7 * math.sin(a)
        x2, y2 = 12 + 9.6 * math.cos(a), 12 + 9.6 * math.sin(a)
        parts.append(("p", f"M{x1:.2f} {y1:.2f}L{x2:.2f} {y2:.2f}", False))
    return parts


ICONS = {
    "leaf": [
        ("p", "M20 4C10 4 4 9 4 20C15 20 20 14 20 4Z", False),
        ("p", "M4 20L13 11", False),
    ],
    "thermo": [
        ("p", "M10 13.5V5C10 3.9 10.9 3 12 3C13.1 3 14 3.9 14 5V13.5C15.2 14.2 16 15.5 16 17"
              "C16 19.2 14.2 21 12 21C9.8 21 8 19.2 8 17C8 15.5 8.8 14.2 10 13.5Z", False),
        ("p", "M12 15V8", False),
        ("c", 12, 17, 1.6, True),
    ],
    "drop": [
        ("p", "M12 3C9 7 6 10.5 6 14.5C6 18 8.7 21 12 21C15.3 21 18 18 18 14.5C18 10.5 15 7 12 3Z", False),
    ],
    "sprout": [
        ("p", "M12 21V11", False),
        ("p", "M12 13C12 9.5 9.5 7 5 7C5 10.5 7.5 13 12 13Z", False),
        ("p", "M12 11C12 7 14.5 4 19 4C19 8 16.5 11 12 11Z", False),
        ("p", "M6 21H18", False),
    ],
    "tank": [
        ("r", 5, 3, 14, 18, 2.5),
        ("p", "M5 13C7.5 11.5 9.5 14.5 12 13C14.5 11.5 16.5 14.5 19 13", False),
    ],
    "sun": [
        ("c", 12, 12, 4, False),
        ("p", "M12 2V4", False), ("p", "M12 20V22", False),
        ("p", "M2 12H4", False), ("p", "M20 12H22", False),
        ("p", "M4.9 4.9L6.3 6.3", False), ("p", "M17.7 17.7L19.1 19.1", False),
        ("p", "M4.9 19.1L6.3 17.7", False), ("p", "M17.7 6.3L19.1 4.9", False),
    ],
    "rain": [
        ("p", "M7 16C4.8 16 3 14.4 3 12.4C3 10.5 4.6 8.9 6.6 8.8C7.4 6.6 9.5 5 12 5C15 5 17.4 7.2 17.8 10"
              "C19.6 10.2 21 11.6 21 13.2C21 14.8 19.6 16 18 16Z", False),
        ("p", "M8 19L7 21", False), ("p", "M12 19L11 21", False), ("p", "M16 19L15 21", False),
    ],
    "power": [
        ("p", "M12 3V11", False),
        ("p", "M7 6.3C5.2 7.6 4 9.7 4 12C4 16.4 7.6 20 12 20C16.4 20 20 16.4 20 12C20 9.7 18.8 7.6 17 6.3", False),
    ],
    "gear": [("c", 12, 12, 3, False), ("c", 12, 12, 7, False)] + _gear_teeth(),
    "back": [("p", "M15 5L8 12L15 19", False)],
    "next": [("p", "M9 5L16 12L9 19", False)],
    "wifi": [
        ("p", "M2 9C7.5 4 16.5 4 22 9", False),
        ("p", "M5 12.5C9 9 15 9 19 12.5", False),
        ("p", "M8.5 16C10.5 14.3 13.5 14.3 15.5 16", False),
        ("c", 12, 19.5, 1.3, True),
    ],
    "sliders": [
        ("p", "M4 6H20", False), ("p", "M4 12H20", False), ("p", "M4 18H20", False),
        ("c", 9, 6, 2.2, True), ("c", 15, 12, 2.2, True), ("c", 7, 18, 2.2, True),
    ],
    "gauge": [
        ("p", "M4.5 17C3.5 15.5 3 13.8 3 12C3 7 7 3 12 3C17 3 21 7 21 12C21 13.8 20.5 15.5 19.5 17", False),
        ("p", "M12 12L16 8", False),
        ("c", 12, 12, 1.5, True),
    ],
    "chip": [
        ("r", 6, 6, 12, 12, 2),
        ("r", 9.5, 9.5, 5, 5, 1),
        ("p", "M9 2V5", False), ("p", "M15 2V5", False), ("p", "M9 19V22", False), ("p", "M15 19V22", False),
        ("p", "M2 9H5", False), ("p", "M2 15H5", False), ("p", "M19 9H22", False), ("p", "M19 15H22", False),
    ],
    "info": [("c", 12, 12, 9, False), ("p", "M12 11V16", False), ("c", 12, 8, 1.1, True)],
    "refresh": [
        ("p", "M20 12C20 16.4 16.4 20 12 20C7.6 20 4 16.4 4 12C4 7.6 7.6 4 12 4C14.8 4 17.2 5.4 18.6 7.6", False),
        ("p", "M19 3V8H14", False),
    ],
    "plus": [("p", "M12 5V19", False), ("p", "M5 12H19", False)],
    "minus": [("p", "M5 12H19", False)],
    "lock": [
        ("r", 5, 11, 14, 10, 2),
        ("p", "M8 11V8C8 5.8 9.8 4 12 4C14.2 4 16 5.8 16 8V11", False),
    ],
    "check": [("p", "M5 12.5L10 17.5L19 7", False)],
    "plug": [
        ("p", "M9 3V8", False), ("p", "M15 3V8", False),
        ("p", "M7 8H17V12C17 14.8 14.8 17 12 17C9.2 17 7 14.8 7 12Z", False),
        ("p", "M12 17V21", False),
    ],
    "disk": [("r", 4, 4, 16, 16, 2.5), ("p", "M4 14H20", False), ("c", 16, 17, 1, True)],
    "clock": [("c", 12, 12, 9, False), ("p", "M12 7V12L15.5 14", False)],
    "eye": [
        ("p", "M2 12C4.5 7.5 8 5 12 5C16 5 19.5 7.5 22 12C19.5 16.5 16 19 12 19C8 19 4.5 16.5 2 12Z", False),
        ("c", 12, 12, 3, False),
    ],
    "backspace": [
        ("p", "M9 5H20V19H9L3 12Z", False),
        ("p", "M12 9L16 15", False), ("p", "M16 9L12 15", False),
    ],
    "shift": [("p", "M12 4L4 13H8.5V20H15.5V13H20Z", False)],
    "close": [("p", "M6 6L18 18", False), ("p", "M18 6L6 18", False)],
    "auto": [
        ("p", "M4 12C4 7.6 7.6 4 12 4C14.6 4 16.9 5.2 18.4 7.2", False),
        ("p", "M20 12C20 16.4 16.4 20 12 20C9.4 20 7.1 18.8 5.6 16.8", False),
        ("p", "M19 3V7.5H14.5", False), ("p", "M5 21V16.5H9.5", False),
    ],
    "hand": [
        ("p", "M8 13V6C8 5.2 8.7 4.5 9.5 4.5C10.3 4.5 11 5.2 11 6V11", False),
        ("p", "M11 10V4.5C11 3.7 11.7 3 12.5 3C13.3 3 14 3.7 14 4.5V11", False),
        ("p", "M14 10.5V6C14 5.2 14.7 4.5 15.5 4.5C16.3 4.5 17 5.2 17 6V14C17 18 14.5 21 11 21"
              "C8.5 21 7 19.8 5.6 17.6L3.8 14.6C3.3 13.8 3.6 12.8 4.4 12.4C5.1 12 6 12.2 6.5 12.9L8 15", False),
    ],
    "home": [
        ("p", "M3 11L12 3.5L21 11", False),
        ("p", "M5.5 9.5V20H10V14.5H14V20H18.5V9.5", False),
    ],
    "apps": [
        ("r", 4, 4, 6.5, 6.5, 1.8), ("r", 13.5, 4, 6.5, 6.5, 1.8),
        ("r", 4, 13.5, 6.5, 6.5, 1.8), ("r", 13.5, 13.5, 6.5, 6.5, 1.8),
    ],
    "flask": [
        ("p", "M8.5 3H15.5", False),
        ("p", "M10 3V9L4.6 18.2C3.9 19.5 4.8 21 6.3 21H17.7C19.2 21 20.1 19.5 19.4 18.2L14 9V3", False),
        ("p", "M6.5 15H17.5", False),
    ],
    "cloud": [
        ("p", "M7 19C4.2 19 2 16.9 2 14.3C2 11.9 3.9 9.9 6.3 9.7C7.2 7 9.4 5 12.5 5C16 5 18.8 7.6 19.1 11"
              "C20.8 11.4 22 12.9 22 14.7C22 17.1 20.1 19 17.7 19Z", False),
    ],
    "cloudsun": [
        ("c", 8, 8, 3, False),
        ("p", "M8 2V3", False), ("p", "M2 8H3", False),
        ("p", "M3.8 3.8L4.5 4.5", False), ("p", "M12.2 3.8L11.5 4.5", False),
        ("p", "M9 20C6.8 20 5 18.4 5 16.4C5 14.5 6.6 12.9 8.6 12.8C9.4 10.6 11.5 9 14 9C17 9 19.4 11.2 19.8 14"
              "C21.6 14.2 23 15.6 23 17.2C23 18.8 21.6 20 20 20Z", False),
    ],
    "storm": [
        ("p", "M7 15C4.8 15 3 13.4 3 11.4C3 9.5 4.6 7.9 6.6 7.8C7.4 5.6 9.5 4 12 4C15 4 17.4 6.2 17.8 9"
              "C19.6 9.2 21 10.6 21 12.2C21 13.8 19.6 15 18 15", False),
        ("p", "M13 12L10 17H14L11 22", False),
    ],
    "fog": [
        ("p", "M4 8H20", False), ("p", "M3 12H21", False), ("p", "M5 16H19", False), ("p", "M8 20H16", False),
    ],
    "moon": [
        ("p", "M20 14.5C18.9 15 17.7 15.3 16.4 15.3C11.9 15.3 8.4 11.8 8.4 7.3C8.4 6 8.7 4.8 9.3 3.7"
              "C5.6 4.9 3 8.4 3 12.5C3 17.7 7.2 21.8 12.3 21.8C16 21.8 19.1 19.6 20.5 16.4Z", False),
    ],
    "wind": [
        ("p", "M3 9H14C15.7 9 17 7.7 17 6C17 4.3 15.7 3 14 3C12.6 3 11.5 4 11.1 5.2", False),
        ("p", "M3 13H19C20.7 13 22 14.3 22 16C22 17.7 20.7 19 19 19C17.6 19 16.5 18 16.1 16.8", False),
        ("p", "M3 17H11", False),
    ],
    "play": [("p", "M7 4.5V19.5L19 12Z", True)],
    "stop": [("r", 6, 6, 12, 12, 2)],
    "sunrise": [
        ("p", "M3 19H21", False),
        ("p", "M7 19C7 16.2 9.2 14 12 14C14.8 14 17 16.2 17 19", False),
        ("p", "M12 3V10", False), ("p", "M9 6L12 3L15 6", False),
    ],
    "sunset": [
        ("p", "M3 19H21", False),
        ("p", "M7 19C7 16.2 9.2 14 12 14C14.8 14 17 16.2 17 19", False),
        ("p", "M12 3V10", False), ("p", "M9 7L12 10L15 7", False),
    ],
    "ruler": [
        ("r", 2.5, 8, 19, 8, 1.5),
        ("p", "M6.5 8V11", False), ("p", "M10.5 8V12", False), ("p", "M14.5 8V11", False), ("p", "M18.5 8V12", False),
    ],
    "bell": [
        ("p", "M6 16V11C6 7.7 8.7 5 12 5C15.3 5 18 7.7 18 11V16L19.5 18H4.5Z", False),
        ("p", "M10 21H14", False), ("p", "M12 3V5", False),
    ],
    "sparkle": [
        ("p", "M11 3C11.6 8.2 13.8 10.4 19 11C13.8 11.6 11.6 13.8 11 19C10.4 13.8 8.2 11.6 3 11C8.2 10.4 10.4 8.2 11 3Z", False),
        ("p", "M18.5 15.5C18.8 17.4 19.6 18.2 21.5 18.5C19.6 18.8 18.8 19.6 18.5 21.5C18.2 19.6 17.4 18.8 15.5 18.5"
              "C17.4 18.2 18.2 17.4 18.5 15.5Z", True),
    ],
    "calendar": [
        ("r", 3.5, 5, 17, 15.5, 2.5), ("p", "M3.5 10H20.5", False),
        ("p", "M8 3V7", False), ("p", "M16 3V7", False), ("c", 12, 15, 1.3, True),
    ],
}

_TOKEN = re.compile(r"[MLHVCZ]|-?\d*\.\d+|-?\d+")


def _parse(d):
    """Yields (command, [args]) from absolute M/L/H/V/C/Z path data."""
    tokens = _TOKEN.findall(d)
    i, cmd = 0, None
    arity = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Z": 0}
    while i < len(tokens):
        if tokens[i] in arity:
            cmd = tokens[i]
            i += 1
            if cmd == "Z":
                yield cmd, []
                continue
        n = arity[cmd]
        yield cmd, [float(t) for t in tokens[i:i + n]]
        i += n
        if cmd == "M":
            cmd = "L"  # implicit lineto after moveto


# ---------------------------------------------------------------------------
# Web (inline SVG)
# ---------------------------------------------------------------------------
def svg(name, size=24, cls="icon", stroke_width=2):
    """Inline SVG markup using currentColor, so CSS controls the colour."""
    out = []
    for prim in ICONS[name]:
        if prim[0] == "p":
            fill = 'fill="currentColor"' if prim[2] else 'fill="none"'
            out.append(f'<path d="{prim[1]}" {fill}/>')
        elif prim[0] == "c":
            fill = 'fill="currentColor"' if prim[4] else 'fill="none"'
            out.append(f'<circle cx="{prim[1]}" cy="{prim[2]}" r="{prim[3]}" {fill}/>')
        elif prim[0] == "r":
            out.append(f'<rect x="{prim[1]}" y="{prim[2]}" width="{prim[3]}" height="{prim[4]}" rx="{prim[5]}" fill="none"/>')
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" stroke="currentColor" '
            f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            + "".join(out) + "</svg>")


def svg_symbols():
    """All icons as <symbol>s for <use href="#i-name"> references."""
    syms = []
    for name in ICONS:
        inner = svg(name)
        inner = inner[inner.index(">") + 1:-len("</svg>")]
        syms.append(f'<symbol id="i-{name}" viewBox="0 0 24 24">{inner}</symbol>')
    return '<svg width="0" height="0" style="position:absolute">' + "".join(syms) + "</svg>"


# ---------------------------------------------------------------------------
# Qt (QPainter)
# ---------------------------------------------------------------------------
_pixmap_cache = {}


def qt_pixmap(name, color, size=24, stroke_width=2.0):
    """Renders an icon to a transparent QPixmap of size x size pixels."""
    key = (name, color, size, stroke_width)
    if key in _pixmap_cache:
        return _pixmap_cache[key]

    from PyQt5.QtCore import Qt, QRectF
    from PyQt5.QtGui import QPixmap, QPainter, QPainterPath, QPen, QColor, QBrush

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    scale = size / 24.0
    p.scale(scale, scale)
    col = QColor(color)
    pen = QPen(col, stroke_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)

    for prim in ICONS[name]:
        p.setPen(pen)
        if prim[0] == "p":
            path = QPainterPath()
            x = y = 0.0
            for cmd, a in _parse(prim[1]):
                if cmd == "M":
                    x, y = a
                    path.moveTo(x, y)
                elif cmd == "L":
                    x, y = a
                    path.lineTo(x, y)
                elif cmd == "H":
                    x = a[0]
                    path.lineTo(x, y)
                elif cmd == "V":
                    y = a[0]
                    path.lineTo(x, y)
                elif cmd == "C":
                    path.cubicTo(a[0], a[1], a[2], a[3], a[4], a[5])
                    x, y = a[4], a[5]
                elif cmd == "Z":
                    path.closeSubpath()
            p.setBrush(QBrush(col) if prim[2] else Qt.NoBrush)
            p.drawPath(path)
        elif prim[0] == "c":
            p.setBrush(QBrush(col) if prim[4] else Qt.NoBrush)
            p.drawEllipse(QRectF(prim[1] - prim[3], prim[2] - prim[3], prim[3] * 2, prim[3] * 2))
        elif prim[0] == "r":
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(prim[1], prim[2], prim[3], prim[4]), prim[5], prim[5])
    p.end()
    _pixmap_cache[key] = pm
    return pm


def qt_icon(name, color, size=24):
    from PyQt5.QtGui import QIcon
    return QIcon(qt_pixmap(name, color, size))
