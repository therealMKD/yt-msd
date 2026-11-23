# GUI Test Suite

This file is an AI generated summary of the test suite.

Everything in this folder exists to prove the GUI still behaves. The scripts themselves are tracked;
what they produce is not - `copy/` and `captions.png` are gitignored - and nothing here is shipped
with the app. The master copy remains `GUI Source Code/yt-msd-gui.pyw`: nothing in this folder is a
second source of truth, and the regression scripts copy that file rather than treating anything here
as the program.

## Running it

From `GUI Source Code`:

```powershell
python "GUI Test Suite\probe_playback.py"      # 424 playback / search / search-row / seam checks. No visible window, no network, no library writes.
python "GUI Test Suite\probe_sync.py"          # 120 sync-chain checks. Loopback sockets only, fixture folders only, no LAN broadcast and no removable device.
python "GUI Test Suite\probe_windows.py"       # 119 window checks: the settings window, the three chain builders, the sync manager, the tray bubble, the three update windows, the rename window, the two promises made to the machine - which file Windows starts, which yt-dlp is looked for - and what MainApp is assembled from since wave 6.
python "GUI Test Suite\probe_shell.py"         # 75 single-instance and crash-reporting checks. The crash log these checks write lands in their own fixture folder, never in the log a user reads.
python "GUI Test Suite\probe_export.py"        # 70 export-package checks. Fixture folders only; every archive built is read back and deleted.
python "GUI Test Suite\probe_local_pane.py"    # 16 local-folder-pane checks: how a folder is filled in chunks, whose number decides each chunk's size, and which module builds the app that fills it.
python "GUI Test Suite\check_glyphs.py"        # 14 icon-caption checks. Paints into bitmaps, never shows a window, writes captions.png.
python "GUI Test Suite\probe_tuning_seam.py"   # 14 checks that the settings seam carries across module boundaries.
python "GUI Test Suite\measure_changeover.py"  # optional dev tool: where the time at a real track change goes. Touches the network.
```

Every regression script prints one line per check and a final `N / N checks passed`, and exits 1 when
anything fails, so they are safe to chain. Those eight are the gate - 852 checks - and they are what a
wave is measured against before it is accepted. `probe_playback.py` is the one to run after any edit to
the `.pyw` or to `yt_msd/`; `probe_sync.py` is the one to run after anything in the sync chains - the
TAG.yaml marker, the socket protocol, either end of a chain, or the removable-media worker;
`probe_windows.py` after any window, the setting it writes, or the startup entry and yt-dlp lookup the
program asks of Windows; `probe_shell.py` after the crash reporting or the single-instance name;
`probe_export.py` after the shape of an exported package; `probe_local_pane.py` after how a folder is
filled onto the screen; `check_glyphs.py` is the one to run after anything that paints a caption, a
tooltip or a button rule.

The split that produced `yt_msd/` is closed. The wave plan in `.test_harness/refactor/waves.py` ran
from 1 to 5g and moved 72 of the entry point's 73 top-level blocks; the 73rd is `MainApp`, and it
stays in `yt-msd-gui.pyw` on purpose - it is the last large piece the compiled build holds
(`build_gui_cython.py` compiles the entry point into a single `.pyd` while `yt_msd` travels as plain
Python), a class split across modules runs exactly as the one class does, and the time in this
program goes to VLC, ffmpeg and the network rather than to attribute lookup. So there is no wave
left to run: `python .test_harness/refactor/splitlib.py analyze` reports `LEFT IN THE .pyw BY
DECISION : 1` with the reason, `BLOCKS THE PLAN STILL OWES : 0` and `... of them over 150 lines : 0`,
and `check_wave` refuses any wave that lists `MainApp` until `LEFT_BY_DECISION["MainApp"]` is deleted
from `waves.py` - which is the edit that reopens the question, if the class ever outgrows being read
as one piece.

Wave 5h was the last one and it moved nothing: it removed 117 names the entry point imported back
from the package that nothing reads - not the file that imports them, not `mod.<name>` in the suite,
not a string the suite contains - together with the thirteen wave banners that still promised a
final wave, taking `yt-msd-gui.pyw` from 6,995 lines to 6,882. `.test_harness/refactor/prune_reexports.py`
does it and `.test_harness/refactor/splitlib.py analyze` reports `... of which nothing reads
anywhere : 0`, so a wave that moves code out and leaves its import behind shows up as a number
rather than quietly adding to the file. Names the suite reaches are kept on purpose: a good third of
what remains in the import layer exists so a check can find it.

