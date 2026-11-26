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
python "GUI Test Suite\probe_playback.py"      # 565 playback / search / search-row / seam checks. No visible window, no network, no library writes.
python "GUI Test Suite\probe_sync.py"          # 257 sync-chain checks. Loopback sockets only, fixture folders only, no LAN broadcast and no removable device; the Restore Host exchange runs as a real client socket against a real host server over two fixture folders.
python "GUI Test Suite\probe_phone_wire.py"    # 39 sync-protocol checks for a client that is not this program: the Qt-free wire layer driven against a real host over a real loopback socket - discovery, the whole offline-playback session, the refusals at the door, a keepalive, a Restore Host rebuild, a coded push and a code-free one, and the recorded session compared with `fixtures/protocol/phone_session.json`.
python "GUI Test Suite\probe_windows.py"       # 362 window checks: the settings window, the three chain builders, the sync manager and the visibility badge on a hosted card, the tray bubble, the three update windows, the rename window, the two promises made to the machine - which file Windows starts, which yt-dlp is looked for - what MainApp is assembled from since wave 6, the question a sync asks before it deletes, the window that searches the network for a host and how big it makes itself, and the main window's own start when there is a saved search and no saved session to go with it, and the three windows the Restore Host answer puts on screen and the main-window handlers that drive them, and the filters the Import button opens with - which is what puts a gui_config.json in the list without touching a dropdown.
python "GUI Test Suite\probe_shell.py"         # 75 single-instance and crash-reporting checks. The crash log these checks write lands in their own fixture folder, never in the log a user reads.
python "GUI Test Suite\probe_export.py"        # 70 export-package checks. Fixture folders only; every archive built is read back and deleted.
python "GUI Test Suite\probe_trace.py"         # 42 command-trace checks. Fake yt-dlp, ffmpeg, ffprobe and winget stand in for the real ones: no network, no audio touched, nothing installed.
python "GUI Test Suite\probe_local_pane.py"    # 16 local-folder-pane checks: how a folder is filled in chunks, whose number decides each chunk's size, and which module builds the app that fills it.
python "GUI Test Suite\check_glyphs.py"        # 14 icon-caption checks. Paints into bitmaps, never shows a window, writes captions.png.
python "GUI Test Suite\probe_tuning_seam.py"   # 14 checks that the settings seam carries across module boundaries.
python "GUI Test Suite\measure_changeover.py"  # optional dev tool: where the time at a real track change goes. Touches the network.
```

Every regression script prints one line per check and a final `N / N checks passed`, and exits 1 when
anything fails, so they are safe to chain. Those ten are the gate - 1454 checks, measured on 26 Nov 2026 -
and they are what a
wave is measured against before it is accepted. `probe_playback.py` is the one to run after any edit to
the `.pyw` or to `yt_msd/`; `probe_sync.py` is the one to run after anything in the sync chains - the
TAG.yaml marker, the socket protocol, either end of a chain, the Restore Host offer registry and the
exchange built on it, the removable-media worker, or the message a host puts on the network a moment
after it comes up and the beacon that reads it; `probe_phone_wire.py` after the wire protocol itself -
`yt_msd/sync/protocol.py`, `yt_msd/sync/wire.py`, the host's answers, or the protocol version;
`probe_windows.py` after any window, the setting it writes, the question a sync asks before it deletes and
the windows the Restore Host answer needs, the box that says this copy has just become a new version, or
the startup entry and yt-dlp lookup the
program asks of Windows; `probe_shell.py` after the crash reporting or the single-instance name;
`probe_export.py` after the shape of an exported package; `probe_trace.py` after anything that starts
another program - the yt-dlp funnels, the ffmpeg and ffprobe calls, winget, the copy that runs the
renamer - or after the flag that decides whether any of it is printed; `probe_local_pane.py` after how
a folder is filled onto the screen; `check_glyphs.py` is the one to run after anything that paints a
caption, a tooltip or a button rule.

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
| `probe_playback.py` | The regression harness, sections A-AI, `AJ`, `AK` and `AL`: prefetch and what it hands the player, stream resolution and expiry, the three "Stop after current" states, the results-list scroll reset, the one-shot stop a new search arms, the stream-liveness watchdog and its resume grace, what a track that ran to its end is held as (a replay), `AA`: a stream URL fetch that a newer pick has superseded being stopped rather than run out - the registry, the kill, the `StreamFetchSupersededError` a killed run raises and what the play and reload paths do with it, plus the wiring that makes a search, a pick and a session restore agree on which fetch is still wanted, `AB`: the channel name a search row wears and the search that is asked again when every entry came back naming no owner, `AC`: the play button a result thumbnail wears while the pointer is on it - built, hidden, torn down, replaced and scrolled out from under a pointer that never moved, and `AE`: the playback clocks - the read-ahead trigger and the stall threshold - moved through the seam with the player's own decision watched at each step, because a constant the harness reads while the player reads a stale copy is the failure mode a wave that moves constants has, and `AF`: a track picked while the player is still starting - held by the 200 ms retry rather than dropped, nothing fetched and nothing handed to VLC while libVLC is being set up, announced once and then thinned to one line per five seconds of waiting, the same notice from a search row and from a local file, the retry count cleared when the pick finally gets through so a later wait announces itself too, and the two trace lines - how long libVLC took to become ready and how long the pick was held - printed when `--trace` asked for them and not one character printed when it did not; and `AI`: a search row whose title key is there and empty - the shape of row yt-dlp answers for a withdrawn upload a playlist still lists, and the row a results window died on mid-draw - named by `entry_display_title` out of whatever it does name (title, fulltitle, channel, id) and then drawn by the real `build_result_ui` and the real queue-item builder, which are the crash site rather than a stand-in for it. It copies the `.pyw` to `copy/yt_msd_under_test.py` because importlib cannot import a `.pyw`, then drives `MainApp` methods against harness objects holding only the attributes the method under test touches. `AA` stands its own fake in for `subprocess` so a resolution can be inspected and killed without a process ever being spawned, and `AC` stands its own fake in for `QCursor` so a row can be pointed at and un-pointed without anybody's mouse moving - both through `harness_seam`, which puts them wherever the program is currently reading them from; its rows are built by the real `build_result_ui` in a window shown at `-32000`, off every screen, because a row is only under a pointer if it is on screen at all. Its `SEAM` section is the harness checking its own instrument: that a replacement lands on the code the program actually calls. |
| `harness_seam.py` | Not a check - the instrument the checks patch through. `seam.patch(name, value)` reads the corpus with ast, finds every module that holds `name` at module level (the entry point's re-export included), and writes to all of them; `seam.restore(name)` gives each module back the value it held for itself. It exists because writing into the entry point stops meaning anything once a name has moved: the patch lands on a copy no caller reads, the check stays green, and it tests nothing. `seam.partial_module(real, **overrides)` is the other half - a stand-in that replaces only the names named and leaves every other attribute genuine, which matters when the name being patched is `subprocess` and the audio helpers import it too. |
| `probe_sync.py` | The sync-chain harness, sections `SY-A`-`SY-R`, written before wave 4 so the move had something to preserve: `SY-A` the TAG.yaml marker a chain leaves on a drive and what reads back out of it (style, owner, alternate names, the `XXXX` placeholder that is not a chain), `SY-B` the two forms `last_synced` takes - epoch in the chain dict, wall-clock string in the marker - and the clock grace between them, `SY-C` the drive scan that finds tagged folders one level down, `SY-D` the id a runtime removable chain gets, `SY-E` chain persistence in the same `gui_config.json` `MainApp` writes (pauses, Wi-Fi binding and the stray-key fold, the legacy file migration), `SY-F` the primitives a link is built out of (length-prefixed messages, the hash both ends agree on, the temporary file that never survives a bad hash, per-drive locks, throttled progress), `SY-G` what `SyncHostServer` answers a client, `SY-H` what `SyncClientWorker` downloads, deletes and leaves alone, `SY-I` the removable worker's copy decisions, `SY-J` the failsafe that refuses to roll a newer drive back to an older copy and the question it asks before it does, `SY-K` the hosted folder watcher's debounce, `SY-M` the number of files a client chain may delete before it has to ask and the `PING` that keeps its host patient while it decides, `SY-N` which chains a host is willing to name to somebody who has not authenticated - the beacon, the UDP probe answer, the `HELLO` answer, and what `HostScanner` makes of each answer including the one an older build gives, `SY-O` what a host calls its own chain and where the client keeps that name - a host hosting two chains naming both, the name in the answer that lets a client in, the name saved in the client's chain record, the name learned by a sync that reaches its host and by the search that finds a host whose address moved - and `SY-L` the seam again; `SY-P` Restore Host - the answer a sync can be given besides Keep and Delete: the code alphabet with the look-alikes taken out and the shape a typed code is read in (`SY-P1`-`SY-P2`), the host's offer registry - one open offer per chain, a newer request replacing the older, a wrong code closing rather than leaving an offer open to be guessed at, an unused offer expiring on its own, and a card refresh cancelling only the code its own window holds (`SY-P3`-`SY-P7`), the path rule no restored file may climb out of (`SY-P8`), the exchange at the host end - the answer that says the host is waiting without putting the code on the wire, the code held only in the host's own callback, the `PING` that keeps a host patient while a code is read off another screen, a code closed on the host's screen reported to the machine that was waiting for it, the shortlist a host builds from what its own folder still needs, a folder mid-rebuild refusing an index, a file and a second rebuild each with a reason that says why, and refusals that neither write anything nor close the connection (`SY-P9`-`SY-P20`), the client half asking, waiting, listing and sending only the files the host comes back and asks for (`SY-P21`-`SY-P22`), a mistype or a code nobody read ending the restore on the client's own side and leaving both folders as they were (`SY-P23`-`SY-P24`), the answer a window hands back being read as one of the three names this program has for an answer, and the wording both questions carry through unchanged (`SY-P25`-`SY-P26`), a refused restore told apart from a host that could not be reached at all (`SY-P27`), and `SY-P28`-`SY-P32` running Keep, Delete and Restore Host through a whole worker run over two fixture folders, each with the host asked the same question in the same words, `SY-Q` Push To Host - the client half that offers its own new files to the host before the sync that follows would delete them out of its own folder, the code the host shows and the refusal that still leaves the folders matching - and `SY-R` the message a host puts on the network a moment after it comes up: its own message type, the port a client would fetch from and the address it came from, the codes it is allowed to name and the private ones it is not, and the beacon that reads one - including a beacon built before that message existed, which reads it, ignores it, and goes on delivering the chain updates it has always delivered. Sockets are loopback only and LAN discovery is patched out, so no check can put a packet on the network; everything it writes goes into `copy/sync_fixture/` and is deleted again at the end. |
| `probe_windows.py` | The windows harness, sections `WN-A`-`WN-M`: the settings window and where each of its controls writes, the three windows that build a chain, the sync manager that lists and pauses and removes them, the playlist picker, the tray progress bubble, the three update windows, the rename-from-metadata window and the names it writes onto files, and `WN-G` - the two promises the program makes to Windows: the startup entry it registers names the file the program was started as rather than the module that asked for it, a `yt-dlp.exe` placed beside the program is looked for beside the program rather than inside `yt_msd/`, and no module under the package reads its own `__file__` for a location; `WN-I` the question a sync asks the user before it deletes more than its chain allows, and since Restore Host the three windows that answer puts on screen and the main-window handlers that drive them - the gate that parks a worker until a window has answered, and which window a question is asked of (`WN-I9b`-`WN-I15`), the window that asks a person for a code and the one that shows it on the host's own screen with its countdown and its refusal to cancel itself twice (`WN-I16`-`WN-I27`), and the handlers that keep an offer alive while the sync manager is open, settle the four host events into one outcome, and keep a folder change arriving mid-rebuild off the notice (`WN-I28`-`WN-I35b`); `WN-J` the window that searches the network for a host - what a found host fills in, the port it remembers, the thread it will not let outlive the window - and the once-only notice a Host is given about chains that were already visible before the visible/private choice existed; `WN-L` the size *Connect To Remote Chain* gives itself - measured off the widgets rather than off a screenshot, because the window used to be `setFixedSize(520, 640)` and its own rows did not fit in it once a search had put a host list inside - and the name a host gives its own chain arriving on the client: two chains on one host being two rows, the row picked filling the name the local folder is made from, a name typed at the box outranking it, and the host's name kept beside it in the record and on the card; and `WN-K` the main window's own start, run by lifting the restore half of `setup_ui` out of `yt_msd/ui/layout.py` and running it over a stub holding only the attributes it asks for - a saved search with the session option off, which is how every new install starts and which used to end in an `UnboundLocalError` before the window was drawn, with the saved-session and saved-playlist starts checked alongside it, and the rename pass asked not to clean a name its prompt never settled on, `WN-M` the box a copy puts on screen the first time it starts as a version it has not reported before - which version counts as news and which is silence, the record that keeps it a once-only box written into the same `gui_config.json` before the window is ever answered and read back by the next start, including a settings file written by a build that kept no such record, and the release page the box links to, named the way every release in this repository is named - along with what a host says to the clients of its chains when it comes up: which chains it names, that a private chain is named in nothing, that a machine with no host server running says nothing either, what Force Sync All adds to the network beside the message it has always sent, and what a client that follows one of the chains named starts - the ordinary auto-sync pass, the same call its own timer makes. `winreg` is replaced with a recorder for the length of those checks, so the real HKCU startup entry is neither read nor changed. Fixture folders only, under `copy/windows_fixture/`. |
| `probe_shell.py` | The shell harness, sections `SH-A`-`SH-E`: the local name that keeps a second copy from starting and what the first copy does when asked, which folders a crash log may live in, what an entry says, how the log is kept from growing without bound, the throttle that logs a repeating fault instead of dialoguing it, the guards that keep a dialog from being raised where no window can raise it, the three roads an unhandled error takes - the interpreter hook, the thread hook and the unraisable hook - and everything handed back afterwards. Its `QLocalServer` / `QLocalSocket` pair is the program's own mechanism driven for real on a named local pipe, and the crash log these checks write goes to `copy/shell_fixture/`, never to the log a user reads. |
| `probe_export.py` | The export harness, sections `EX-A`-`EX-H`: the vocabulary a package is known by, the three cases `build_exported_config` answers, `export.yaml` written by hand and read back by the program, the name a folder takes inside the archive, the walk that copies a music folder into it, a package built by these functions and read back by them, the window that asks for a package, and the seam again. Everything it writes lands under `copy/export_fixture/` and is deleted at the end. |
| `probe_trace.py` | The trace harness, checks `TR1`-`TR42`: that `--trace`, `-v` and `--trace=all` are read and then dropped before Qt or the renamer's own argparse can mistake one for something else; that off means not one character printed and nothing buffered for later; that turning the gate on changes nothing about the call being watched - same returned path, same progress-callback count, same exception raised; and that what is printed is the whole command, including which program was resolved to run it. `TR11`-`TR13` are why the trace never prints a resolved stream URL: the formats offered, the host they come from and the size are printed, the signed query never is, and the player still gets the URL whole. `TR16` and `TR17` hold the feature's one performance promise - sixty progress lines from yt-dlp come out as one line of chatter while every line that names something (a destination, a conversion, an error) passes through. `TR21`-`TR25` are the renamer's half of it: the ffmpeg command as actually built, the silence-trim filter intact through the wrapping, the codec chosen for the suffix, and the per-file ffprobe question kept out of level 1 because a library folder of a few thousand songs is a few thousand lines answering nobody's question. `TR28b`-`TR28d` are winget installing yt-dlp - the command, the last thing winget said, and a machine with no winget saying so. `TR29`-`TR31` cover where the lines can go - dropped rather than raised when there is no console, kept when the console cannot take the box-drawing characters, and eight background threads producing eight whole commands rather than one interleaved mess. Fake yt-dlp, ffmpeg, ffprobe and winget are written into `copy/trace_fixtures/` and stood in through the same seams the program uses to find the real ones, so no request leaves the machine, no real audio is touched and nothing is installed. |
| `probe_local_pane.py` | Written for wave 5g, which moved the five `LOCAL_RENDER_*` constants into `yt_msd.ui.render` - nothing in this suite touched the local folder pane before it. `LP1`-`LP12` drive `_local_screenful_rows` and `_fill_local_chunk` against a pane stand-in that holds a viewport height and a minimum height it was told, and check each constant by moving it through the seam and watching the next chunk change size: the screenful floor, the budget a chunk is measured against, the ceiling over it, the floor under it, and the height the pane is handed while only its first chunk exists. No folder is scanned, nothing is written, no window is shown. |
| `probe_tuning_seam.py` | The 14 checks on the one seam the split has introduced that had no coverage of any kind before it: `yt_msd.audio.tuning.TUNING`, the object that replaced the four module globals the settings dialog used to write. It proves a write made from the entry point is visible to the module that reads it, that `from_settings()` decides the way the three call sites used to, and that a settings value survives into a subprocess. |
| `probe_phone_wire.py` | The phone harness, checks `PW1`-`PW39`: the Qt-free wire layer (`yt_msd/sync/wire.py`) driven against a real `SyncHostServer` over a real loopback socket, exactly as a client that is not this program drives it - that the wire layer and the protocol module import no Qt and load none, that every command and status `protocol.py` names is a word `host.py` really says, the `HELLO` discovery a phone runs and what a private chain may be told to a machine that has its code, the whole offline-playback session (`AUTH` with the protocol version, `GET_INDEX`, two `PULL_FILE`s verified by the announced hash, a re-pull, `GET_CONFIG`, `PING`), the refusals at the door read as refusals, a keepalive that hands the socket back clean, the whole Restore Host exchange - requested, taken away mid-read, code mistyped, given up, rebuilt with nothing deleted - and a Push with a code and a Push from a trusted address, with the host keeping its own copy of a name it holds. It is the only suite here that does not import the entry point, because a phone speaks to the package. Loopback sockets on port 0 and `copy/phone_wire_fixture/` only. |
| `fixtures/protocol/phone_session.json` | The recorded session `probe_phone_wire.py` compares against: 18 frames - every frame the client sent and every frame the host answered, in order, with the digest of the bytes that followed each `SENDING`. Written by `python probe_phone_wire.py --record`. **The contract a phone client is written against**: changing it is a protocol change, and it is reviewed like one. It is tracked by a negation in `.gitignore`, because the repo ignores `*.json` and this file is not scratch. |
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


## Added with the search-row filter and the dead-row changeover (23 Nov 2026)

`probe_playback.py` went 439 to 515 and the gate to 985. Nothing was folded and no label moved.

- `AB31`-`AB43` which rows a search may show at all: the channel a query is named for, its uploads shelf and a playlist that came back among the tracks are
  refused; a live row with no duration, a short and a radio row are kept; a row of another extractor is judged by nothing here. The shapes are the ones measured
  on a live `ytsearch15:F5ve` answer, whose first row is the band's own channel (`id=UCV1YxS0AVPOrx_HDj9Pgt8Q`, `url=https://www.youtube.com/channel/…`).
