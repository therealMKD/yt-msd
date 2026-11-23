"""The local folder pane: how a folder arrives on the screen.

Not the audio and not the player - this is the half of `MainApp` that turns a folder listing into
rows. `MainApp` fills a folder in chunks, hands the event loop back between them, and sizes the
chunks from what a row costs the machine it is running on. The five constants the wave moved out
(yt_msd.ui.render) are the whole of that policy, and every one of them is checked here by moving it
and watching the pane's next chunk change size, which is the only way to know the pane is reading
the program's number rather than a copy the suite read.

Recipe (GUI Test Suite README, "Running it"): the `.pyw` is copied to a throwaway `.py` in `copy/`
and imported, and the methods are driven against a stand-in for the pane that holds nothing but what
those methods touch. Nothing is replaced except the constants themselves, each restored before the
next check. No files are written, no window is shown, no folder is scanned - the listing is handed
in by hand.
"""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))              # .../GUI Source Code/GUI Test Suite
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")    # the master copy, one folder up
SRC_DIR = os.path.dirname(SRC)       # GUI Source Code, which now also holds the yt_msd package
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)      # the copy below imports that package, so it must be reachable

import importlib.util

COPY_DIR = os.path.join(HERE, "copy")
os.makedirs(COPY_DIR, exist_ok=True)
TMP_PY = os.path.join(COPY_DIR, "yt_msd_local_pane_under_test.py")
shutil.copyfile(SRC, TMP_PY)
_spec = importlib.util.spec_from_file_location("yt_msd_local_pane_under_test", TMP_PY)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

import harness_seam as seam

seam.install(mod, SRC_DIR)

CHECKS = 0
FAILS = []


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"ok   {label}")
    else:
        FAILS.append(label)
        print(f"FAIL {label} {detail}")


class PaneStandIn:
    """The folder pane, as far as the chunking cares about it: how tall its viewport is, and the
    minimum height it is told. No Qt widget is built, so nothing is laid out or painted."""

    def __init__(self, height=0):
        self.viewport_height = height
        self.minimum_height = None

    def viewport(self):
        return self

    def height(self):
        return self.viewport_height

    def setMinimumHeight(self, height):
        self.minimum_height = height


class RowStandIn:
    """A row, as far as the fill cares about it: where it ended up on screen."""

    def y(self):
        return 0


class TimerStandIn:
    """The zero-timer that asks for the next chunk. It records being asked; it never runs anything."""

    def __init__(self):
        self.starts = 0

    def start(self, msecs):
        self.starts += 1


def pane_app(pane_height=300, items=4000, chunk_age=None, chunk_rows=0):
    """A MainApp that never ran __init__, holding only what the fill and the screenful question
    touch, mid-render, with `chunk_age` and `chunk_rows` describing the chunk it just finished.

    Those two are what the fill measures a row's cost from - the gap since the last chunk ended,
    divided by the rows that chunk produced - so setting them by hand is what makes the size of the
    next chunk something a check can predict."""
    app = mod.MainApp.__new__(mod.MainApp)
    app.local_list = PaneStandIn(pane_height)
    app.local_content = PaneStandIn()
    app.local_rows = []
    app.local_current_path = "Z:/fixture/folder"
    app._local_render_id = 1
    app._local_render_pending = list(range(items))
    app._local_render_pending_id = 1
    app._local_render_pending_path = app.local_current_path
    app._local_render_total_rows = items
    app._local_render_row_height = mod.LOCAL_RENDER_ROW_HEIGHT_GUESS
    app._local_render_step = app._local_screenful_rows()
    app._local_render_chunk_end = None
    app._local_render_chunk_cost = 0.0
    app._local_render_chunk_rows = 0
    app._local_render_row_cost = 0.0
    app._local_render_extent_height = 0
    app._local_render_timer = TimerStandIn()
    app.finished = []
    app._finish_local_render = lambda: app.finished.append(True)
    app._append_local_rows = lambda rows: app.local_rows.extend((RowStandIn(), row) for row in rows)
    if chunk_age is not None:
        app._local_render_chunk_end = time.perf_counter() - chunk_age
        app._local_render_chunk_rows = chunk_rows
        app._local_render_chunk_cost = 0.0
    return app


print("=" * 72)
print("LP. the size of a chunk, and who decides it")

# The first chunk is what fits in the pane, floored at the constant so a folder smaller than a
# screen is filled in one go.
app = pane_app(pane_height=1200)
check("LP1 the first chunk of a folder is a screenful when the pane can show more than the floor",
      app._local_screenful_rows() == 50, app._local_screenful_rows())
app = pane_app(pane_height=300)
check("LP2 and never smaller than the floor - a pane that holds twelve rows still asks for thirty-two",
      app._local_screenful_rows() == 32, app._local_screenful_rows())
_floor = mod.LOCAL_RENDER_FIRST_CHUNK_ROWS
seam.patch("LOCAL_RENDER_FIRST_CHUNK_ROWS", 64)
_app_short = pane_app(pane_height=300)
check("LP3 move that floor up and the same pane asks for sixty-four, so it is the program's number the pane compares against",
      _app_short._local_screenful_rows() == 64, _app_short._local_screenful_rows())
