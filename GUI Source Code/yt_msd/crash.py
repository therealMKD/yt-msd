# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.crash).
import os
import sys
import threading
import time
import traceback
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Signal, QObject
from yt_msd.constants import APP_VERSION
from yt_msd.paths import program_folder


# ============================================================
# CRASH REPORTING - where an unhandled error goes
#
# The installed program is a windowed exe: no console, no terminal behind it, and a
# windowed PyInstaller build gives print() nowhere to go. An error that no part of
# the program caught has had nowhere to say itself out loud - the window simply
# stopped doing whatever it was doing, and the only way to read the reason was to
# run the .pyw from a terminal with "py yt-msd-gui.pyw".
#
# So an unhandled error is written to yt-msd-crash.log in the folder the program
# sits in (or in %LOCALAPPDATA%\yt-msd when that folder cannot be written to) and,
# while the window is still there, shown in a dialog that names the failure and
# points at the log. This lives in the source rather than in the build, so the .pyw
# and the compiled exe behave the same; install_crash_reporting() is called by the
# entry block below, before any of the program's own work starts.
# ============================================================

CRASH_LOG_NAME = "yt-msd-crash.log"

CRASH_LOG_MAX = 256 * 1024          # past this, the older half of the log is dropped

MAX_CRASH_DIALOGS_PER_MINUTE = 3    # a fault that repeats is logged, not repeated


_crash_state = {"writing_log": False, "in_dialog": False,
                "dialogs_allowed": True, "dialog_times": []}

_crash_reporter = None  # the QObject that carries a background error to the GUI thread



def traceback_text(exc_type, exc_value, exc_traceback):
    """The traceback as text, or a plain description when it will not format."""
    try:
        return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    except Exception:
        return "Error could not be formatted: %r: %r" % (exc_type, exc_value)



def crash_log_folders():
    r"""The folders the crash log may live in, best first.

    First is the folder the program itself sits in, which is where gui_config.json
    already is; the installer puts that under %LOCALAPPDATA%, so it is writable
    without an administrator. %LOCALAPPDATA%\yt-msd is the fallback for a copy run
    from somewhere it may not be allowed to write to - C:\Program Files, a read-only
    share, a USB drive that was pulled out mid-run.
    """
    folders = []
    if getattr(sys, "frozen", False):
        folders.append(os.path.dirname(os.path.abspath(sys.executable)))
        folders.append(getattr(sys, "_MEIPASS", ""))
    else:
        try:
            folders.append(program_folder())
        except NameError:  # a module that was never given a file at all
            pass
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        folders.append(os.path.join(local, "yt-msd"))
    unique = []
    for folder in folders:
        if folder and folder not in unique:
            unique.append(folder)
    return unique



def trim_crash_log(path):
    """Drop the older half of the log once it passes CRASH_LOG_MAX, so a program
    that fails most days does not end up with a file no one can open."""
    try:
        if os.path.getsize(path) <= CRASH_LOG_MAX:
            return
        keep = CRASH_LOG_MAX // 2
        with open(path, "rb") as handle:
            handle.seek(-keep, os.SEEK_END)
            tail = handle.read()
        note = b"[the oldest entries were dropped to keep this file small]\n"
        with open(path, "wb") as handle:
            handle.write(note + tail)
    except OSError:
        pass  # the log is the last thing a failing program can still do



def crash_log_entry(what, detail):
    """One entry: when, which program, which build, how it was started, and the
    traceback itself. Enough to read an error without the machine it happened on."""
    build = "installed program" if getattr(sys, "frozen", False) else "python source"
    lines = [
        "=" * 72,
        "%s | yt-msd %s | %s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"),
                                      APP_VERSION, build, what),
        "Python %s on %s" % (sys.version.split()[0], sys.platform),
        "Started as: %s" % " ".join(sys.argv),
        detail.rstrip(),
        "",
    ]
    return "\n".join(lines)



def write_crash_log(what, detail):
    """Append one crash to yt-msd-crash.log, in the first folder that will take it.
    Returns the path written, or None when no folder would.

    Nothing here is allowed to fail loudly: this runs when the program is already
    failing, and a second fault while reporting the first would hide it.
    """
    entry = crash_log_entry(what, detail)
    for folder in crash_log_folders():
        try:
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, CRASH_LOG_NAME)
            trim_crash_log(path)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(entry)
            return path
        except OSError:
            continue
    return None



class CrashReporter(QObject):
    """The bridge a background thread uses to reach the GUI thread.

    A widget may only be created in the thread that runs the event loop, so a thread
    that fails cannot raise a dialog itself. It emits this signal instead, and Qt
    delivers it in the thread this object was created in - the GUI thread.
    """
    report_requested = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self.report_requested.connect(self._show)

    def _show(self, what, detail, path):
        show_crash_dialog(what, detail, path or None)



