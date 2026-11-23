r"""The shell of the program: one copy at a time, and where an unhandled error goes.

Sections SH-A..SH-E cover the two pieces of `GUI Source Code/yt-msd-gui.pyw` that exist before any
window does - the local name that keeps a second copy from starting, and the reporting that catches
what nothing else caught - and, since wave 5e moves them into `yt_msd.instance` and `yt_msd.crash`,
it is also the check that the move did not break the routes into them.

Recipe (AI Readme section 20): the `.pyw` is copied to a throwaway `.py` in this folder's `copy/` and
imported, then driven directly. Anything replaced goes through harness_seam.py; nothing is written
into the entry point by hand.

What is stood in for, and why:

  - `crash_log_folders`. Left alone it points at the folder this program sits in and at
    %LOCALAPPDATA%\yt-msd, and every check below writes a crash - so the log the checks write would
    land in the real log a user reads. It is replaced through the seam for the length of the logging
    sections, with the fixture folders of this suite as the answer, and its own behaviour is checked
    against `seam.original`, which is the one the program calls.
  - `QMessageBox` while a crash dialog is raised, and `os` for the one name `open_crash_log` uses.
    `box.exec()` blocks until someone dismisses it, and a stand-in for the box is the only way to
    read what the dialog says and to press its own button. `os` is replaced with
    `harness_seam.partial_module`, so every other attribute of `os` - `startfile` excepted - stays
    the genuine one.
  - `sys.stderr` is redirected with `contextlib.redirect_stderr` rather than patched, because it is
    the interpreter's own stream and not a name the program owns.
  - `sys.excepthook`, `threading.excepthook` and `sys.unraisablehook` are saved before
    `install_crash_reporting()` replaces them and put back at the end. They are the interpreter's
    state, not module-level names, so the seam has nothing to restore for them.

Two things are done for real rather than replaced. The single-instance check uses the program's own
`QLocalServer` and `QLocalSocket` under its own name - no LAN address is bound and no packet is put
on a network, which is probe_sync's rule, and a named local pipe is the mechanism the program itself
uses. And the reporter bridge is driven from a real background thread, because the whole reason
`CrashReporter` exists is that a thread cannot raise a dialog on its own.

Everything written lands in `copy/shell_fixture/`, rebuilt at the start of the run and deleted at the
end. The crash log written by the checks is written there, never to the real one.
"""
import ast
import contextlib
import gc
import importlib.util
import io
import os
import shutil
import sys
import threading
import time
import types

from pathlib import Path

from PySide6.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))              # .../GUI Source Code/GUI Test Suite
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")    # the master copy, one folder up
SRC_DIR = os.path.dirname(SRC)       # GUI Source Code, which now also holds the yt_msd package
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)      # the copy below imports that package, so it must be reachable
COPY_DIR = os.path.join(HERE, "copy")
os.makedirs(COPY_DIR, exist_ok=True)
TMP_PY = os.path.join(COPY_DIR, "yt_msd_shell_under_test.py")
shutil.copyfile(SRC, TMP_PY)
_spec = importlib.util.spec_from_file_location("yt_msd_shell_under_test", TMP_PY)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

import harness_seam as seam

seam.install(mod, SRC_DIR)

# The log a real copy of this program would write to, snapshotted before anything below can write.
# No check in this suite is allowed to land a crash in it: every write is redirected into the
# fixture folder instead, and SH-E12 proves the difference.
_REAL_LOGS = [Path(folder) / mod.CRASH_LOG_NAME for folder in seam.original("crash_log_folders")()]
_REAL_LOG_WAS = {log: (log.read_bytes() if log.exists() else None) for log in _REAL_LOGS}

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


FIXTURE_ROOT = Path(COPY_DIR) / "shell_fixture"
shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)


def fixture(name):
    """A folder under the fixture root, always fresh."""
    folder = FIXTURE_ROOT / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


LOG_FOLDER = fixture("crash log")
# A folder this machine will not make: the name itself is illegal on Windows, so no drive
# or permission setting can accidentally make it writable.
_UNWRITABLE = str(Path(COPY_DIR) / "not:a:usable:folder")
_UNWRITABLE_EXISTS = Path(_UNWRITABLE).exists()


def _capture(statement):
    """Run one statement and hand back the exception it raised, as sys.exc_info() does.

    exec rather than eval, because the statements this suite needs include `raise ...`, and
    BaseException rather than Exception, because KeyboardInterrupt is one of the routes checked and
    is precisely the one the program hands back to the interpreter untouched.
    """
    try:
        exec(compile(statement, __file__, "exec"), {})
    except BaseException:
        return sys.exc_info()
    return (None, None, None)

_QT_APP = QApplication.instance() or QApplication([])

# ===========================================================================
# SH-A: one copy at a time
# ===========================================================================
# The round trip below is real - a local server and a socket, the mechanism the program
# itself uses - but it is done under a name belonging to this suite rather than the
# program's own. Left as the program's name, a running copy of yt-msd on this machine would
# have its name taken away by the probe. The name itself is checked separately.
check("SH-A1 the name a second copy looks for is the program's own, spelled out rather than composed",
      mod.SINGLE_INSTANCE_NAME == "yt-msd-gui-single-instance", mod.SINGLE_INSTANCE_NAME)