seam.restore("LOCAL_RENDER_FIRST_CHUNK_ROWS")
check("LP3b and thirty-two again once it is back",
      mod.LOCAL_RENDER_FIRST_CHUNK_ROWS == _floor
      and pane_app(pane_height=300)._local_screenful_rows() == 32)

app = pane_app(pane_height=300, items=30)
app._fill_local_chunk()
check("LP4 a folder of thirty files is filled by the first chunk alone, and the render closes out there",
      len(app.local_rows) == 30 and app._local_render_pending is None and app.finished == [True],
      (len(app.local_rows), app._local_render_pending, app.finished))

# After the first chunk the size is what a row costs this machine, within a budget and between a
# floor and a ceiling. A chunk that took 0.4 s for 4000 rows costs a row 1e-4 s, so at the program's
# 20 ms budget the next chunk is about two hundred rows.
app = pane_app(pane_height=300, chunk_age=0.4, chunk_rows=4000)
app._fill_local_chunk()
check("LP5 the next chunk is as big as this machine's measured row cost allows - about two hundred rows at a 20 ms budget",
      190 <= app._local_render_step <= 210, app._local_render_step)
_ceiling = mod.LOCAL_RENDER_CHUNK_MAX_ROWS
seam.patch("LOCAL_RENDER_CHUNK_MAX_ROWS", 64)
app = pane_app(pane_height=300, chunk_age=0.4, chunk_rows=4000)
app._fill_local_chunk()
check("LP6 move the ceiling and the ceiling is what sizes the chunk - the GUI thread is never held for longer than that",
      app._local_render_step == 64, app._local_render_step)
seam.restore("LOCAL_RENDER_CHUNK_MAX_ROWS")
check("LP6b and the ~200 rows are back when it is put back",
      mod.LOCAL_RENDER_CHUNK_MAX_ROWS == _ceiling, seam.read("LOCAL_RENDER_CHUNK_MAX_ROWS"))
_budget = mod.LOCAL_RENDER_CHUNK_BUDGET_S
seam.patch("LOCAL_RENDER_CHUNK_BUDGET_S", 0.004)
app = pane_app(pane_height=300, chunk_age=0.4, chunk_rows=4000)
app._fill_local_chunk()
check("LP6c move the budget instead, ceiling where it was, and the chunk shrinks with the budget",
      38 <= app._local_render_step <= 42, app._local_render_step)
seam.restore("LOCAL_RENDER_CHUNK_BUDGET_S")

# A machine where a row is expensive - 0.4 s for 40 of them - wants two rows at a 20 ms budget, and
# is floored at thirty-two rather than dribbling the folder out a row at a time.
app = pane_app(pane_height=300, chunk_age=0.4, chunk_rows=40)
app._fill_local_chunk()
check("LP7 an expensive folder is floored rather than dribbled out a row at a time",
      app._local_render_step == 32, app._local_render_step)
_floor_rows = mod.LOCAL_RENDER_CHUNK_MIN_ROWS
seam.patch("LOCAL_RENDER_CHUNK_MIN_ROWS", 4)
app = pane_app(pane_height=300, chunk_age=0.4, chunk_rows=40)
app._fill_local_chunk()
check("LP8 move the floor to four and the same expensive folder gets four rows - the floor is the program's, not a number this suite kept",
      app._local_render_step == 4, app._local_render_step)
seam.restore("LOCAL_RENDER_CHUNK_MIN_ROWS")

# The row height a screenful is measured against is the guess in the same group, and the one place
# it is used is where a MainApp is built.
_source_lines = [line.strip() for line in open(TMP_PY, encoding="utf-8")]
_seeded = [line for line in _source_lines
           if line == "self._local_render_row_height = LOCAL_RENDER_ROW_HEIGHT_GUESS"]
check("LP9 the guess a screenful is measured against is seeded where MainApp is built, exactly once",
      len(_seeded) == 1, _seeded)

# The height the pane is given is known before its rows are painted: 4000 rows at the guessed pitch.
app = pane_app(pane_height=300, items=4000)
app._fill_local_chunk()
check("LP10 the pane is handed the height of the whole folder while only its first chunk exists",
      app.local_content.minimum_height == 4000 * 24, app.local_content.minimum_height)

_render_constants = ("LOCAL_RENDER_FIRST_CHUNK_ROWS", "LOCAL_RENDER_ROW_HEIGHT_GUESS",
                     "LOCAL_RENDER_CHUNK_MIN_ROWS", "LOCAL_RENDER_CHUNK_MAX_ROWS",
                     "LOCAL_RENDER_CHUNK_BUDGET_S")
_still_patched = [name for name in _render_constants if seam.is_patched(name)]
check("LP11 nothing this suite moved is left moved for the next suite to run against",
      _still_patched == [], _still_patched)
_holders = {_name: seam.owners(_name) for _name in _render_constants}
check("LP12 every one of these five is a single object wherever it is held, whichever module ends up holding it",
      all(len({getattr(_m, _name) for _m in _hs}) == 1 for _name, _hs in _holders.items()),
      {_name: seam.owned_by(_name) for _name, _hs in _holders.items()})

print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)