- `AB44`-`AB51` the row under a second long, and the one deeper fetch - `--playlist-items 16-30` of `ytsearch30:` - that replaces refused rows. It happens only
  when something was actually refused (`AB49`), not when the list filled itself (`AB50`); it stops at fifteen rows with no repeats (`AB48`); and a half that
  fails keeps the rows already in hand (`AB51`). `AB41` moved from `call[3]` to `call[2:4]` for one reason - the deeper call carries the `--playlist-items` pair
  the original search does not, so the third and fourth arguments are what stay comparable between the two.
- `C10`, `C16`, `E10`-`E12`, `K10`-`K14` and `N17` the read-ahead's scope: a track is read ahead for in its last 30 seconds whatever the stop-after state is and
  however that track got onto the player, and the decision belongs to the track now on the player rather than to the track it was decided for. `C10` and `N17`
  were **rewritten rather than added to**: both used to assert the armed-state gate this wave removed, and a label that asserts the opposite of what the program
  now does is worth keeping as a rewritten check rather than as a gap. The `E7` gap listed above stays a gap - the new look-ahead checks are `E10`-`E12`.
- `AH1`-`AH15` a changeover to a row with no stream behind it: the row after it starts (`AH1`), the dead row is tried once and no more (`AH2`), the listener is
  told which row was skipped (`AH3`), the list is not rearranged to do it (`AH4`), the allowance is the program's own `STREAM_ADVANCE_SKIP_LIMIT` (`AH14`) and any
  track that does start pays it back (`AH5`, `AH15`). `AH6`, `AH9` and `AH11` hold the half that must never move: a failure the listener caused by clicking a row
  is theirs to retry, and nothing plays behind their click.
