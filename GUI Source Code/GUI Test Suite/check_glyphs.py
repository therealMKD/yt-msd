r"""Every icon caption this app paints, checked against the font that has to draw it.

Segoe MDL2 Assets is a private-use font, and the published chart lists codepoints this machine's
copy of it does not contain: U+E76A, the chart's own "Replay", paints a hollow .notdef box rather
than an arrow. That is why the replay button carries U+E72C and the stop-after button carries the
plain text square U+25A0 (AI Readme gotcha 35). A caption is only proven by asking Qt whether the
codepoint has a glyph, and by looking at what it paints - never by trusting a chart.

What this checks: that every private-use codepoint the source paints is one this font can draw;
that the play button's three captions are named, distinct, drawable and not the chart's Replay;
that the stop-after caption is an ordinary text glyph; and that the real buttons, built from the
QSS rules copied out of the source, paint something other than the fallback box - a filled square
rather than a hollow one, and three states that look different from one another.

    python "GUI Source Code\GUI Test Suite\check_glyphs.py"

Writes `captions.png` beside this file - the app's own captions at the sizes the app uses, next to
the box they must not be - and prints a pass/fail count. Nothing is ever shown on screen: a widget
is painted with grab(), which does not need it to be shown. QT_QPA_PLATFORM is deliberately left
alone, because the offscreen plugin's font database does not carry any private-use codepoint and
would report every one of these captions as missing.
"""
import ast
import os
import re
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QApplication, QPushButton

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")
SHEET = os.path.join(HERE, "captions.png")

MDL2 = "Segoe MDL2 Assets"
CHART_REPLAY = 0xE76A                      # the codepoint the published chart calls "Replay"
PUA = lambda cp: 0xE000 <= cp <= 0xF8FF    # the private-use range an icon font lives in

# The source is no longer one file: the .pyw is the entry point and the code it used to hold
# now sits in the yt_msd package beside it. A caption rule can live in either place, so the
# glyph check reads the entry point plus every module extracted from it.
def _read_sources():
    texts = [open(SRC, encoding="utf-8").read()]
    pkg = os.path.join(os.path.dirname(SRC), "yt_msd")
    for root, _dirs, files in os.walk(pkg):
        for name in sorted(files):
            if name.endswith(".py"):
                texts.append(open(os.path.join(root, name), encoding="utf-8").read())
    return "\n".join(texts)


_source = _read_sources()
CHECKS = 0
FAILS = []


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"{'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"   [{detail}]"))
    if not cond:
        FAILS.append(label)


app = QApplication(sys.argv)
_metrics = QFontMetrics(QFont(MDL2, 14))

# 1. every private-use codepoint the source paints, however it is written there
_codes = sorted({cp for cp in ({int(m, 16) for m in re.findall(r"\\u([0-9a-fA-F]{4})", _source)}
                               | {ord(c) for c in _source if PUA(ord(c))}) if PUA(cp)})
_missing = ", ".join(f"U+{cp:04X}" for cp in _codes if not _metrics.inFontUcs4(cp))
check("G1 every private-use codepoint the source paints is one this machine's Segoe MDL2 Assets can draw",
      bool(_codes) and not _missing, _missing)
check("G2 the scan found the captions it is meant to check", len(_codes) >= 12, f"{len(_codes)} codepoints")

_consts = {name: chr(int(val, 16)) for name, val in
           re.findall(r'^([A-Z]+_GLYPH) = "\\u([0-9a-fA-F]{4})"', _source, re.M)}
check("G3 the play button's captions are named constants in the source",
      set(_consts) == {"PLAY_GLYPH", "PAUSE_GLYPH", "REPLAY_GLYPH"}, sorted(_consts))
check("G4 this machine still has no glyph for the chart's Replay codepoint, so the trap is still real",
      not _metrics.inFontUcs4(CHART_REPLAY), "U+E76A draws here now - re-read gotcha 35")
check("G5 the replay caption is a drawable glyph and is not the chart's Replay",
      _consts.get("REPLAY_GLYPH") not in (None, chr(CHART_REPLAY))
      and _metrics.inFontUcs4(ord(_consts.get("REPLAY_GLYPH", " "))), repr(_consts.get("REPLAY_GLYPH")))
