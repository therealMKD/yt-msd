# GUI Test Suite

Everything in this folder exists to prove the GUI still behaves. It is gitignored
(`.gitignore` line 23, `GUI Source Code/GUI Test Suite/`) and nothing here is shipped with the app.
The master copy remains `GUI Source Code/yt-msd-gui.pyw` - nothing in this folder is a second source
of truth, and the two regression scripts read that file directly instead of a temp copy elsewhere.

## Running it

From `GUI Source Code`:

```powershell
python "GUI Test Suite\probe_playback.py"      # 400 playback / search / search-row checks. No visible window, no network, no library writes.
python "GUI Test Suite\check_glyphs.py"        # 14 icon-caption checks. Paints into bitmaps, never shows a window, writes captions.png.
python "GUI Test Suite\measure_changeover.py"  # optional dev tool: where the time at a real track change goes. Touches the network.
```

Both regression scripts print one line per check and a final `N / N checks passed`, and exit 1 when
anything fails, so they are safe to chain. `probe_playback.py` is the one to run after any edit to the
`.pyw`; `check_glyphs.py` is the one to run after anything that paints a caption, a tooltip or a
button rule.

## What is in here

| name | what it is |
| --- | --- |
| `probe_playback.py` | The regression harness, sections A-AC: prefetch and what it hands the player, stream resolution and expiry, the three "Stop after current" states, the results-list scroll reset, the one-shot stop a new search arms, the stream-liveness watchdog and its resume grace, what a track that ran to its end is held as (a replay), `AA`: a stream URL fetch that a newer pick has superseded being stopped rather than run out - the registry, the kill, the `StreamFetchSupersededError` a killed run raises and what the play and reload paths do with it, plus the wiring that makes a search, a pick and a session restore agree on which fetch is still wanted, `AB`: the channel name a search row wears and the search that is asked again when every entry came back naming no owner, and `AC`: the play button a result thumbnail wears while the pointer is on it - built, hidden, torn down, replaced and scrolled out from under a pointer that never moved. It copies the `.pyw` to `copy/yt_msd_under_test.py` because importlib cannot import a `.pyw`, then drives `MainApp` methods against harness objects holding only the attributes the method under test touches. `AA` stands its own fake in for `mod.subprocess` so a resolution can be inspected and killed without a process ever being spawned, and `AC` stands its own fake in for `mod.QCursor` so a row can be pointed at and un-pointed without anybody's mouse moving; its rows are built by the real `build_result_ui` in a window shown at `-32000`, off every screen, because a row is only under a pointer if it is on screen at all. |
| `check_glyphs.py` | The icon-caption check that used to be several throwaway scripts in the OS temp folder. It asks Qt whether every private-use codepoint the source paints has a glyph on this machine, and then measures what the real buttons paint - a shape, or the hollow fallback box. |
| `captions.png` | The sheet `check_glyphs.py` writes: the app's own captions at the sizes the app uses, beside the box they must not be, and every caption codepoint with the font's answer. A by-product, not an input - rewrite it by re-running the script. |
| `measure_changeover.py` | Not a regression check. It times `resolve_stream_url()`, the libVLC open and `get_length()` on a real machine, which is the only way to know how much a prefetch can possibly save. The only thing here that touches the network. |
| `copy/` | The throwaway `.py` the harness imports, rebuilt from the `.pyw` on every run. Safe to delete at any time. |
| `__pycache__/` | Python's own residue. Safe to delete at any time. |

## Rules that keep it honest

- **A check label never moves.** A gap in the numbering means a check was removed as redundant, and
  the gap is listed below rather than back-filled, so an older entry in `AI Readme.md` naming `Y24`
  or `J15` still points at the right promise.
- **Behaviour first, source-text second.** Most checks drive the code and read what came out. A
  handful read the source as text where a promise is awkward to reach with fixtures; those say so in
  their label, and each is paired with a behavioural check of the same promise.
- **Nothing here may write.** No config file, no library file, no network, no visible window - with
  the one exception of `measure_changeover.py`, which says so in its own docstring.