- Two pieces of the harness itself grew, and both are load-bearing for the above: `Sig.connect()` is now recorded, because a signal the window connects at
  start-up was otherwise invisible to the fixture (`AH13` asks about it directly), and `patch_resolve(..., fail_for=...)` makes exactly one video id
  unresolvable so that a scripted search list can hold one dead row while every other row plays.


## Added with the volume read-out picked out under a click (24 Nov 2026)

`probe_playback.py` went 515 to 521 and the gate to 991. Nothing was folded and no label moved. `AG23` was **relabelled rather than rewritten**: it has always
driven `setFocus()`, which is the road the Tab key takes into the box, and its label said click. What it asserts is unchanged.

- `AG32`-`AG36` the road a hand on the mouse takes into the volume read-out: nothing picked out while another control holds the caret (`AG32`), the focus half of
  the click picking 73 out of 73% and leaving the sign alone (`AG33`), the press that same click delivers leaving it picked out all the same (`AG34`) - the promise
  the box did not keep before, because `QLineEdit` answers that press by putting the caret where the pointer landed and losing the selection with it - one key
  after that replacing the whole number instead of landing inside it (`AG35`), and a click on a box that already holds the caret placing the caret and picking
  nothing out (`AG36`), which is the half that must not change because it is how one digit is edited.