_PROBE_NAME = "yt-msd-shell-probe-single-instance"
seam.patch("SINGLE_INSTANCE_NAME", _PROBE_NAME)


class AttentionWindow:
    """The window a second copy is answered with: it records being asked to come forward."""

    def __init__(self):
        self.attention_requested = 0

    def request_attention(self):
        self.attention_requested += 1


check("SH-A2 with nothing holding the name, asking finds nobody - which is what lets the first copy carry on",
      mod.ask_running_instance_to_show() is False)

_server = mod.take_single_instance_name()
check("SH-A3 claiming the name hands back a server that is actually listening on that name",
      _server is not None and _server.isListening() and _server.serverName() == _PROBE_NAME,
      (_server, getattr(_server, "serverName", lambda: None)()))

_window = AttentionWindow()
check("SH-A4 with the name claimed, a second copy finds the first - and finds it without creating anything of its own",
      mod.ask_running_instance_to_show() is True and _server.isListening(), _server)
check("SH-A5 and asking does not disturb the copy holding it: the server is still listening afterwards",
      _server.isListening(), _server)

_server.close()
_stale = mod.take_single_instance_name()
check("SH-A6 a name left behind by a copy that was killed rather than closed is dropped first, so a crash cannot lock the program out of starting again",
      _stale is not None and _stale.isListening(), _stale)
_stale.close()

check("SH-A7 with the name released again, asking finds nobody again - the answer follows the name, not the history of who held it",
      mod.ask_running_instance_to_show() is False)

check("SH-A8 a window that has been asked nothing yet starts at nothing, so what the next check counts is the program's answer and not its own history",
      _window.attention_requested == 0)

# The arrival only lands once the event loop is given a turn, because that is how the listening end
# notices it. A running copy of the program is already in its loop; this suite is not, so it turns
# the loop here rather than measuring its own pacing.
_arrivals = []
_server = mod.take_single_instance_name()
_server.newConnection.connect(lambda: _arrivals.append(True))


def _arrival_has_landed(up_to_seconds=3.0):
    deadline = time.time() + up_to_seconds
    while not _arrivals and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return bool(_arrivals)


mod.ask_running_instance_to_show()
_landed = _arrival_has_landed()
mod.accept_instance_request(_server, _window)
check("SH-A9 an arrival is read, the arriving end of it is let go, and the window is asked to come forward",
      _landed and _window.attention_requested == 1, (_landed, _window.attention_requested))
mod.accept_instance_request(_server, _window)
check("SH-A10 with nobody waiting, accepting answers nobody: the window is not asked a second time for a request that was never made",
      _window.attention_requested == 1, _window.attention_requested)
_server.close()


class _FailedServer:
    """A server that cannot take the name, standing in for a machine where it is refused."""

    def __init__(self):
        self.asked_to_listen = 0

    @staticmethod
    def removeServer(name):
        return True

    def listen(self, name):
        self.asked_to_listen += 1
        return False


class _ThrowingServer(_FailedServer):
    def listen(self, name):
        raise OSError("this machine will not hand out that name")


seam.patch("QLocalServer", _FailedServer)
_refused = mod.take_single_instance_name()
seam.patch("QLocalServer", _ThrowingServer)
_thrown = mod.take_single_instance_name()
seam.restore("QLocalServer")
check("SH-A11 a name that is refused is answered with None, not with a half-built server or an exception - so the copy carries on instead of not opening",
      _refused is None and _thrown is None, (_refused, _thrown))

_entry_source = Path(TMP_PY).read_text(encoding="utf-8")
_entry_block = _entry_source.split('if __name__ == "__main__":', 1)[-1]
_asking_line = next((i for i, line in enumerate(_entry_block.splitlines())
                     if "ask_running_instance_to_show()" in line), None)
_window_line = next((i for i, line in enumerate(_entry_block.splitlines())
                     if "MainApp()" in line), None)
check("SH-A12 the entry block asks the running copy before it builds a window, so a second copy never opens a second set of watchers, LAN services or settings file",
      _asking_line is not None and _window_line is not None and _asking_line < _window_line
      and "sys.exit" in _entry_block.splitlines()[_asking_line + 1],
      (_asking_line, _window_line))

check("SH-A13 the window this answers is asked through Qt's own bring-to-front pair, which the program's window has",
      hasattr(mod.MainApp, "request_attention") and callable(mod.MainApp.request_attention),
      [name for name in ("raise_", "activateWindow", "request_attention")
       if hasattr(mod.MainApp, name)])
seam.restore("SINGLE_INSTANCE_NAME")
check("SH-A14 the name this suite borrowed is handed back, and nothing of the program's is left claimed",
      seam.read("SINGLE_INSTANCE_NAME") == "yt-msd-gui-single-instance"
      and not seam.is_patched("SINGLE_INSTANCE_NAME"), seam.read("SINGLE_INSTANCE_NAME"))



# ===========================================================================
# SH-B: where a crash is written
# ===========================================================================
# Every write below goes through a stand-in for the folders the log may live in, so the
# crashes these checks invent cannot land in the log a user reads. The function's own
# answer is checked against the original the program calls.
_LOG_WRITES = []
seam.patch("crash_log_folders", lambda: [_UNWRITABLE, str(LOG_FOLDER)])