- **Glyph checks must not set `QT_QPA_PLATFORM=offscreen`.** The offscreen plugin's font database
  holds no private-use codepoint at all, so under it every icon caption in the app reports as
  missing. `check_glyphs.py` uses the normal platform and paints with `grab()`, which does not need
  a widget to be shown.
- **`probe_playback.py` stays on the normal platform for the same reason** - `Z1` asks this
  machine's font the same question - so section `AC` owns its pointer instead of moving the real
  one: it swaps `mod.QCursor` for a stand-in that says where the harness puts the pointer, shows its
  rows in a window at `-32000` because a widget is only under a pointer if it is on screen at all,
  and sends the Enter and Leave Qt itself sends on a hover. `.test_harness/probe_thumb_hover_fix.py`
  runs the same cases the other way round - offscreen, a real cursor, Qt's own dispatch - which is
  where the two agree, and `.test_harness/probe_thumb_hover.py` is the measurement of what Qt
  reports on its own, which is where a stuck button and a missing button come from.

## Pruning done when this suite was assembled

The harness moved here out of `%TEMP%\ytmsd_playback_probe` on 25 Oct 2026, and 16 checks were folded
or dropped on the way - 338 down to 322, with the same coverage:

| label | what happened |
| --- | --- |
| `E7` | folded into `E6`: "what was resolved" and "what VLC was given" are one promise about one prefetch. |
| `H5` | dropped: the H fixture's stop-after hold leaves the replay glyph, which `Z11` already asserts on a fixture that really is finished. |
| `H7a` | folded into `H7`: dropping the decided successor and re-arming the read-ahead are one reset. |
| `I5`, `I6` | folded into `I4`: a fresh list clears the successor, the cached URL and the trigger key together. |
| `I7` | kept, but made real - it used to assert `True` after calling the reset, which reported nothing whether or not the call worked. |
| `K2` | dropped: `K4` already proves "too early prefetches nothing", and `K2` said the same thing at a wider margin. |
| `N9` | folded into `N8`: a stopped track and the id left behind by a finished one are refused by the same guard. |
| `J12`, `J13` | relabelled `J12a`, `J13a`. The stop-after caption checks already held those labels, so two different checks were answering to the same names. |
| `W12` | rewritten rather than removed. It used to assert that `build_gui_cython.py` exists, which `J14` already asserted; it now asserts that `yt_msd_gui.pyx` carries this exact source, which is the promise worth keeping. |
| `X22a` | dropped: `X8` already proves a stalled stream is held dead while the cooldown refuses a fetch. |
| `X62` | dropped: `X1` already pins `STREAM_URL_MAX_AGE` at `30 * 60`. |
| `Y17` | folded into `Y16`: Erroring and still-Opening are both "not provably playing". |
| `Z13b` | folded into `Z13`: the re-resolve and the media it produced are one outcome. |
| `Z39` | folded into `Z38`: the hold and the look-ahead it consults are written in the same branch. |
| `Z43` | folded into `Z42`: the named constants and the one place that captions that button. |
| `Z46` | folded into `Z45`: the died-early stream is not held *because* the verdict is not the raw `Ended` state. |
| `Z52` | dropped: `Z47` already proves a Play press restarts a reload the watchdog gave up on, and reads more of the state while doing it. |
| `Z56` | folded into `Z40` and `Z41`: the in-flight flag is initialised with the rest of the hold state and cleared on both sides. |

`A2`, `A3`, `X2`, `X3` and `X4` were tightened at the same time, from "some positive number" to the
numbers the code actually uses - 4 cached URLs, 15 minutes, 8 seconds, 3 attempts, 15000 ms - which
is what makes them worth re-running.

`glyph_probe.py`, `glyph_render.py`, `glyph_final.py`, `probe_glyph.py`, `stop_after_glyph_picker.pyw`,
`backslash_check.py`, `escape_test.txt`, `out.txt` and the picker/candidate PNGs were left in the temp
folder and deleted with it. Every question they answered - is this codepoint drawable, does it paint
as a shape rather than a box, does the app's own QSS rule actually apply the family it names - is
answered by `check_glyphs.py` now, against the app's real rules. The one-off survey that compared
candidate replay glyphs and settled on `U+E72C` is not repeated here; its result is recorded in
`AI Readme.md` (gotcha 37).