- `AG37` is the source-text pair to `AG34` and `AG36`: one `_pick_out_the_number` for both roads in, and the flag that remembers the click set only for
  `Qt.MouseFocusReason` and cleared again by the single press that came with it.
- The order these checks ask for was measured first, in `.test_harness/scratch_volbox_click.py`, with `QTest.mouseClick` - `QApplication.sendEvent`, which is how
  every press in this suite is delivered, hands a widget the press *without* the focus a pointer causes, so a press-only harness cannot see the undo at all and
  `AG34` would have been written against the wrong order. `QtTest` is not imported here: the two halves are asked for by hand, `setFocus(Qt.MouseFocusReason)`
  then `_ag_press`, in the order that measurement showed them.


## Added with a nameless search row, and a connect window that sizes itself (24 Nov 2026)

`probe_playback.py` went 521 to 537, `probe_sync.py` 174 to 180, `probe_windows.py` 183 to 201 and the gate to 1149. Nothing was folded and no label moved, with
one exception: `AB23` counts the readers of a channel name, and `entry_display_title` is now the sixth of them - it falls back to the channel when a row names no
title - so its exact count went 5 to 6 and the comment above it names the new reader.

Later the same day the hosted card's visibility control became the badge itself, and `probe_windows.py` went 201 to 203. `WN-C26`-`WN-C32` now press the
**Visible / Private** button that is the state: `C26` that the card carries exactly one such widget and no `Make …` button beside it, `C27` that its tooltip and the
card's own sentence both say what a click does, `C28`-`C30` that pressing it writes the decision, rebuilds the card and needs no watcher re-arming, `C31` that it is
Tab-reachable, named for a screen reader and never the window's default button - so the keyboard access the removed button carried is still there - and `C32` that a
chain saved before the choice existed still shows a pressable `Visible`. `WN-J17` reads the notice's wording for the badge it now names.

- `AI1`-`AI8` are `entry_display_title` asked about the shape of search row yt-dlp serves: `title` present and empty (`AI1`), a row naming no owner named by its id
  (`AI2`), a row nothing names given the caller's word rather than None (`AI3`), a title of only spaces (`AI4`), a real title trimmed (`AI5`), `fulltitle` when
  `title` is absent (`AI6`), a row that is not a dict at all (`AI7`), and the exact row the crash log was made by (`AI8`). `AI9`-`AI11` then hand that row to the
  real `build_result_ui` - which is where a results window died, `AttributeError: 'NoneType' object has no attribute 'replace'` - and ask what the checkbox it
  builds is named, including that a fallback name goes through the same `&` doubling a real title does. `AI12` is the same row in the queue list, `AI13`-`AI15`
  are source-text checks that the stream status line, the playback notification, both queue labels and the recent-playlist name read titles through the helper,
  and `AI16` that the helper is the program's own, in `yt_msd/ytdlp/runner.py`.
- `WN-L1`-`WN-L7` are the connect window's size, measured off the widgets: the window is not pinned to a size it cannot grow past (`WN-L1`), it is already roomier
  than its rows ask for before a search has found anything (`WN-L2`), hosts arriving make it taller rather than squeezing the rows that were already there
  (`WN-L3`), the host list holds a height of its own (`WN-L4`), the search button is at least as wide as the sentence it carries and is not pinned (`WN-L5`),
  "Searching..." does not shrink it (`WN-L6`), and what the search did is said on a wrapping line of its own instead of sharing a row with the button (`WN-L7`).
  `WN-L5` and `WN-L6` compare the button's minimum with `QFontMetrics.horizontalAdvance` of its own text - the width it needs in the font it will be drawn in -
  which is what lets the same check say the same thing at 100%, 125% and 150% Windows scaling instead of asserting 185 px.