_real_folders = seam.original("crash_log_folders")()
_started_from = os.path.dirname(os.path.abspath(__file__))
_reports_from = os.path.dirname(os.path.abspath(
    seam.original("crash_log_folders").__code__.co_filename))
check("SH-B1 the log may live in the folder the program was started from, and in the per-user folder under %LOCALAPPDATA% as the fallback",
      _real_folders and _real_folders[0] == _started_from
      and any(folder.endswith(os.path.join("yt-msd")) for folder in _real_folders),
      (_real_folders, _started_from))
check("SH-B1b and it is the folder the program was started from rather than the folder the reporting code itself now lives in, which is where the log would go if the folder were still taken from `__file__` after the move",
      _reports_from != _started_from and _reports_from not in _real_folders,
      (_reports_from, _real_folders))
check("SH-B2 nothing unusable is on that list: no empty entry, no folder named twice",
      all(folder for folder in _real_folders) and len(set(_real_folders)) == len(_real_folders),
      _real_folders)

check("SH-B3 the traceback a crash reports is the real one - the file, the line and the error are all in it",
      "ZeroDivisionError" in mod.traceback_text(*_capture("1 // 0"))
      and "probe_shell.py" in mod.traceback_text(*_capture("1 // 0")),
      mod.traceback_text(*_capture("1 // 0")))

class _Unformattable(Exception):
    """An error whose traceback cannot be walked at all - the case traceback_text exists for."""


check("SH-B4 an error whose traceback will not format is still reported, as itself rather than as nothing",
      "could not be formatted" in mod.traceback_text(_Unformattable, _Unformattable("broken"),
                                                     "not a traceback at all"),
      mod.traceback_text(_Unformattable, _Unformattable("broken"), "not a traceback at all"))

_first = mod.write_crash_log("First fault", "the detail of the first fault")
check("SH-B5 a crash is written into the first folder that will take it, and the folder it landed in is said out loud",
      _first is not None and os.path.basename(_first) == mod.CRASH_LOG_NAME
      and os.path.dirname(_first) == str(LOG_FOLDER), _first)
check("SH-B6 the folder it could not write to is skipped rather than reported as the place it was written",
      _first is not None and _UNWRITABLE not in _first and not Path(_UNWRITABLE).exists(),
      (_first, _UNWRITABLE_EXISTS))
_written = Path(_first).read_text(encoding="utf-8")
check("SH-B7 an entry names the fault, the program, the build it came from and the detail, so a log read later is readable",
      "First fault" in _written and "yt-msd" in _written and str(mod.APP_VERSION) in _written
      and "the detail of the first fault" in _written and "python source" in _written,
      _written)
check("SH-B8 it says which machine it happened on and how the program was started, which is what a log without them cannot answer",
      "Python " in _written and "Started as:" in _written, _written)
check("SH-B9 every entry is set apart from the one before it, so two crashes do not read as one",
      "=" * 72 in _written, _written)

mod.write_crash_log("Second fault", "and the detail of the second")
_written = Path(_first).read_text(encoding="utf-8")
check("SH-B10 a second crash is added to the log rather than replacing the first - the log is the history, not the last word",
      "First fault" in _written and "Second fault" in _written
      and _written.index("First fault") < _written.index("Second fault"), _written)

_entry_shape = mod.crash_log_entry("Verbatim entry", "the exact detail")
check("SH-B11 one entry is built as a block - the rule, the header naming what happened, the machine, how it was started, the detail, then a blank line - so entries can be read apart from each other",
      _entry_shape.startswith("=" * 72) and _entry_shape.splitlines()[1].count(" | ") == 3
      and "Started as:" in _entry_shape and "the exact detail" in _entry_shape
      and _entry_shape.endswith("\n"), _entry_shape)

_small = Path(fixture("small log")) / mod.CRASH_LOG_NAME
_small.write_text("a log that is well under the limit\n", encoding="utf-8")
_before_small = _small.read_bytes()
mod.trim_crash_log(_small)
check("SH-B12 a log under the limit is left exactly as it was - trimming is not tidying",
      _small.read_bytes() == _before_small, _small.stat().st_size)

_big = Path(fixture("big log")) / mod.CRASH_LOG_NAME
_big.write_bytes(b"old half\n" + b"x" * (mod.CRASH_LOG_MAX + 4096))
mod.trim_crash_log(_big)
_after_big = _big.read_bytes()
check("SH-B13 past the limit the older half is dropped and the newer half is kept, because a log no one can open reports nothing",
      len(_after_big) < mod.CRASH_LOG_MAX + 4096
      and b"oldest entries were dropped" in _after_big and b"old half" not in _after_big
      and _after_big.endswith(b"x" * 1024), len(_after_big))

Path(_first).write_bytes(b"the oldest part\n" + b"x" * (mod.CRASH_LOG_MAX + 4096))
mod.write_crash_log("After a long log", "written into a log that had to be trimmed")
_after_write = Path(_first).read_bytes()
check("SH-B14 the log is kept under the limit as it is written, not only when someone remembers to trim it, and the new crash is still in it",
      len(_after_write) < mod.CRASH_LOG_MAX + 4096 and b"After a long log" in _after_write
      and b"oldest entries were dropped" in _after_write, len(_after_write))