def crash_dialog_allowed():
    """At most MAX_CRASH_DIALOGS_PER_MINUTE dialogs a minute. A fault inside a
    repaint or a one-second timer would otherwise raise a new dialog on every tick
    of it, and the log keeps every one of them."""
    now = time.time()
    recent = [shown for shown in _crash_state["dialog_times"] if now - shown < 60.0]
    if len(recent) >= MAX_CRASH_DIALOGS_PER_MINUTE:
        _crash_state["dialog_times"] = recent
        return False
    recent.append(now)
    _crash_state["dialog_times"] = recent
    return True



def open_crash_log(path):
    """Open the log in whatever edits .log files. Only the button on the dialog
    calls this, and nothing depends on it working."""
    try:
        os.startfile(path)
        return True
    except OSError:
        return False



def show_crash_dialog(what, detail, path):
    """The dialog: what stopped, the traceback behind "Show Details", and where the
    same text was written. Returns True when a dialog was raised."""
    if not _crash_state["dialogs_allowed"] or _crash_state["in_dialog"]:
        return False
    if QApplication.instance() is None or not crash_dialog_allowed():
        return False
    _crash_state["in_dialog"] = True
    try:
        box = QMessageBox()  # no parent: a crash may have taken the window with it
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("yt-msd ran into an error")
        box.setText("yt-msd hit an error it could not handle: %s\n\n"
                    "Whatever was running when it happened stopped. The full error is "
                    "behind \"Show Details\", and in the log file." % what)
        if path:
            box.setInformativeText("Written to: %s" % path)
        else:
            box.setInformativeText("The error could not be written to a log file - "
                                   "use \"Show Details\" to read it or copy it.")
        box.setDetailedText(detail)
        if path:
            open_button = box.addButton("Open the log file", QMessageBox.ActionRole)
            open_button.clicked.connect(lambda checked=False, log=path: open_crash_log(log))
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()
        return True
    except Exception:
        return False
    finally:
        _crash_state["in_dialog"] = False



def report_crash(what, detail, want_dialog=True):
    """Write the failure down, then say so: a dialog while the window is up, the
    traceback on stderr when it is not - the renamer console, a "--console" run of
    the exe, or a failure so early there is no window yet."""
    path = None
    if not _crash_state["writing_log"]:
        _crash_state["writing_log"] = True
        try:
            path = write_crash_log(what, detail)
        except Exception:
            path = None
        finally:
            _crash_state["writing_log"] = False

    if want_dialog and _crash_reporter is not None and QApplication.instance() is not None:
        try:
            _crash_reporter.report_requested.emit(what, detail, path or "")
            return path
        except RuntimeError:  # the GUI thread that owned the reporter is gone
            pass

    stream = getattr(sys, "stderr", None)
    if stream is not None:
        try:
            stream.write("%s\n%s\n" % (what, detail))
            stream.flush()
        except Exception:
            pass
    return path



def handle_unhandled_error(exc_type, exc_value, exc_traceback):
    """sys.excepthook - anything that escapes the program's own try/except blocks."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    report_crash("Unhandled error", traceback_text(exc_type, exc_value, exc_traceback))



def handle_thread_error(args):
    """threading.excepthook - a background job that died on its own. The window
    carries on; the job that was running in that thread does not."""
    name = getattr(args.thread, "name", "") or "unnamed"
    report_crash("Background thread error (%s)" % name,
                 traceback_text(args.exc_type, args.exc_value, args.exc_traceback))



def handle_unraisable_error(args):
    """sys.unraisablehook - an error Python could not hand to anyone: inside a __del__,
    inside a garbage-collection pass, inside the clean-up done at exit. Those are
    written down and left alone, because they are rarely the reason something stopped.
    """
    try:
        detail = "%s\n%s" % (getattr(args, "err_msg", "Unraisable exception"),
                             traceback_text(getattr(args, "exc_type", None),
                                           getattr(args, "exc_value", None),
                                           getattr(args, "exc_traceback", None)))
    except Exception:
        detail = repr(args)
    report_crash("Unraisable error", detail, want_dialog=False)



def install_crash_reporting():
    """Point every route an unhandled error can take at the log and the dialog.
    Called once from the entry block, before the window or the renamer starts."""
    global _crash_reporter
    sys.excepthook = handle_unhandled_error
    threading.excepthook = handle_thread_error
    if hasattr(sys, "unraisablehook"):
        sys.unraisablehook = handle_unraisable_error
    if _crash_reporter is None and QApplication.instance() is not None:
        _crash_reporter = CrashReporter()
    return _crash_reporter



def silence_crash_dialogs():
    """Stop raising dialogs, which is what the window does on its way out: a dialog
    raised during shutdown would hold the process open until someone dismissed it.
    The logging side keeps working."""
    _crash_state["dialogs_allowed"] = False