- `WN-L8`-`WN-L13` are a host hosting two chains - "Other" and "Christian" - arriving as two rows, the row picked filling the name the local folder is made from
  (`WN-L8`-`WN-L10`), a name typed at the box surviving the next pick while the host's own name is still kept beside it (`WN-L11`-`WN-L12`), and an address typed
  in afterwards not being given another machine's chain name (`WN-L13`). `WN-L14`-`WN-L17` carry that name into the chain record and onto the client card,
  including the refresh that rebuilds a card when the name is learned; `WN-L18` is the source-text pair for the two answers a client takes it from.
- `SY-O1`-`SY-O6` are the same name on the wire and in the worker: a host naming both of its chains to a search, the `AUTH` answer naming the chain it is letting
  a client into, the name saved in the chain record - empty rather than absent when no host has ever said one - a sync learning it from its host, a chain whose
  host has moved address being found again and bringing the name back with the address, and a search that finds an address it cannot reach still leaving the name
  it was given on the chain.
- One harness detail these checks needed: `AI9`-`AI12` build a real result row and a real queue row on a `MainApp` made with `__new__`, which is the idiom `AB`
  already uses, with `_fetch_thumbnail` replaced on the instance so a row built by a check does not go looking for a thumbnail on the network.


## Added with the Restore Host answer (24 Nov 2026)

`probe_sync.py` went 180 to 212, `probe_windows.py` 203 to 252, and the gate to 1232. Nothing was folded and no label that had been written down before moved: `WN-I7` and `WN-I8` were extended rather than replaced, and everything from `WN-I8b` on and all of `SY-P` is new.