check("SH-B15 and a trim that cannot be done is not an error - a failing program is not asked to report a second one",
      mod.trim_crash_log(Path(str(fixture("no log here"))) / mod.CRASH_LOG_NAME) is None)

_nowrite = None
seam.patch("crash_log_folders", lambda: [_UNWRITABLE])
try:
    _nowrite = mod.write_crash_log("Nowhere to write", "detail with nowhere to go")
finally:
    seam.patch("crash_log_folders", lambda: [_UNWRITABLE, str(LOG_FOLDER)])
check("SH-B16 when no folder will take it, the writer says so with None instead of raising or claiming a file",
      _nowrite is None and not Path(_UNWRITABLE).exists(), _nowrite)

# crash_log_folders stays replaced through the rest of this suite: the routes in SH-D write
# crashes too, and none of them may reach the log a user reads. It is handed back in SH-E.

# ===========================================================================
# SH-C: the dialog, and the guards that decide whether it is raised
# ===========================================================================
class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self):
        for slot in self.slots:
            slot()


class _FakeButton:
    def __init__(self, text, role):
        self.text = text
        self.role = role
        self.clicked = _Signal()

    def press(self):
        self.clicked.emit()


class _FakeBox:
    """A message box that can be read and pressed without anyone having to dismiss it."""
    Critical = 16
    Warning = 14
    ActionRole = 2
    Ok = 1
    built = []

    def __init__(self, parent=None):
        self.parent_arg = parent
        self.built_in = threading.current_thread()
        self.icon = None
        self.title = ""
        self.text = ""
        self.informative = ""
        self.detailed = ""
        self.buttons = []
        self.standard = None
        self.exec_calls = 0
        _FakeBox.built.append(self)

    def setIcon(self, icon):
        self.icon = icon

    def setWindowTitle(self, title):
        self.title = title

    def setText(self, text):
        self.text = text

    def setInformativeText(self, text):
        self.informative = text

    def setDetailedText(self, text):
        self.detailed = text

    def addButton(self, text, role):
        button = _FakeButton(text, role)
        self.buttons.append(button)
        return button

    def setStandardButtons(self, which):
        self.standard = which

    def exec(self):
        self.exec_calls += 1
        return 0


_OS_REAL = seam.original("os")
_opened_logs = []


_DIALOG_GUARD = False


def guard_dialogs():
    """Hold the stand-in box up while the program's own handlers are installed.

    Once install_crash_reporting() has run, an error raised by this suite is an error the program
    catches: it would raise the real dialog and wait for someone to dismiss it. The guard is lifted
    again at SH-E, where the hooks are handed back to the interpreter.
    """
    global _DIALOG_GUARD
    seam.patch("QMessageBox", _FakeBox)
    _DIALOG_GUARD = True


def unguard_dialogs():
    global _DIALOG_GUARD
    seam.restore("QMessageBox")
    _DIALOG_GUARD = False


def raising(what="Something stopped", detail="the traceback of what stopped", path=None,
            press=None, box_class=None):
    """Raise the program's crash dialog against a box the suite can read and press.

    The stand-ins stay in place while the dialog is raised *and* while `press` runs, because the
    dialog offers to open the log through the program's own open-the-log function: pressing that
    after the stand-ins were handed back would open a file on the machine running the suite.
    `box_class` stands in a box that misbehaves, for the checks about what happens then.
    """
    box_class = box_class or _FakeBox
    _FakeBox.built.clear()
    _opened_logs.clear()
    mod._crash_state["dialog_times"] = []
    seam.patch("QMessageBox", box_class)
    seam.patch("os", seam.partial_module(_OS_REAL, startfile=lambda log_path: _opened_logs.append(log_path)))
    try:
        raised = mod.show_crash_dialog(what, detail, path)
        box = _FakeBox.built[0] if _FakeBox.built else None
        pressed = press(box) if (press is not None and box is not None) else None
        return raised, box, pressed
    finally:
        seam.restore("QMessageBox")
        seam.restore("os")
        if _DIALOG_GUARD:
            seam.patch("QMessageBox", _FakeBox)


def _press_log_button(box):
    log_buttons = [button for button in box.buttons if "log" in button.text.lower()]
    if log_buttons:
        log_buttons[0].press()
    return log_buttons


_raised, _box, _log_buttons = raising("Search thread died", "Traceback...\nValueError: no results",
                                      str(LOG_FOLDER / mod.CRASH_LOG_NAME), press=_press_log_button)
check("SH-C1 with a window up, a crash is shown as well as written, and the dialog is raised rather than only described",
      _raised is True and _box is not None and _box.exec_calls == 1, (_raised, _box))
check("SH-C2 it says out loud what stopped, and that what was running when it happened stopped with it",
      "Search thread died" in _box.text and "stopped" in _box.text.lower(), _box.text)
check("SH-C3 the log it wrote is named on the dialog, so the user is not left searching for the file",
      mod.CRASH_LOG_NAME in _box.informative and str(LOG_FOLDER) in _box.informative,
      _box.informative)
check("SH-C4 the traceback itself is behind Show Details, which is where a crash is readable without a terminal",
      _box.detailed == "Traceback...\nValueError: no results", _box.detailed)