check("G6 play, pause and replay are three different captions and all three are drawable",
      len(set(_consts.values())) == 3 and all(_metrics.inFontUcs4(ord(c)) for c in _consts.values()),
      sorted(_consts.values()))

_match = re.search(r'self\.stop_after_btn = QPushButton\("([^"]*)"\)', _source)
_stop_caption = ast.literal_eval('"' + _match.group(1) + '"') if _match else ""
check("G7 the stop-after caption is one ordinary text glyph rather than a private-use codepoint",
      len(_stop_caption) == 1 and not PUA(ord(_stop_caption)),
      f"U+{ord(_stop_caption):04X}" if _stop_caption else "no caption found")
check("G8 this machine's icon font can draw the stop-after caption too",
      bool(_stop_caption) and _metrics.inFontUcs4(ord(_stop_caption)))

# 3. the real buttons, built from the QSS rules as the app itself writes them
_VARS = {"fg": "#111111", "secondary_fg": "#111111", "bg": "#f6f6f6", "btn_hover": "#e6e6e6",
         "accent": "#0A84FF", "accent_fg": "#ffffff", "hover_bg": "#e6e6e6", "hover_fg": "#111111"}
PLAY_SELECTORS = ["playerPlayBtn"]
STOP_SELECTORS = ['stopAfterBtn', 'stopAfterBtn[stop_after_state="once"]',
                  'stopAfterBtn[stop_after_state="always"]']


def _qss(selectors, measure):
    """Those blocks copied out of the app source, with the theme names filled in.  `measure`
    repeats them with a white ground and dark ink, which is what makes the shape underneath
    measurable; the font family, size and weight stay exactly as the app asks for them."""
    blocks = []
    for sel in selectors:
        at = _source.index("QPushButton#" + sel + " {{")
        blocks.append(re.sub(r"\{([a-z_]+)\}", lambda m: _VARS.get(m.group(1), "#888888"),
                            _source[at:_source.index("}}", at) + 2]).replace("{{", "{").replace("}}", "}"))
    if measure:
        blocks += ["QPushButton#" + sel + " { background-color: #ffffff; color: #111111; }"
                   for sel in selectors]
    return "\n".join(blocks)


def _shot(caption, selectors, object_name, size, state=None, measure=True):
    button = QPushButton(caption)
    button.setObjectName(object_name)
    if state is not None:
        button.setProperty("stop_after_state", state)
    button.setFixedSize(size, size)
    button.setStyleSheet(_qss(selectors, measure))
    button.style().polish(button)
    return button.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _painted(image):
    """The pixels this button puts ink on, measured against a white ground so that the ink is
    the only thing that is not already white."""
    canvas = QImage(image.width(), image.height(), QImage.Format.Format_ARGB32)
    canvas.fill(QColor(255, 255, 255))
    painter = QPainter(canvas)
    painter.drawImage(0, 0, image)
    painter.end()
    painted = set()
    for y in range(canvas.height()):
        for x in range(canvas.width()):
            px = canvas.pixelColor(x, y)
            if (255 - px.red()) + (255 - px.green()) + (255 - px.blue()) > 120:
                painted.add((x, y))
    return painted