- `SY-P1`-`SY-P8` are what both ends must agree on before a byte moves: the four-character alphabet with the look-alikes out and the fact that a restore code can never be a number a sync code already is (`SY-P1`), the shape a typed code is read in and every way it is refused before it is compared to anything (`SY-P2`), what an offer holds - chain, the address that asked, the code, the moment it stops being any use (`SY-P3`) - and the four ways an offer stops: a newer request replacing the older and killing the code it replaced (`SY-P4`), a wrong code closing rather than leaving an offer open to be guessed at (`SY-P5`), an unused code expiring and being unusable after that (`SY-P6`), and a card refresh that happened because somebody else was let in cancelling nothing while the code window closing does close its own code (`SY-P7`). `SY-P8` is the path rule every restored name is checked against.
- `SY-P9`-`SY-P20` run the host half over a real `SyncHostServer` on a loopback port with a real socket against it, because the half of this feature that can do damage is the ordering of the exchange - which message the host will read while it waits, and what a mid-rebuild folder will and will not answer. The answer says the host is waiting and puts no code on the wire (`SY-P9`); the code lives in the host's own callback and reaches no other socket (`SY-P10`); a client holding its connection open while somebody reads a code off another screen does it with a `PING`, and the host answers it (`SY-P11`); a code closed on the host's own screen is reported to the machine that was waiting for it (`SY-P12`); a mistype closes the offer and writes nothing (`SY-P13`); the right code lets the client through and starts the host's own half at that moment (`SY-P14`); a host being rebuilt answers with a shortlist built from what its folder still needs and a count of what it already holds (`SY-P15`); a folder mid-rebuild is neither a host nor a half-host and refuses an index, a file and a second rebuild, each with a reason that says why (`SY-P16`); a host takes only what it asked for and only inside its folder, and neither refusal closes the connection or writes anything (`SY-P17`); the files land with the dates the tracks were made on, beside files that were never touched (`SY-P18`); the close says what was received and what never arrived, leaves the folder a host again, and deletes nothing on either machine (`SY-P19`); and a client that sends the wrong thing midway ends the restore instead of leaving a host stuck in one (`SY-P20`).
- `SY-P21`-`SY-P27` are the client half and the words it comes back with: asks for an offer, waits on the code, lists its own folder and sends only the files the host comes back and asks for (`SY-P21`), a report a window can print without guessing - which host it rebuilt, how much it wrote, and that nothing was deleted here (`SY-P22`), a mistype and a code nobody read each ending the restore on the client's own side, closing what it was waiting on, and leaving both folders exactly as they were (`SY-P23`, `SY-P24`), the answer a window gives being read as one of the three answers this program names an answer with and anything else - a half answer, a garbled one, a window that cannot answer - read as the one that deletes nothing (`SY-P25`), both halves of the question built with the chain's name in the title they hand the window and the words they were given carried through unchanged (`SY-P26`), and a restore that was refused, mistyped or given up on told apart from a host that could not be reached at all (`SY-P27`).
- `SY-P28`-`SY-P32` run all three answers through a whole `SyncClientWorker` over two fixture folders: Keep keeping every file the host stopped offering, saying so, and the rest of the sync still running (`SY-P28`), Delete meaning what it has always meant - the same warning, the same files gone, nothing else touched (`SY-P29`), a Restore Host answer the worker cannot carry out, with no window to read a code off, leaving every file where it is and writing nothing anywhere (`SY-P30`), a Restore Host answer given the code read off the host's own screen turning the client's folder into its host's library, deleting nothing on either machine, and stopping there (`SY-P31`), and the host having been asked the same question the Delete and Keep answers were given, in the same words, with the code it was typed coming from the host that was waiting for it (`SY-P32`).
- `WN-I8b`-`WN-I18b` are the main window's two gates. `WN-I9b` that Restore Host's two extra questions are a signal and a slot each on the same window `WN-I9` already describes, and that the host server has a signal to talk back to this screen with; the decision gate - the parked worker getting back the word it acts on, on the words the chain put on the question (`WN-I10`), which window the question is raised against (the main window when no Sync Chains window is open (`WN-I11`), that window when it is, because that is where anybody watching the sync is looking (`WN-I11b`), and no parent at all when it was deleted underneath the worker (`WN-I11c`)), the answer clearing the waiter it was parked on exactly as the Yes/No box did (`WN-I12`), a decision nobody answers being Keep on a bounded wait so a sync cannot be held open by a window nobody read (`WN-I13`), an answer that is not one of the three words this program names an answer with being Keep and never permission to delete (`WN-I14`), and a slot called for a request nothing is parked on building no window at all (`WN-I15`); the code gate - the typed code coming back to the worker that is holding the host's connection open, with the machine it is being typed for written on the window (`WN-I16`), the request the worker parked on gone the moment the code arrives so one code cannot be handed to two syncs (`WN-I17`), and nobody typing anything being no code at all, which is the answer that closes the host's offer from this end (`WN-I18`, `WN-I18b`).
- `WN-I19`-`WN-I23b` build the two windows a person actually sees. The three-answer question carries the warning the Yes/No box used to carry as the first thing said, in the host's own words (`WN-I19`), all three answers on it with the one it opens on being the one that changes nothing (`WN-I19b`), and what each answer does to this PC said before anybody reads them - Delete takes files out of this folder and Restore takes none (`WN-I19c`) - then pressing each answer closing the window on the answer the worker reads back (`WN-I20`, `WN-I20b`) and a window closed by its X, by Escape or by nobody at all being Keep, because the safe answer is the one that needs no button pressed (`WN-I20c`). The code window hands back nothing until there is a whole code, names the machine being written into from the window's own label, upper-cases what is typed because both ends compare a code upper case and leaves a half code unpressable (`WN-I21`, `WN-I21b`), refuses as a code the four characters this code never uses instead of quietly normalising them into one (`WN-I21c`), opens its button only for a whole code and says the host is the one that will check it (`WN-I22`), hands back the code and nothing else, upper-cased (`WN-I22b`), refuses a press that has only half a code and stays where it is (`WN-I23`), and hands back no code on Cancel even when a whole one had been typed, leaving the host exactly as it is (`WN-I23b`).
- `WN-I24`-`WN-I27` are the host's own code window: the machine waiting named, the code shown so a person can read it out, and the countdown already running (`WN-I24`); nothing cancelled and nothing written while it is open (`WN-I24b`); the time running out closing the code here, telling the machine waiting on it, and not leaving the offer open for whoever asks next (`WN-I25`); a code that has closed no longer something the person here can act on, both of its buttons shut (`WN-I25b`); and closing not being counted twice - a second Cancel reporting nothing a second time (`WN-I25c`), a window the rebuild has already settled closing without cancelling the offer the other side owns (`WN-I26`), and that window being unable to report a cancellation over the top of the first one whether by its Cancel button or by its own X (`WN-I27`).
- `WN-I28`-`WN-I35b` drive the main window's own handlers, lifted unbound off `MainApp` rather than re-implemented: a client asking this machine to rebuild itself putting that chain's code on this machine's own screen under the chain it belongs to (`WN-I28`), the code shown being the one this host's own registry is holding and not the one that arrived over the connection, because the window and the offer behind it have to be the same code (`WN-I28b`), and the person sitting here being told to read it out in the chain's own name (`WN-I28c`); an offer that closed between the socket making it and the window raising it showing no code at all and saying so rather than showing a code nothing would accept (`WN-I29`); a newer request for the same chain taking the older window off the screen before the new one goes up, exactly as it took the offer off the host (`WN-I30`); the code named taking the window off the screen and the screen saying what is about to happen to this host - only what it is missing is written, and nothing here is deleted (`WN-I31`); a restore that did not happen being said out loud on this machine too with the reason the host was given (`WN-I32`); and nothing left open in the host's own registry when the section is done (`WN-I32b`). Cancel on this machine's window closes the offer behind it and says what that did to the machine waiting on it (`WN-I33`), and a Cancel arriving after that restore was already accepted or closed says so instead of reporting a cancellation that never happened (`WN-I33b`). A rebuild that finished is said out loud here and the rest of the chain is told about a folder that is now whole (`WN-I34`), this PC's folder list being asked for again when the folder rebuilt is the one being looked at (`WN-I34b`) and the other clients being told either way because the rebuild is theirs to hear about (`WN-I34c`); and a hosted folder mid-rebuild telling the clients nothing, because a Mirror client that synced against a half-built folder would delete its own tracks to match it (`WN-I35`), the same folder telling them once - and only once - when it is whole (`WN-I35b`).
- Three harness pieces grew for this. `harness_seam.py` gained `seam.patched(name, value)`, a context manager around the existing patch/restore pair, because a check that failed between `patch()` and `restore()` used to leave the patched value live for every check that ran after it. `probe_windows.py` gained `_HostRestoreApp`, which takes `MainApp._on_host_restore_event`, `_cancel_host_restore_offer` and `_on_hosted_folder_changed` unbound off the class rather than re-implementing them - the same guarantee `WN-H1`-`WN-H5` exist to hold - and `_HostCodeWindowStandIn`, a `QDialog` whose `show()` records instead of painting, so a host-side window can be checked without one ever reaching the desktop. `WN-I28`-`WN-I32b` go through the real `issue_restore_code` / `cancel_restore_offer` in `yt_msd/sync/host.py` and assert the registry is empty again at the end, so the offer registry is tested as a side effect rather than compared against a hand-written dict. And no `WN-I` window check calls `exec()`: the decision and code boxes are stood in for at class level and the gates are driven from a worker thread, which is the only way a check can tell a parked worker from a worker that was never parked. On the sync side the restore checks run a real `SyncHostServer` with a real socket against it rather than calling handler methods by hand, because the half of this feature that can do damage is the ordering of the exchange - which message a host is willing to read while it waits, and what a mid-rebuild folder will and will not answer.


## Added with the thumbnail cache measured and sized (26 Nov 2026)

`probe_playback.py` went 537 to 558 and the gate to 1332. Nothing was folded and no label written before moved.

A playlist of a few hundred tracks was costing the process about 240 kB a track in fetched thumbnails, against
a box a row paints at 86x46. `.test_harness/probe_ram.py` measures both through the app's own `pil_to_qpixmap`
and `cover_thumbnail` - 240 kB cached at the arriving 320x180 size, 32 kB at the painted size, 48 MB of process
with Qt loaded and nothing cached - and `.test_harness/probe_thumb_cache.py` weighs the cache as the app now
fills it: 1000 tracks, 26.3 MB resident. `AJ1`-`AJ13` hold the behaviour that number came out of.

- `AJ1`-`AJ3` a thumbnail arriving at 320x180 is painted at the box size and *kept* at the box size, with the
  cache totalled in the RGBA bytes the kept picture costs. It used to hold the arriving picture and be capped at
  256 MB of the downloaded JPEG bytes - over 17,000 tracks of pictures the pane cannot show.