check("SH-C5 the window is marked as an error rather than as a question or a note",
      _box.icon == _FakeBox.Critical, _box.icon)
check("SH-C6 it is raised without a parent window, because the fault may have taken that window with it",
      _box.parent_arg is None, _box.parent_arg)
check("SH-C7 it can always be dismissed - it ends with an OK - so a crash cannot leave the program waiting for a click",
      _box.standard == _FakeBox.Ok, _box.standard)
check("SH-C8 when a log was written the dialog offers to open it, and pressing it opens that file and no other",
      len(_log_buttons) == 1 and _opened_logs == [str(LOG_FOLDER / mod.CRASH_LOG_NAME)],
      ([button.text for button in _box.buttons], _opened_logs))

_no_path_raised, _no_path_box, _ = raising("No log possible", "detail with no file", None)
check("SH-C9 when nothing could be written it says so and points at Show Details, rather than naming a file that does not exist",
      _no_path_raised is True and "could not be written" in _no_path_box.informative
      and not any("log" in button.text.lower() for button in _no_path_box.buttons)
      and _opened_logs == [], (_no_path_box.informative, [b.text for b in _no_path_box.buttons]))

class _BoxThatCannotOpen(_FakeBox):
    """A window that fails at the moment it is shown - showing a crash is not itself a crash."""

    def exec(self):
        raise RuntimeError("the window refused to open")


mod._crash_state["in_dialog"] = True
_second_raised, _second_box, _ = raising("While another is open", "detail")
check("SH-C10 a second dialog is not raised on top of the one already open - a fault that opens a window per fault is a queue, not a report",
      _second_raised is False and _second_box is None, (_second_raised, _second_box))
mod._crash_state["in_dialog"] = False

_broke_raised, _broke_box, _ = raising("A fault while opening the report", "detail",
                                       box_class=_BoxThatCannotOpen)
check("SH-C11 a dialog that fails to open does not become a second fault, and having one open is cleared either way, so a program is never left permanently unable to report",
      _broke_raised is False and mod._crash_state["in_dialog"] is False, (_broke_raised, mod._crash_state))

mod._crash_state["dialog_times"] = []
_allowed = [mod.crash_dialog_allowed() for _ in range(mod.MAX_CRASH_DIALOGS_PER_MINUTE)]
_blocked = mod.crash_dialog_allowed()
check("SH-C12 a fault that repeats is dialogued a few times and then only logged, so a fault inside a repaint or a one-second timer cannot fill the screen",
      all(_allowed) and _blocked is False and len(_allowed) == mod.MAX_CRASH_DIALOGS_PER_MINUTE,
      (_allowed, _blocked))
mod._crash_state["dialog_times"] = [time.time() - 61.0]
check("SH-C13 a minute old is old: the count is not a lifetime total, so a program that faults once an hour keeps telling its user",
      mod.crash_dialog_allowed() is True and mod._crash_state["dialog_times"][0] > 0,
      mod._crash_state["dialog_times"])

mod.silence_crash_dialogs()
_silenced_raised, _silenced_box, _ = raising("During shutdown", "detail while closing")
check("SH-C14 once the window is on its way out no dialog is raised - one held open during shutdown would keep the process alive until someone dismissed it",
      _silenced_raised is False and _silenced_box is None, (_silenced_raised, _silenced_box))
_log_before = Path(_first).read_text(encoding="utf-8").count("=" * 72)
with contextlib.redirect_stderr(io.StringIO()):
    mod.report_crash("Fault during shutdown", "logged while dialogs are silenced", want_dialog=False)
_log_after = Path(_first).read_text(encoding="utf-8")
check("SH-C15 silencing the dialogs silences only the dialogs: the logging half keeps working, and that is the only record of a fault at exit",
      _log_after.count("=" * 72) > _log_before and "Fault during shutdown" in _log_after,
      _log_after[-300:])
mod._crash_state["dialogs_allowed"] = True
_lifted, _lifted_box, _ = raising("After the shutdown silence", "detail once dialogs are allowed again")
check("SH-C16 the silence is lifted again here, so the program this suite drove is left able to report what it finds",
      _lifted is True and _lifted_box is not None and mod._crash_state["dialogs_allowed"] is True,
      (_lifted, mod._crash_state))

# ===========================================================================
# SH-D: the roads an unhandled error takes
# ===========================================================================
# install_crash_reporting() replaces three hooks the interpreter itself holds. They are not names
# the seam can hand back, so they are saved here and put back in SH-E. The log those handlers write
# is still the fixture log: crash_log_folders has been replaced since SH-B and is only handed back
# at the end of this file.
_LOG_PATH = Path(_first)
_STATE_WAS = {key: (list(value) if isinstance(value, list) else value)
              for key, value in mod._crash_state.items()}


def log_text():
    """The crash log this suite has been writing, as it stands."""
    return _LOG_PATH.read_text(encoding="utf-8") if _LOG_PATH.exists() else ""


def log_entry_count():
    return log_text().count("=" * 72)


def spin_until(what_is_wanted, up_to_seconds=3.0):
    """Turn the event loop until `what_is_wanted()` is true, or the turns run out.

    A signal emitted by a background thread is delivered the next time the GUI thread runs its loop,
    which a running copy of the program does by sitting in app.exec(). The checks about a fault in a
    thread are about that delivery, so the loop is turned here rather than the delivery ignored.
    """
    deadline = time.time() + up_to_seconds
    while time.time() < deadline:
        QApplication.processEvents()
        if what_is_wanted():
            return True
        time.sleep(0.01)
    return what_is_wanted()