Wave 6 is listed in `LIFTS` in that same file rather than in `WAVES`, because it moved methods and not
blocks: `MainApp` stayed, and the five methods that had outgrown a screenful went into modules it now
inherits - `yt_msd.ui.bootstrap` (`__init__`), `yt_msd.ui.layout` (`setup_ui`), `yt_msd.ui.stylesheet`
(`apply_theme`), `yt_msd.ui.settings_reset` (`reset_to_defaults`) and `yt_msd.ytdlp.batch`
(`start_batch_download`, whose nested `_run_batch` and `download_single` went with it). 1,618 lines,
cut and pasted at the same indentation, which is why `verify.py` still reports not one changed line in
any of them. `.test_harness/refactor/lift_methods.py` writes those modules and refuses a method whose
out-edges still point at the entry point. `yt-msd-gui.pyw` went from 6,882 lines to 5,252, and the
longest thing left in it is 132 lines.

Three checks moved with it, and the one that complained loudest was the one that was right. `WN-G9`
refuses a module under `yt_msd` that reads its own `__file__` for a location, and the constructor had
done exactly that to decide where `gui_config.json` lives - after the move it would have been
`yt_msd/ui/`, so it reads `program_folder()` now. `Z41` and `LP9`/`LP9b` were text windows pinned to a
place in the `.pyw`, so they now ask the same questions of the whole program. The wave also left 18
imports nothing read behind, which `analyze` reported and `prune_reexports.py` removed.

Five checks were added rather than re-pointed. `WN-H1`-`WN-H5` ask the question the rest of the suite
is structurally unable to ask: every other check drives `MainApp`'s methods as unbound functions on
hand-made stand-ins, so a shadowed method, a duplicated one or a base in the wrong place would have
left all 847 of them green. They assert that the five mixins are inherited ahead of `QMainWindow`,
that each lifted method resolves to the mixin that owns it, that none of the five is redefined in
`MainApp` on top of the mixin that holds it, that the constructor resolves to `BootstrapMixin` rather
than to the Qt one behind it, and that the signals `MainApp` wires its threads to are still declared
on the class itself.

## What is in here