- `AJ4` a cached picture is painted as it is, so scrolling a row back in scales nothing a second time.
- `AJ5`, `AJ6` the cap counts bytes kept, trims the pictures nothing is looking at, and is written in the unit it guards.
- `AJ7` a picture arriving for a row that has been torn down is kept by nothing.
- `AJ8`-`AJ10` run through the real `_on_search_results`: a redraw of the list that stays keeps the pictures its
  rows are rebuilt out of - the one job the cache has - and a new search drops the pictures and the queued fetches
  of the list it replaced.
- `AJ11`, `AJ12` a row asks the app's shared fetch pool for its picture; it used to start a thread of its own,
  which is a thread per row for a scroll through a long playlist. `AJ13` closing the window cancels what is queued.

Two of these checks failed on code written the same day, which is what they are for. `AJ4` caught a `NameError`
on the cache-hit path - `THUMB_BOX_H` was read in the entry point and never imported there, and the first three
checks passed only because `and` short-circuited before it. `AJ5` caught the trim unpacking an `OrderedDict` as
pairs when it iterates keys. Both were fixed in the program; the check text never moved.

`ReadingHarness` gained `_drop_thumbnail_cache` bound to `MainApp`'s own, the way it already binds
`invalidate_next_track_prefetch` and `_arm_stop_after_for_new_search`, so `M4` and `AJ9` exercise the real drop
rather than a stand-in for it.

### The thumbnails that came and went (`AK`, same day)

The cache landed in a build and the RAM came down - 283 MB to 150 MB on a playlist the user measures - and the
thumbnails started appearing only some of the time. `AJ` had written down what the fetch path was *meant* to do and
never drove it end to end, so two defects passed every check it had:

- A finished download whose row had scrolled out was **thrown away** - not painted, not kept. The row rebuilt when
  it scrolled back had nothing to paint out of and sat grey until it fetched all over again. The code this replaced
  cached in the fetch thread, so the scroll-back was always instant. `AJ7` had this behaviour written down as the
  requirement, which is what let it through; its expectation is now the opposite, and `AK4` is the symptom itself -
  fetch, tear the row down, rebuild it, fetch again, and check the second visit paints **with one download for the
  two visits**.
- The cache's mutations all moved onto the GUI thread (insert, and the trim's `next(iter(cache))`) while the fetch
  threads kept reading it and calling `move_to_end` on it. That raises - `KeyError` on a trimmed key, `RuntimeError`
  on a dict that changed size mid-walk - and the cache-hit `move_to_end` sits outside the `try`, so the raise landed
  in a `ThreadPoolExecutor` future nobody ever inspects: **that row never painted, and nothing was ever reported.**
  `self._thumbnail_lock` (made in `BootstrapMixin.__init__`, handed out by `MainApp._thumbnail_cache_lock`) is taken
  by every read, write, trim and clear. `AK6` runs four threads doing exactly that at once, with the cap patched
  small so trims are happening under them, and checks the total is still exact.
- `THUMBNAIL_FETCH_WORKERS = 8` replaces the four workers that serialized a burst of downloads: the row the person
  is looking at was waiting behind the rows they had already scrolled past, which reads as pictures arriving late on
  some rows and never on others. `AK8` holds the name and the floor.
- `AK1`-`AK3` drive the fetch path through the signal, not the slot. An app built with `__new__` cannot have a Qt
  signal connected (`Signal source has been deleted` - `__init__` never ran), so `_AK_Emits` plays the connection
  bootstrap.py makes for a real window: it records what was emitted and hands it to `_on_thumbnail_loaded`. The
  download itself is stood in for on `urllib.request.urlopen` - the attribute the entry point calls - with a real
  320x180 JPEG, so no request leaves the machine and a check can count downloads, which is the only way `AK1` and
  `AK4` can say *nothing was fetched*.
- `AK5` failed on its first run and the check was the wrong one, not the code: it raised the generation *before*
  calling `_fetch_thumbnail`, which proves nothing because the number compared is the one read on the way in. It now
  drops the cache from inside the fake download, the way a new search lands mid-flight.
- A row built after the pool is shut down (`AK7`) must not take the window's shutdown down with it: `submit` on a
  shut pool raises, and that raise came out of `build_result_ui`. A row with no picture is the answer; a row build
  that fails is not.
- The re-visit charged the track twice: a cache hit hands the kept picture back to `_remember_thumbnail`, which added
  its cost again and trimmed a picture nothing was looking at. `AJ4` caught that on the first run of the fixed code.

### The whole pane going grey on a scroll, and filling back in two seconds later (`AL`, same day)

With the cache fixed, thumbnails stopped disappearing - but a large playlist still showed pictures only in the rows
on screen, and scrolling down and back turned *every* thumbnail grey for about two seconds before they all came back.
The cause is how the results pane is virtualized: `lazy_load_visible_results` builds rows inside viewport plus 200 px
each way and `clear_result_ui` tears down everything outside it, so a scroll down and back **rebuilds every row from
nothing** - a new `ThumbnailWidget`, a grey placeholder label - and each rebuilt row asked the fetch pool for a
picture the cache was already holding. Eight workers and a trip back through the event loop for a thousand rows is
exactly a two-second grey pane.

- `build_result_ui` now asks `MainApp._cached_thumbnail` first and, when the cache has the picture, puts it on the
  label there and then: GUI thread, no download, no thread, no signal. The pool is asked only for a track the cache
  does not have.
- `_fetch_thumbnail` takes `prefetch`, and a **non-prefetch** fetch whose row has been torn down by the time it gets a
  worker returns before downloading: that work was for a row nobody can see, and it was making the row on screen
  queue behind it.
- `THUMBNAIL_PREFETCH_ROWS` / `THUMBNAIL_PREFETCH_BAND`: the scroll pass now collects the rows just outside the built
  band, sorts them by distance from it, and asks for their pictures after the rows on screen have been queued -
  capped per pass, so a scroll over a thousand tracks cannot queue a thousand downloads. A row that reaches the fold
  with its picture already fetched appears wearing it.
- `AL`'s pane is a real `QScrollArea` shown at `-32000`, because the pass under test decides what to build by reading
  the placeholders' geometry. `AL2` is the symptom verbatim: build (grey) → fetch (painted) → tear down → rebuild →
  painted, **with no event pump between the rebuild and the assertion**, which is what makes it say *on the spot*.
  `AL6`/`AL7` check the pass: the rows on screen are queued ahead of the prefetch, the prefetch starts at the row
  nearest the band, nothing is asked for twice, and a track already in the cache is not asked for at all.
