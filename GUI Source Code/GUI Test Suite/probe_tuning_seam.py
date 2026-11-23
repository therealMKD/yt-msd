r"""The normalization settings seam: one object, written in one place, read in another.

Four of the loudness settings - the end pad, whether silence trimming runs, the worker count
and the custom loudnorm override - are things a user changes. Before the 3.5 modularisation
they were module globals in yt-msd-gui.pyw that eight places rewrote with `global` while the
normalizer read them, which only works while the writer and the reader share one module. Wave
2 moves the normalizer into the yt_msd package and leaves the writers in the entry point, so
the settings had to become one object both sides reach through. Left as globals, every
`global` would have updated the copy in the module it sat in and every reader would have read
a copy imported at import time: a setting that silently stops doing anything, with no error
and no failed check.

Nothing in the suite covered these four settings before this file, which is how the duplication
between the globals and MainApp's own silence_trim / silence_pad_dur / use_custom_norm_cmd /
custom_norm_cmd survived as long as it did.

What this checks: that the entry point no longer claims those names as globals and no longer
mentions them unqualified; that the entry point and the package hold the same single object;
and that a write made through that object from the package side changes what the entry point's
own ffmpeg -af chain builder produces - which is the exact failure the old layout would have
had, tested in both directions.

    python "GUI Source Code\GUI Test Suite\probe_tuning_seam.py"

Nothing is downloaded, no window is shown, no audio file is touched, and no ffmpeg or ffprobe
process is started: the chain is only assembled as a string. The `.pyw` is imported by the
importlib recipe from AI Readme section 20 (copy it beside this file as a `.py`), so the chain
builder checked here is the one the program actually runs.
"""
import importlib.util
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))               # .../GUI Source Code/GUI Test Suite
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")     # the master copy, one folder up
SRC_DIR = os.path.dirname(SRC)                                  # GUI Source Code, which holds yt_msd
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
COPY_DIR = os.path.join(HERE, "copy")
os.makedirs(COPY_DIR, exist_ok=True)
TMP_PY = os.path.join(COPY_DIR, "yt_msd_tuning_under_test.py")
shutil.copyfile(SRC, TMP_PY)
_spec = importlib.util.spec_from_file_location("yt_msd_tuning_under_test", TMP_PY)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

from yt_msd.audio import tuning as tuning_mod
from yt_msd.audio.tuning import TUNING

SETTINGS = ("silence_trim", "silence_pad_dur", "max_workers", "custom_norm_cmd")
OLD_NAMES = ("SILENCE_TRIM", "SILENCE_PAD_DUR", "CUSTOM_NORM_CMD", "MAX_WORKERS")

_source = open(SRC, encoding="utf-8").read()
CHECKS = 0
FAILS = []


def check(label, cond, detail=""):
    global CHECKS
    CHECKS += 1
    print(f"{'ok  ' if cond else 'FAIL'} {label}" + ("" if cond else f"   [{detail}]"))
    if not cond:
        FAILS.append(label)


# 1. the entry point stopped claiming these as its own
_globals_left = re.findall(r"^\s*global\b.*$", _source, flags=re.M)
_claimed = [g.strip() for g in _globals_left if any(n in g for n in OLD_NAMES)]
check("T1 the entry point declares no `global` on any normalization setting", not _claimed,
      "; ".join(_claimed))

_bare = sorted({n for n in OLD_NAMES if re.search(r"\b%s\b" % n, _source)})
check("T2 the entry point never names a setting unqualified again", not _bare, ", ".join(_bare))

check("T3 the settings live in exactly one module",
      hasattr(tuning_mod, "TUNING") and not any(hasattr(tuning_mod, n) for n in OLD_NAMES),
      ", ".join(n for n in OLD_NAMES if hasattr(tuning_mod, n)))

# 2. one object, shared by both sides of the boundary
check("T4 the entry point and the package hold the same settings object",
      getattr(mod, "TUNING", None) is TUNING,
      f"pyw holds {type(getattr(mod, 'TUNING', None)).__name__}")

# 3. the chain the program builds reacts to a write made through the object
_build = mod.build_af_chain
_baseline = _build("loudnorm=I=-16:TP=-1.5")
check("T5 built-in chain is silence trim then loudnorm then end pad",
      _baseline.startswith("silenceremove=") and ",loudnorm=" in _baseline
      and _baseline.endswith(",apad=pad_dur=2.0"), _baseline)

_saved = {a: getattr(TUNING, a) for a in SETTINGS}
try:
    TUNING.silence_trim = False
    _no_trim = _build("loudnorm=I=-16:TP=-1.5")
    check("T6 turning silence trim off removes the trim filters from the chain",
          "silenceremove" not in _no_trim and _no_trim == "loudnorm=I=-16:TP=-1.5,apad=pad_dur=2.0",
          _no_trim)

    TUNING.silence_pad_dur = 0.0
    _no_pad = _build("loudnorm=I=-16:TP=-1.5")
    check("T7 a zero end pad removes the apad part entirely", "apad" not in _no_pad, _no_pad)

    TUNING.silence_pad_dur = 4.5
    _padded = _build("loudnorm=I=-16:TP=-1.5")
    check("T8 a longer pad reaches the chain the entry point builds",
          _padded.endswith(",apad=pad_dur=4.5"), _padded)

    # 4. the one place that decides whether a custom override counts
    TUNING.silence_trim = True
    TUNING.silence_pad_dur = 2.0
    TUNING.from_settings(True, 2.0, False, "  EQ(bass=6)  ")
    check("T9 an opted-out custom override is ignored rather than half-applied",
          TUNING.custom_norm_cmd == "", repr(TUNING.custom_norm_cmd))

    TUNING.from_settings(True, 2.0, True, "  EQ(bass=6)  ")
    check("T10 an opted-in custom override is stored stripped",
          TUNING.custom_norm_cmd == "EQ(bass=6)", repr(TUNING.custom_norm_cmd))

    _chained = _build(TUNING.custom_norm_cmd)
    check("T11 an override replaces only the loudnorm part; trim and pad stay",
          "silenceremove" in _chained and "EQ(bass=6)" in _chained and "apad" in _chained,
          _chained)

    TUNING.from_settings(False, "not-a-number", True, "EQ(bass=6)")
    check("T12 an unusable pad length falls back to the factory value instead of raising",
          TUNING.silence_pad_dur == tuning_mod.DEFAULT_SILENCE_PAD_DUR, TUNING.silence_pad_dur)

    TUNING.reset()
    check("T13 reset returns every setting to its factory value",
          all(getattr(TUNING, a) == _saved[a] for a in SETTINGS),
          str({a: getattr(TUNING, a) for a in SETTINGS}))

    check("T14 a reset reaches the chain the entry point builds, not just the attributes",
          _build("loudnorm=I=-16:TP=-1.5") == _baseline, _build("loudnorm=I=-16:TP=-1.5"))
finally:
    for _attr, _value in _saved.items():
        setattr(TUNING, _attr, _value)

print(f"\n{TUNING.__module__}.{type(TUNING).__name__} seam: "
      f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
print("PROBE TUNING SEAM: " + ("OK" if not FAILS else "FAIL " + " | ".join(FAILS)))
sys.exit(0 if not FAILS else 1)