| name | what it is |
| --- | --- |
| `probe_playback.py` | The regression harness, sections A-AE: prefetch and what it hands the player, stream resolution and expiry, the three "Stop after current" states, the results-list scroll reset, the one-shot stop a new search arms, the stream-liveness watchdog and its resume grace, what a track that ran to its end is held as (a replay), `AA`: a stream URL fetch that a newer pick has superseded being stopped rather than run out - the registry, the kill, the `StreamFetchSupersededError` a killed run raises and what the play and reload paths do with it, plus the wiring that makes a search, a pick and a session restore agree on which fetch is still wanted, `AB`: the channel name a search row wears and the search that is asked again when every entry came back naming no owner, `AC`: the play button a result thumbnail wears while the pointer is on it - built, hidden, torn down, replaced and scrolled out from under a pointer that never moved, and `AE`: the playback clocks - the read-ahead trigger and the stall threshold - moved through the seam with the player's own decision watched at each step, because a constant the harness reads while the player reads a stale copy is the failure mode a wave that moves constants has. It copies the `.pyw` to `copy/yt_msd_under_test.py` because importlib cannot import a `.pyw`, then drives `MainApp` methods against harness objects holding only the attributes the method under test touches. `AA` stands its own fake in for `subprocess` so a resolution can be inspected and killed without a process ever being spawned, and `AC` stands its own fake in for `QCursor` so a row can be pointed at and un-pointed without anybody's mouse moving - both through `harness_seam`, which puts them wherever the program is currently reading them from; its rows are built by the real `build_result_ui` in a window shown at `-32000`, off every screen, because a row is only under a pointer if it is on screen at all. Its `SEAM` section is the harness checking its own instrument: that a replacement lands on the code the program actually calls. |
| `harness_seam.py` | Not a check - the instrument the checks patch through. `seam.patch(name, value)` reads the corpus with ast, finds every module that holds `name` at module level (the entry point's re-export included), and writes to all of them; `seam.restore(name)` gives each module back the value it held for itself. It exists because writing into the entry point stops meaning anything once a name has moved: the patch lands on a copy no caller reads, the check stays green, and it tests nothing. `seam.partial_module(real, **overrides)` is the other half - a stand-in that replaces only the names named and leaves every other attribute genuine, which matters when the name being patched is `subprocess` and the audio helpers import it too. |
| `probe_sync.py` | The sync-chain harness, sections `SY-A`-`SY-L`, written before wave 4 so the move had something to preserve: `SY-A` the TAG.yaml marker a chain leaves on a drive and what reads back out of it (style, owner, alternate names, the `XXXX` placeholder that is not a chain), `SY-B` the two forms `last_synced` takes - epoch in the chain dict, wall-clock string in the marker - and the clock grace between them, `SY-C` the drive scan that finds tagged folders one level down, `SY-D` the id a runtime removable chain gets, `SY-E` chain persistence in the same `gui_config.json` `MainApp` writes (pauses, Wi-Fi binding and the stray-key fold, the legacy file migration), `SY-F` the primitives a link is built out of (length-prefixed messages, the hash both ends agree on, the temporary file that never survives a bad hash, per-drive locks, throttled progress), `SY-G` what `SyncHostServer` answers a client, `SY-H` what `SyncClientWorker` downloads, deletes and leaves alone, `SY-I` the removable worker's copy decisions, `SY-J` the failsafe that refuses to roll a newer drive back to an older copy and the question it asks before it does, `SY-K` the hosted folder watcher's debounce, and `SY-L` the seam again. Sockets are loopback only and LAN discovery is patched out, so no check can put a packet on the network; everything it writes goes into `copy/sync_fixture/` and is deleted again at the end. |
| `probe_windows.py` | The windows harness, sections `WN-A`-`WN-G`: the settings window and where each of its controls writes, the three windows that build a chain, the sync manager that lists and pauses and removes them, the playlist picker, the tray progress bubble, the three update windows, the rename-from-metadata window and the names it writes onto files, and `WN-G` - the two promises the program makes to Windows: the startup entry it registers names the file the program was started as rather than the module that asked for it, a `yt-dlp.exe` placed beside the program is looked for beside the program rather than inside `yt_msd/`, and no module under the package reads its own `__file__` for a location. `winreg` is replaced with a recorder for the length of those checks, so the real HKCU startup entry is neither read nor changed. Fixture folders only, under `copy/windows_fixture/`. |
| `probe_shell.py` | The shell harness, sections `SH-A`-`SH-E`: the local name that keeps a second copy from starting and what the first copy does when asked, which folders a crash log may live in, what an entry says, how the log is kept from growing without bound, the throttle that logs a repeating fault instead of dialoguing it, the guards that keep a dialog from being raised where no window can raise it, the three roads an unhandled error takes - the interpreter hook, the thread hook and the unraisable hook - and everything handed back afterwards. Its `QLocalServer` / `QLocalSocket` pair is the program's own mechanism driven for real on a named local pipe, and the crash log these checks write goes to `copy/shell_fixture/`, never to the log a user reads. |
| `probe_export.py` | The export harness, sections `EX-A`-`EX-H`: the vocabulary a package is known by, the three cases `build_exported_config` answers, `export.yaml` written by hand and read back by the program, the name a folder takes inside the archive, the walk that copies a music folder into it, a package built by these functions and read back by them, the window that asks for a package, and the seam again. Everything it writes lands under `copy/export_fixture/` and is deleted at the end. |
| `probe_local_pane.py` | Written for wave 5g, which moved the five `LOCAL_RENDER_*` constants into `yt_msd.ui.render` - nothing in this suite touched the local folder pane before it. `LP1`-`LP12` drive `_local_screenful_rows` and `_fill_local_chunk` against a pane stand-in that holds a viewport height and a minimum height it was told, and check each constant by moving it through the seam and watching the next chunk change size: the screenful floor, the budget a chunk is measured against, the ceiling over it, the floor under it, and the height the pane is handed while only its first chunk exists. No folder is scanned, nothing is written, no window is shown. |
| `probe_tuning_seam.py` | The 14 checks on the one seam the split has introduced that had no coverage of any kind before it: `yt_msd.audio.tuning.TUNING`, the object that replaced the four module globals the settings dialog used to write. It proves a write made from the entry point is visible to the module that reads it, that `from_settings()` decides the way the three call sites used to, and that a settings value survives into a subprocess. |
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
- **A replacement lands where the program reads it.** Nothing in this suite writes into the entry
  point's namespace: `mod.<name> = fake` injects behaviour only while that name resolves in the
  module the suite imported, and the split means a name may now resolve somewhere else. Replacements
  go through `harness_seam.patch()`, which writes to every module holding the name. A name nothing
  owns is refused outright, because a patch that silently does nothing is worse than a check that
  fails. `SEAM1`-`SEAM10` hold this, and `.test_harness/refactor/splitlib.py` reads the suite's
  syntax to refuse any wave that would put a name back in that shape.
- **Nothing here may write.** No config file, no library file, no network, no visible window - with
  the one exception of `measure_changeover.py`, which says so in its own docstring. `probe_sync.py`
  keeps to the same rule in the two places a chain cannot be proven without it: its sockets are
  loopback only (`127.0.0.1`, including a fake host listening on an ephemeral loopback port, and LAN
  discovery patched out so nothing is ever broadcast), and its files are fixture folders under
  `copy/sync_fixture/` that are rebuilt at the start of a run and deleted at the end - never a
  removable device, never the app's own config folder, never the library, never the startup registry.
- **Glyph checks must not set `QT_QPA_PLATFORM=offscreen`.** The offscreen plugin's font database
  holds no private-use codepoint at all, so under it every icon caption in the app reports as
  missing. `check_glyphs.py` uses the normal platform and paints with `grab()`, which does not need
  a widget to be shown.
- **`probe_playback.py` stays on the normal platform for the same reason** - `Z1` asks this
  machine's font the same question - so section `AC` owns its pointer instead of moving the real
  one: it swaps `QCursor` through the seam for a stand-in that says where the harness puts the
  pointer, shows its
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