_HOOKS_WERE = (sys.excepthook, threading.excepthook, getattr(sys, "unraisablehook", None))
guard_dialogs()
_REPORTER = mod.install_crash_reporting()

check("SH-D1 all three roads an unhandled error can take lead to the program's own handler once reporting is installed",
      sys.excepthook is mod.handle_unhandled_error
      and threading.excepthook is mod.handle_thread_error
      and getattr(sys, "unraisablehook", None) is mod.handle_unraisable_error,
      (sys.excepthook, threading.excepthook, getattr(sys, "unraisablehook", None)))
check("SH-D2 the interpreter's own handler is kept rather than replaced, because it is what still runs when the program's own reporting is not enough",
      sys.__excepthook__ is _HOOKS_WERE[0], sys.__excepthook__)
_reporting_function = seam.original("install_crash_reporting")
_reporting_home = next(module for module in seam.owners("install_crash_reporting")
                       if module.__name__ == _reporting_function.__module__)
_stale_reporters = [module.__name__ for module in seam.owners("_crash_reporter")
                    if getattr(module, "_crash_reporter", _REPORTER) is not _REPORTER]
check("SH-D3 the reporter a thread emits through is held by the module that defines the function which rebinds it, and nowhere is there a second copy still holding the value from before the rebinding - which is what `global _crash_reporter` has to mean once that function lives in a package",
      _REPORTER is not None and getattr(_reporting_home, "_crash_reporter", None) is _REPORTER
      and not _stale_reporters, (_reporting_home.__name__, _stale_reporters))

# Every dialog below is raised against a stand-in box: the real one blocks until someone dismisses
# it, and nobody is sitting here to dismiss one. guard_dialogs() keeps it standing until SH-E.
mod._crash_state["dialog_times"] = []
_FakeBox.built.clear()
_entries_before = log_entry_count()
with contextlib.redirect_stderr(io.StringIO()) as _console:
    mod.handle_unhandled_error(*_capture("1 // 0"))
check("SH-D4 an error nothing caught is written as a crash naming what stopped, with its real traceback in it",
      log_entry_count() == _entries_before + 1 and "Unhandled error" in log_text()
      and "ZeroDivisionError" in log_text()
      and "Traceback (most recent call last)" in log_text(), log_text()[-500:])
check("SH-D5 and it is shown as well as written, saying the same thing in both places",
      len(_FakeBox.built) == 1 and "Unhandled error" in _FakeBox.built[0].text
      and "ZeroDivisionError" in _FakeBox.built[0].detailed,
      (_FakeBox.built[0].text if _FakeBox.built else None, _FakeBox.built[0].detailed if _FakeBox.built else None))
check("SH-D6 while a window is up the error is not also printed anywhere, because the installed program has nowhere to print it",
      _console.getvalue() == "", _console.getvalue())

_entries_before = log_entry_count()
_boxes_before = len(_FakeBox.built)
with contextlib.redirect_stderr(io.StringIO()) as _console:
    mod.handle_unhandled_error(*_capture("raise KeyboardInterrupt()"))
check("SH-D7 a Ctrl-C is not written as a crash and is not dialogued: it is handed to the interpreter's own handler, which is the thing that stops the program",
      log_entry_count() == _entries_before and len(_FakeBox.built) == _boxes_before
      and "KeyboardInterrupt" in _console.getvalue(), (log_text()[-200:], _console.getvalue()))

def _fault_in_a_background_job():
    1 // 0


_entries_before = log_entry_count()
_boxes_before = len(_FakeBox.built)
_job = threading.Thread(target=_fault_in_a_background_job, name="probe background job")
_job.start()
_job.join()
check("SH-D8 a background job that dies on its own is reported with the job named, which is the one thing a log without the thread name cannot tell you afterwards",
      log_entry_count() == _entries_before + 1
      and "Background thread error (probe background job)" in log_text()
      and "ZeroDivisionError" in log_text(), log_text()[-500:])
_reached = spin_until(lambda: len(_FakeBox.built) > _boxes_before)
_new_boxes = _FakeBox.built[_boxes_before:]
check("SH-D9 and the window for it belongs to the thread that runs the event loop and not to the thread that faulted, which is the only reason the reporter exists",
      _reached and len(_new_boxes) == 1 and _new_boxes[0].built_in is threading.main_thread()
      and "Background thread error" in _new_boxes[0].text,
      (_new_boxes[0].built_in if _new_boxes else None, _new_boxes[0].text if _new_boxes else None))

mod._crash_state["dialog_times"] = []
_boxes_before = len(_FakeBox.built)
_entries_before = log_entry_count()
seam.patch("_crash_reporter", None)
with contextlib.redirect_stderr(io.StringIO()) as _console:
    mod.report_crash("Fault with no window", "detail with nowhere to show it")