def _centre_inked(painted):
    """True when the middle of what was painted is painted - a solid shape, not a hollow outline."""
    if not painted:
        return False
    xs = [point[0] for point in painted]
    ys = [point[1] for point in painted]
    return ((min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2) in painted


def _ground(image):
    """The colour the button's own background paints, read along the top edge away from the caption."""
    return image.pixelColor(image.width() // 2, 2)


_captions = {"PLAY": _consts.get("PLAY_GLYPH", ""), "PAUSE": _consts.get("PAUSE_GLYPH", ""),
             "REPLAY": _consts.get("REPLAY_GLYPH", "")}
_play_shots = {name: _shot(caption, PLAY_SELECTORS, "playerPlayBtn", 44)
               for name, caption in _captions.items()}
_play_tofu_shot = _shot(chr(CHART_REPLAY), PLAY_SELECTORS, "playerPlayBtn", 44)
_play_painted = {name: _painted(image) for name, image in _play_shots.items()}
_play_tofu = _painted(_play_tofu_shot)
check("G9 each of the three play-button captions paints something at 30px on a 44px button",
      all(_play_painted[name] for name in _play_painted), {n: len(v) for n, v in _play_painted.items()})
check("G10 and none of them paints the hollow box a codepoint this font lacks paints instead",
      all(_play_painted[name] != _play_tofu for name in _play_painted),
      [name for name in _play_painted if _play_painted[name] == _play_tofu])
check("G11 and they are three different pictures rather than one picture painted three times",
      len({frozenset(v) for v in _play_painted.values()}) == 3, {n: len(v) for n, v in _play_painted.items()})

_stop_shots = {state: _shot(_stop_caption, STOP_SELECTORS, "stopAfterBtn", 36, state)
               for state in ("off", "once", "always")}
_stop_raw = {state: _shot(_stop_caption, STOP_SELECTORS, "stopAfterBtn", 36, state, measure=False)
             for state in ("off", "once", "always")}
_stop_painted = {state: _painted(image) for state, image in _stop_shots.items()}
_stop_tofu_shot = _shot(chr(CHART_REPLAY), STOP_SELECTORS, "stopAfterBtn", 36, "off")
_stop_tofu = _painted(_stop_tofu_shot)
check("G12 the stop-after caption paints a filled square where the fallback box is hollow in the middle",
      all(_centre_inked(_stop_painted[s]) for s in _stop_painted) and not _centre_inked(_stop_tofu),
      {s: _centre_inked(_stop_painted[s]) for s in _stop_painted})
check("G13 the once and always states paint their own backgrounds, copied from the app's own rules",
      _ground(_stop_raw["once"]) != _ground(_stop_raw["off"])
      and _ground(_stop_raw["always"]) == QColor("#E31E24"),
      {s: _ground(_stop_raw[s]).name() for s in _stop_raw})


# 4. the sheet worth looking at, made of exactly what was just measured
CELL_W, CELL_H, COLS = 112, 148, 4
_tiles = [("PLAY U+E768", _play_shots["PLAY"]),
          ("PAUSE U+E769", _play_shots["PAUSE"]),
          ("REPLAY U+E72C", _play_shots["REPLAY"]),
          ("U+E76A box", _play_tofu_shot),
          ("stop off", _stop_raw["off"]),
          ("stop once", _stop_raw["once"]),
          ("stop always", _stop_raw["always"]),
          ("stop U+E76A", _stop_tofu_shot)]
_tile_rows = (len(_tiles) + COLS - 1) // COLS
_code_rows = (len(_codes) + COLS - 1) // COLS
sheet = QImage(COLS * CELL_W, (_tile_rows + _code_rows) * CELL_H, QImage.Format.Format_ARGB32)
sheet.fill(QColor(245, 245, 245))
sheet_painter = QPainter(sheet)
for index, (label, image) in enumerate(_tiles):
    x, y = (index % COLS) * CELL_W, (index // COLS) * CELL_H
    sheet_painter.drawImage(x + (CELL_W - image.width()) // 2, y + 6, image)
    sheet_painter.setPen(QColor(60, 60, 60))
    sheet_painter.setFont(QFont("Consolas", 8))
    sheet_painter.drawText(x + 2, y + image.height() + 24, CELL_W - 4, 30, Qt.AlignCenter, label)
for index, code in enumerate(_codes):
    x, y = (index % COLS) * CELL_W, (_tile_rows + index // COLS) * CELL_H
    sheet_painter.setPen(QColor(0, 0, 0))
    sheet_painter.setFont(QFont(MDL2, 26))
    sheet_painter.drawText(x, y, CELL_W, CELL_H - 34, Qt.AlignCenter, chr(code))
    sheet_painter.setPen(QColor(60, 60, 60))
    sheet_painter.setFont(QFont("Consolas", 8))
    sheet_painter.drawText(x + 2, y + CELL_H - 30, CELL_W - 4, 26, Qt.AlignCenter,
                           f"U+{code:04X} " + ("ok" if _metrics.inFontUcs4(code) else "MISSING"))
sheet_painter.end()
_saved = sheet.save(SHEET)
check("G14 the comparison sheet was written beside this file",
      _saved and os.path.exists(SHEET) and os.path.getsize(SHEET) > 4096, SHEET)

print(f"{CHECKS - len(FAILS)} / {CHECKS} glyph checks passed - sheet: {SHEET}")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)