- `AL7` failed on its first run because the check assumed rows are pitched 54 px apart; the layout adds its default
  spacing, so the pitch is 60. The code had the nearest row right - the check now says "the first row that was not
  built" and does not care what the pitch is.

## Import showing a settings file without a dropdown (`WN-N52`, `WN-N53`, 26 Nov 2026)

`open_import_dialog` has offered a settings file beside a package since the bare-config-import change, and `WN-N38`
has checked it since: `"yt-msd Package (*.zip);;yt-msd Settings (*.json);;All Files (*)"`. What that does not buy is
visibility - `QFileDialog.getOpenFileName` **opens on its first filter**, so the Import dialog listed `.zip` files and
a `gui_config.json` was invisible until somebody changed the filter in the dropdown. Nothing the suite asserted, so
nothing the suite caught.

- The filter string is now `"yt-msd Package And Settings (*.zip *.json);;yt-msd Package (*.zip);;yt-msd Settings
  (gui_config.json);;yt-msd Settings (*.json);;All Files (*)"`. The first entry names both things the button can
  read, so a settings file is in the list on opening; packages only, the settings file by its exact name, any json,
  and everything follow behind it. Routing is untouched - `.json` goes to the settings import, everything else to the
  package reader - and `WN-N38`/`WN-N39` keep their meaning, including `WN-N38`'s ordering assertion, which still
  holds because the combined label does not contain the string `yt-msd Package (*.zip)`.
- `WN-N52` reads the **first** filter entry and requires both `*.zip` and `*.json` in it, with the narrower views
  behind it and `All Files (*)` last. `WN-N53` keeps the exact-name view honest: the name it names is the file the
  app keeps its own settings in, so the view is naming something a settings import can be asked for.
- `probe_windows.py` went 360 to 362. The per-file counts written in this README and in `AI Readme.md` had drifted
  behind the harness (307 and 252 against 362 measured, and gate totals of 1339 and 1232 against 1412 measured);
  they now carry the measured 26 Nov numbers.

## A protocol a phone can speak (`SY-G15`-`SY-G17`, `PW1`-`PW39`, 26 Nov 2026)

The plan is at `feature-android-client-2026-11-26.md`, the specification at `docs/sync-protocol.md`, and the
reasoning at `docs/voice-2026-11-26-android-client.md`. What the suite has to keep true:

- **A version, named at last.** The protocol has run for six builds without one. `protocol.py` says
  `PROTOCOL_VERSION = 1`; the host names it in its `HELLO` answer and its `AUTH` answer, and refuses a version
  it does not speak at the door. `SY-G15` is a client that names 1, `SY-G16` is the one that matters - a client
  that names **nothing**, which is every 3.0-to-3.5 client there is, answered exactly as it has always been
  answered - and `SY-G17` is a client naming 99, refused, told which versions the two machines have, and not
  answered at. `SY-G3` grew the new key in the `AUTH` answer, the one existing assertion that was an exact-dict
  comparison.
- **The words in one place, and checked against the words the host says.** `PW3`-`PW5` scan `host.py` and
  `discovery.py` for every command, status and discovery type `protocol.py` names. A constant nobody compares
  against the code is a constant that drifts; these are the comparison.
- **A client with no Qt in it.** `PW1` reads the imports of `wire.py` and `protocol.py` out of their syntax
  trees and `PW2` asserts no Qt module is loaded in the process - a phone cannot import PySide6, so this is a
  buildability rule, not a tidiness one. It is why `probe_phone_wire.py` is the only suite here that imports the
  package directly instead of the copied entry point: a phone speaks to `yt_msd`, not to the GUI, and the seam
  exists for replacements inside the entry point, of which this suite makes none.
- **The whole phone session, on a real socket.** `PW15`-`PW21` is M1 of the plan in one block: pair, list, pull
  twice, re-pull, take the settings, ping. `PW17` is the rule that makes a pull trustworthy - the bytes are
  checked against the hash the host announced *in its answer*, the file lands as `.tmp_sync`, and only a hash
  match ever takes the final name. `PW19` is a host refusing to hand over `notes.txt`. `PW22`-`PW25` are the
  refusals at the door, which a phone has to read as refusals: a host answers once and closes.
- **The exchanges a phone is worst at.** `PW26` is a keepalive that pings while a person reads a code and hands
  the socket back clean, so the next command is the next command and not somebody's `PONG`. `PW27`-`PW31` are a
  whole Restore Host exchange - requested, taken away mid-read (`RESTORE_CLOSED` on the next `PING`), a code
  mistyped, given up, and a rebuild that writes 5 files, keeps the host's 3, and deletes nothing. `PW32`-`PW36`
  are a Push: a coded one whose limit of 3 takes the newest three, refuses the fourth for being over the limit
  and refuses the phone's copy of `old song.mp3` because that name is the host's; and a trusted address pushing
  with no code at all.
- **The recording is the contract.** `PW37` compares the session's 18 frames with
  `fixtures/protocol/phone_session.json`, byte for byte, on every run. Fixture files have fixed bytes and fixed
  mtimes, which is what makes the recording reproducible on any machine. It is re-recorded with
  `python probe_phone_wire.py --record` - read what it wrote before committing it, because the fixture is the
  protocol.
- **Two harness lessons for anyone adding socket checks here.** A host that refuses at its door closes the
  connection, and a socket closed with data it has not read discards what it had already queued to send: send
  the follow-up request first and you may read a reset instead of the refusal. `SY-G17` and `PW24` read in
  order, one request and one answer at a time. And a probe must never call `SyncHostServer.start()`: it binds
  63350-63370, and a yt-msd genuinely running is sitting on the first free one of them. `LoopbackHost` binds
  port 0 and sets `active_port` itself, which is also what makes a `HELLO` answer's `port` mean anything.
- `probe_sync.py` went 254 to 257, `probe_phone_wire.py` is 39, and the gate is **1454 checks** - 565 + 257 +
  39 + 362 + 75 + 70 + 42 + 16 + 14 + 14, counted off the run, not off the sum of two numbers in prose
  (`probe_trace.py` prints `42/42 checks passed` with no spaces, so anything that counts the gate by
  matching that line has to match it as it is written).