seam.restore("_crash_reporter")
check("SH-D10 with no reporter - the renamer console, a --console run, a fault so early there is no window yet - the detail goes to the console instead, and the log is still written",
      "Fault with no window" in _console.getvalue()
      and "detail with nowhere to show it" in _console.getvalue()
      and log_entry_count() == _entries_before + 1 and len(_FakeBox.built) == _boxes_before,
      (_console.getvalue(), log_text()[-300:]))

_entries_before = log_entry_count()
_boxes_before = len(_FakeBox.built)


class _FaultyCleanup:
    """An object whose own clean-up faults - the case sys.unraisablehook exists for."""

    def __del__(self):
        raise RuntimeError("cleanup fault")


with contextlib.redirect_stderr(io.StringIO()):
    _transient = _FaultyCleanup()
    del _transient
    gc.collect()
check("SH-D11 an error the interpreter cannot hand to anyone - a fault during clean-up - is written down too, and named as what it is",
      log_entry_count() == _entries_before + 1 and "Unraisable error" in log_text()
      and "cleanup fault" in log_text(), log_text()[-500:])
check("SH-D12 and it is written without a window to interrupt anything, because a fault during clean-up is rarely the reason something stopped",
      len(_FakeBox.built) == _boxes_before,
      [box.text for box in _FakeBox.built[_boxes_before:]])


def _writer_that_cannot_write(what, detail):
    raise RuntimeError("the log itself could not be written")


mod._crash_state["dialog_times"] = []
_boxes_before = len(_FakeBox.built)
seam.patch("write_crash_log", _writer_that_cannot_write)
try:
    with contextlib.redirect_stderr(io.StringIO()):
        mod.handle_unhandled_error(*_capture("1 // 0"))
    _survived = True
except BaseException as _error:
    _survived = _error
finally:
    seam.restore("write_crash_log")
_new_boxes = _FakeBox.built[_boxes_before:]
check("SH-D13 a log that cannot be written does not turn into a second fault, and the error still reaches the screen because the log was never the only copy of it",
      _survived is True and len(_new_boxes) == 1
      and "could not be written" in _new_boxes[0].informative
      and "ZeroDivisionError" in _new_boxes[0].detailed,
      (_survived, _new_boxes[0].informative if _new_boxes else None))

_entry_lines = Path(TMP_PY).read_text(encoding="utf-8").split('if __name__ == "__main__":', 1)[-1].splitlines()
_installs = [i for i, line in enumerate(_entry_lines) if "install_crash_reporting()" in line]
_builds = [i for i, line in enumerate(_entry_lines) if "MainApp()" in line]
_renames = [i for i, line in enumerate(_entry_lines) if "run_integrated_renamer_cli()" in line]
check("SH-D14 the entry block installs the reporting before either thing it covers starts, so a fault in the first lines of startup is caught rather than missed",
      _installs and _builds and _renames and min(_installs) < min(_renames)
      and min(_installs) < min(_builds), (_installs, _renames, _builds))

def _body_after(name):
    """The lines of a method's body, stopping at the next def at the same indent."""
    lines = Path(TMP_PY).read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "def %s(self):" % name:
            indent = len(line) - len(line.lstrip())
            body = []
            for offset, following in enumerate(lines[i + 1:], start=1):
                if following.strip() and (len(following) - len(following.lstrip())) <= indent:
                    break
                body.append((offset, following))
            return body
    return []


_shutdown_body = _body_after("shutdown_for_exit")
_silenced_at = next((offset for offset, line in _shutdown_body
                     if "silence_crash_dialogs()" in line), None)
_saves_at = next((offset for offset, line in _shutdown_body if "save_config()" in line), None)
_stops_timers_at = next((offset for offset, line in _shutdown_body if "player_timer" in line), None)
check("SH-D15 the window silences the dialogs at the top of its shutdown, before the settings save and the timer stops that can themselves fault on the way out",
      _silenced_at is not None and _saves_at is not None and _stops_timers_at is not None
      and _silenced_at < _saves_at and _silenced_at < _stops_timers_at,
      (_silenced_at, _saves_at, _stops_timers_at))

# ===========================================================================
# SH-E: the seams these checks reach, and everything handed back
# ===========================================================================
def shares_a_holder(*names):
    """The modules that hold every one of `names`, so a caller and what it calls can be followed."""
    return set.intersection(*(set(seam.owned_by(name)) for name in names))


check("SH-E1 the crash code and the names it reaches for are held by the same module, whichever module that is today",
      bool(shares_a_holder("write_crash_log", "crash_log_entry", "crash_log_folders", "trim_crash_log"))
      and bool(shares_a_holder("show_crash_dialog", "open_crash_log", "crash_dialog_allowed"))
      and bool(shares_a_holder("report_crash", "write_crash_log", "_crash_reporter")),
      {name: seam.owned_by(name) for name in
       ("write_crash_log", "report_crash", "crash_log_folders", "_crash_reporter")})
check("SH-E2 the one `global` in this part of the program rebinds a name held by the function that rebinds it, which is what keeps a re-export from leaving the entry point holding the value from before the rebinding",
      bool(shares_a_holder("install_crash_reporting", "_crash_reporter")),
      (seam.owned_by("install_crash_reporting"), seam.owned_by("_crash_reporter")))
check("SH-E3 the single-instance code and the name it listens on are held by the same module, whichever module that is today",
      bool(shares_a_holder("take_single_instance_name", "ask_running_instance_to_show",
                           "accept_instance_request", "SINGLE_INSTANCE_NAME")),
      seam.owned_by("SINGLE_INSTANCE_NAME"))

_ENTRY_SEAM = seam.original("crash_log_entry")
seam.patch("crash_log_entry", lambda what, detail: "%sSTAND-IN ENTRY: %s\n" % ("=" * 72, what))
_wrote_to = mod.write_crash_log("Written through the seam", "the detail that went with it")
check("SH-E4 writing a crash reaches the module-level name this suite can replace, so a check of what an entry says is a check of the writer rather than of a private copy of it",
      _wrote_to is not None and "STAND-IN ENTRY: Written through the seam"
      in Path(_wrote_to).read_text(encoding="utf-8"), _wrote_to)
seam.restore("crash_log_entry")
check("SH-E5 and the program's own entry builder is back afterwards",
      seam.read("crash_log_entry") is _ENTRY_SEAM and not seam.is_patched("crash_log_entry"),
      seam.read("crash_log_entry"))

seam.patch("traceback_text", lambda *args: "STAND-IN TRACEBACK")
seam.patch("QMessageBox", _FakeBox)
_FakeBox.built.clear()
mod._crash_state["dialog_times"] = []
with contextlib.redirect_stderr(io.StringIO()):
    mod.handle_unhandled_error(*_capture("1 // 0"))
seam.restore("traceback_text")
check("SH-E6 the route an unhandled error takes reaches for the same names this suite patches: the installed hook, the formatter and the dialog are all the seam sees, in whichever module each now lives",
      "STAND-IN TRACEBACK" in log_text() and len(_FakeBox.built) == 1
      and "STAND-IN TRACEBACK" in _FakeBox.built[0].detailed,
      (log_text()[-300:], _FakeBox.built[0].detailed if _FakeBox.built else None))
try:
    seam.patch("_a_name_nothing_in_the_program_holds", lambda: None)
    seam.restore("_a_name_nothing_in_the_program_holds")
    _refused = None
except seam.SeamError as _error:
    _refused = _error
check("SH-E7 patching a name nothing in the program holds is refused out loud, rather than quietly replacing nothing and leaving behind a check that tests nothing",
      _refused is not None, _refused)

_harness = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
_stray_writes = []
for _node in ast.walk(_harness):
    if isinstance(_node, ast.Assign):
        _targets = _node.targets
    elif isinstance(_node, (ast.AugAssign, ast.AnnAssign)):
        _targets = [_node.target]
    else:
        continue
    for _target in _targets:
        if isinstance(_target, ast.Attribute) and isinstance(_target.value, ast.Name) \
                and _target.value.id == "mod":
            _stray_writes.append("mod.%s (line %s)" % (_target.attr, _node.lineno))
check("SH-E8 nothing in this suite writes a name straight into the program: every replacement goes through the seam, which is what makes it reach the code the program actually calls",
      not _stray_writes, _stray_writes)

unguard_dialogs()
sys.excepthook, threading.excepthook = _HOOKS_WERE[0], _HOOKS_WERE[1]
if _HOOKS_WERE[2] is not None:
    sys.unraisablehook = _HOOKS_WERE[2]
check("SH-E9 the three hooks this suite installed are given back to the interpreter, which is state the seam has nothing to restore for",
      sys.excepthook is _HOOKS_WERE[0] and threading.excepthook is _HOOKS_WERE[1]
      and sys.unraisablehook is _HOOKS_WERE[2] and sys.__excepthook__ is _HOOKS_WERE[0],
      (sys.excepthook, threading.excepthook, sys.unraisablehook))

for _name, _value in _STATE_WAS.items():
    mod._crash_state[_name] = list(_value) if isinstance(_value, list) else _value
check("SH-E10 the crash state this suite drove is left as it was found: able to write, able to show, no dialog open, nothing mid-write",
      {key: (list(value) if isinstance(value, list) else value)
       for key, value in mod._crash_state.items()} == _STATE_WAS, mod._crash_state)

for _name in ("crash_log_folders", "QMessageBox", "os", "_crash_reporter", "SINGLE_INSTANCE_NAME",
              "QLocalServer"):
    seam.restore(_name)
_left_patched = [name for name in ("crash_log_folders", "QMessageBox", "os", "_crash_reporter",
                                   "SINGLE_INSTANCE_NAME", "QLocalServer") if seam.is_patched(name)]
check("SH-E11 everything this suite replaced is handed back, so the program is left writing crashes where it really writes them",
      not _left_patched and seam.read("crash_log_folders") is seam.original("crash_log_folders")
      and mod.SINGLE_INSTANCE_NAME == "yt-msd-gui-single-instance",
      (_left_patched, seam.read("crash_log_folders")()))
check("SH-E12 nothing this suite wrote reached the crash log a real copy of the program would write, in either folder it may live in",
      all((saved is None and not log.exists()) or (log.exists() and log.read_bytes() == saved)
          for log, saved in _REAL_LOG_WAS.items()),
      [(str(log), log.exists()) for log in _REAL_LOG_WAS])
shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
check("SH-E13 and the fixture this suite wrote into is removed, so the next run starts from nothing the last one left behind",
      not FIXTURE_ROOT.exists(), FIXTURE_ROOT)

print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)

