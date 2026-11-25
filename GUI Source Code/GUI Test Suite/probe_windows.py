"""The windows regression harness.

Sections WN-A..WN-M cover the windows half of `GUI Source Code/yt-msd-gui.pyw`: the settings window
and where each of its controls writes, the three windows that build a sync chain (host, client,
removable drive), the sync manager that lists and pauses and removes them, the playlist picker, the
tray progress bubble, the three update windows, the rename-from-metadata window, the two things
the program promises the machine - which file Windows is told to start, and which yt-dlp it looks for
- the question a sync asks before it deletes more than its chain allows, the three answers that question
has once Restore Host exists and the windows that carry them - the code a Host puts on its own screen and
the box a client types it into - and the window that searches
the network for a host along with the once-only notice a Host is given about chains that were already
visible when this choice existed, and the start of the main window itself - a saved search with no
saved session behind it, which is how a new install starts, the box a copy shows the first time it
starts as a version it has not reported before and the record that keeps it a once-only box, and the
message a Host sends the clients of its chains when it comes up along with what a client does when it
reads one.

Recipe (AI Readme section 20): the `.pyw` is copied to a throwaway `.py` in this folder's `copy/` and
imported, and the windows are driven directly against a stand-in for the main window they are opened
from. Anything replaced goes through harness_seam.py; nothing is written into the entry point by hand.

Three things are stood in for, each because the suite's own rules say so rather than because the
program is awkward:

  - QMessageBox and the startup-registry lookups. A modal box blocks, and the registry is the real
    Windows startup entry. Both are replaced through the seam for the length of the check that needs
    them and restored straight afterwards, so a handler that asks for confirmation is still asked,
    and still answers, without a box opening or the machine being changed.
  - `SyncManagerDialog._check_firewall_rule`, which binds an ephemeral port on every interface and
    sends a probe packet, and `get_local_ip` / `get_current_wifi_ssid`, which read the machine's own
    network. This suite keeps probe_sync's rule - no LAN address bound, no probe packet - so the
    firewall probe is stubbed on a subclass of the real dialog and the two network reads are patched.
  - `TrayProgressPopup.show` and `.move`, which place a real bubble in the corner of the real screen.
    Its labels are checked; the bubble itself is not put on the desktop.

Everything written lands in fixture folders under `copy/windows_fixture/`, rebuilt at the start of
the run and deleted at the end: sync-chain config files, the tracks the rename window is given.
"""
import ast
import importlib.util
import json
import os
import shutil
import sys
import threading
import time

from pathlib import Path

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QLabel, QLineEdit,
                               QPushButton, QSlider, QSplitter, QWidget)
from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QCloseEvent

HERE = os.path.dirname(os.path.abspath(__file__))              # .../GUI Source Code/GUI Test Suite
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")    # the master copy, one folder up
SRC_DIR = os.path.dirname(SRC)       # GUI Source Code, which now also holds the yt_msd package
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)      # the copy below imports that package, so it must be reachable
COPY_DIR = os.path.join(HERE, "copy")
os.makedirs(COPY_DIR, exist_ok=True)
TMP_PY = os.path.join(COPY_DIR, "yt_msd_windows_under_test.py")
shutil.copyfile(SRC, TMP_PY)
_spec = importlib.util.spec_from_file_location("yt_msd_windows_under_test", TMP_PY)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

# Everything this suite replaces goes through the seam, never by writing into the entry
# point. Writing there lands on a re-exported copy that nothing calls once a name has
# moved into yt_msd.*, and the check then passes while testing nothing.
import harness_seam as seam

seam.install(mod, SRC_DIR)

# The shape a code has belongs to the layer that checks a code against, and the entry point does not
# re-export it, so this is the one place this suite names a package name directly. The four host
# functions are the host's own restore and push registries: a check about a code on a host's screen is
# worth running against the thing that hands out codes rather than against a hand-written copy of one.
from yt_msd.sync.lan import RESTORE_CODE_LENGTH
from yt_msd.sync.host import cancel_push_offer as _close_push_offer
from yt_msd.sync.host import cancel_restore_offer as _close_restore_offer
from yt_msd.sync.host import issue_push_code as _issue_push_offer
from yt_msd.sync.host import issue_restore_code as _issue_restore_offer

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


# ---------------------------------------------------------------------------
# Fixtures: everything this suite writes lives here, and goes away at the end
# ---------------------------------------------------------------------------
FIXTURE_ROOT = Path(COPY_DIR) / "windows_fixture"
shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)


def fixture(name):
    """A folder under the fixture root, always fresh."""
    folder = FIXTURE_ROOT / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def audio_file(folder, name, body=b"\xff\xfb\x90\x64 fake track"):
    """A file with an audio suffix. Its contents are bytes rather than real audio, so
    the windows that read tags out of them find none - which is the case they have to
    survive by guessing from the name."""
    folder.mkdir(parents=True, exist_ok=True)
    path = Path(folder) / name
    path.write_bytes(body)
    return path


# ---------------------------------------------------------------------------
# The stand-ins these windows talk to
# ---------------------------------------------------------------------------
class AppStandIn(QWidget):
    """A stand-in for the main window each of these windows is opened from.

    It holds the settings a window reads when it is built, and it records every call a window
    makes back onto it, so a check can say where a change landed: on the app, on the tuning
    seam, on the config file, or nowhere.
    """

    def __init__(self, **overrides):
        super().__init__(None)
        self.calls = []
        self.appearance_mode = "Dark"
        self.accent_color_name = "Blue"
        self.normalization_mode = "ask"
        self.use_custom_args = False
        self.custom_args = ""
        self.minimize_to_tray = False
        self.save_place = False
        self.download_threads = 3
        self.local_rescan_interval = 60
        self.auto_rename = False
        self.silence_pad_dur = 2.0
        self.normalization_threads = 2
        self.silence_trim = True
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.run_custom_script = False
        self.custom_script_path = ""
        self.ytdlp_version = "2025.10.1"
        self.disable_ytdlp_updates = False
        self.recent_playlists = []
        self.local_current_path = ""
        self.sync_config_manager = None
        self.sync_threads = {}
        self.sync_host_server = None
        self.sync_progress_state = {}
        self.active_removable_drives = {}
        self.mount_state = {}
        self.chain_track_counts = {}
        self.last_wifi_ssid = "yt-msd test network"
        self._runtime_state_lock = threading.Lock()
        for key, value in overrides.items():
            setattr(self, key, value)

    def _note(self, name):
        self.calls.append(name)

    def called(self, name):
        return self.calls.count(name)

    def apply_theme(self):
        self._note("apply_theme")

    def save_config(self):
        self._note("save_config")

    def _update_local_rescan_timer(self):
        self._note("_update_local_rescan_timer")

    def _update_sync_timer(self):
        self._note("_update_sync_timer")

    def update_yt_dlp_now(self):
        self._note("update_yt_dlp_now")

    def refresh_yt_dlp_version(self):
        self._note("refresh_yt_dlp_version")

    def open_import_dialog(self):
        self._note("open_import_dialog")

    def open_sync_manager(self, parent_dialog=None):
        self._note("open_sync_manager")

    def refresh_sync_watchers(self):
        self._note("refresh_sync_watchers")

    def reset_to_defaults(self):
        self._note("reset_to_defaults")

    def _auto_sync_removable_chain(self, rc):
        self._note("_auto_sync_removable_chain")


class _Answers:
    """Stands in for QMessageBox while a check drives a handler that would otherwise block.

    The handler still asks, and still gets an answer either way, so the branch that waits for a
    confirmation is exercised. It is patched through the seam for the length of the call below and
    restored straight afterwards.
    """
    answer_yes = True
    asked = []
    warned = []
    told = []
    Yes = 1
    No = 0
    Critical = 16
    Warning = 14

    @classmethod
    def question(cls, parent, title, text, *args, **kwargs):
        # args and text are kept apart so a check can see which button a box defaults to.
        cls.asked.append((title, text, args))
        return cls.Yes if cls.answer_yes else cls.No

    @classmethod
    def warning(cls, parent, title, text, *args, **kwargs):
        cls.warned.append((title, text))

    @classmethod
    def information(cls, parent, title, text, *args, **kwargs):
        # A notice rather than a question: the window it is on is recorded too, because where a box
        # opens is part of what a notice is supposed to do.
        cls.told.append((parent, title, text))


def answering(answer_yes, drive):
    """Run `drive`, with confirmations answered `answer_yes` and warnings recorded."""
    _Answers.answer_yes = answer_yes
    _Answers.asked.clear()
    _Answers.warned.clear()
    _Answers.told.clear()
    seam.patch("QMessageBox", _Answers)
    try:
        return drive()
    finally:
        seam.restore("QMessageBox")


_QT_APP = QApplication.instance() or QApplication([])


# ===========================================================================
# WN-A: the settings window - where each control writes
# ===========================================================================
# The startup checkbox reads the machine's startup entry, and ticking it writes one. Neither
# happens in this suite: both names are replaced through the seam for the length of this section.
_startup_seen = {"value": True, "written": []}
seam.patch("is_run_on_startup_enabled", lambda: _startup_seen["value"])
seam.patch("set_run_on_startup", lambda enabled: _startup_seen["written"].append(enabled))

_settings_app = AppStandIn()
_w = mod.SettingsDialog(_settings_app)

check("WN-A1 the settings window builds against the window that opened it, and holds it under a name that is not Qt's parent()",
      _w.main_app is _settings_app and callable(_w.parent))
check("WN-A2 appearance offers System, Light and Dark, and the one this app is on is the one ticked",
      set(_w.mode_btns) == {"System", "Light", "Dark"}
      and _w.mode_btns["Dark"].isChecked() and not _w.mode_btns["Light"].isChecked())
check("WN-A3 the accent chips are the named colours plus the one taken from Windows",
      set(_w.accent_btns) == {"System"} | set(mod.THEME_COLORS), sorted(_w.accent_btns))
check("WN-A4 normalisation offers ON, OFF and ASK, and the app's own mode is the one ticked",
      set(_w.norm_btns) == {"on", "off", "ask"} and _w.norm_btns["ask"].isChecked())
check("WN-A5 the startup box starts at what the machine says, without reading the registry itself",
      _w.startup_cb.isChecked() is True)

_w._change_mode("Light")
check("WN-A6 changing the appearance writes it into the app and asks the app to re-theme and to remember it",
      _settings_app.appearance_mode == "Light" and _settings_app.called("apply_theme") == 1
      and _settings_app.called("save_config") == 1, _settings_app.calls)

_w._change_accent("Green")
check("WN-A7 choosing an accent does the same, and the name - not a colour - is what is stored",
      _settings_app.accent_color_name == "Green" and _settings_app.called("apply_theme") == 2
      and _settings_app.called("save_config") == 2, _settings_app.calls)

_saves = _settings_app.calls.count("save_config")
_w._update_dl_threads("5")
check("WN-A8 parallel download threads: a number lands, and a word is refused without saving anything",
      _settings_app.download_threads == 5 and _settings_app.calls.count("save_config") == _saves + 1,
      (_settings_app.download_threads, _settings_app.calls.count("save_config")))
_w._update_dl_threads("several")
check("WN-A8b a word in the threads box changes nothing and saves nothing",
      _settings_app.download_threads == 5 and _settings_app.calls.count("save_config") == _saves + 1,
      (_settings_app.download_threads, _settings_app.calls.count("save_config")))

_TUNE_BEFORE = (mod.TUNING.silence_pad_dur, mod.TUNING.silence_trim, mod.TUNING.custom_norm_cmd)
_w._update_silence_pad("3.5")
check("WN-A9 the silence pad reaches both the app and the tuning the audio is built with - the seam, not a copy of it",
      _settings_app.silence_pad_dur == 3.5 and mod.TUNING.silence_pad_dur == 3.5
      and _settings_app.calls.count("save_config") == _saves + 2,
      (_settings_app.silence_pad_dur, mod.TUNING.silence_pad_dur))
_w._update_silence_pad("-4")
_w._update_silence_pad("soon")
check("WN-A10 a negative pad and a word in its box change nothing, on either side",
      _settings_app.silence_pad_dur == 3.5 and mod.TUNING.silence_pad_dur == 3.5
      and _settings_app.calls.count("save_config") == _saves + 2,
      (_settings_app.silence_pad_dur, mod.TUNING.silence_pad_dur))

_w._toggle_silence_trim(False)
check("WN-A11 turning silence trimming off turns it off for the app and for the filter chain that reads it",
      _settings_app.silence_trim is False and mod.TUNING.silence_trim is False,
      (_settings_app.silence_trim, mod.TUNING.silence_trim))

_w._update_norm_cmd("loudnorm=I=-7:TP=-2:LRA=9")
check("WN-A12 an override that is not ticked is remembered but never reaches the audio",
      _settings_app.custom_norm_cmd == "loudnorm=I=-7:TP=-2:LRA=9" and mod.TUNING.custom_norm_cmd == "",
      mod.TUNING.custom_norm_cmd)
_settings_app.use_custom_norm_cmd = True
_w._toggle_norm_cmd(True)
_w._update_norm_cmd("loudnorm=I=-7:TP=-2:LRA=9,equalizer=f=100:g=-3")
check("WN-A13 ticked, the same box writes straight into the filter chain the normalizer builds from",
      mod.TUNING.custom_norm_cmd.endswith("equalizer=f=100:g=-3")
      and _w.norm_cmd_edit.isEnabled(), mod.TUNING.custom_norm_cmd)
_w._toggle_norm_cmd(False)
check("WN-A14 unticking it takes the override out of the chain while leaving the text the user typed",
      mod.TUNING.custom_norm_cmd == ""
      and _settings_app.custom_norm_cmd.endswith("equalizer=f=100:g=-3"), mod.TUNING.custom_norm_cmd)


_idx15 = _w.rescan_combo.findData(15)
_w._update_rescan_interval(_idx15)
check("WN-A15 the rescan interval lands on the app, re-arms the app's own timer and is saved",
      _settings_app.local_rescan_interval == 15 and _settings_app.called("_update_local_rescan_timer") == 1
      and _settings_app.called("save_config") > 0, _settings_app.calls)

_w._update_norm_threads(7)
_w._set_norm_mode("off")
check("WN-A16 the normalisation mode is stored, its button row re-ticked, and the app asked to remember it",
      _settings_app.normalization_mode == "off" and _w.norm_btns["off"].isChecked()
      and not _w.norm_btns["ask"].isChecked() and _settings_app.normalization_threads == 7,
      _settings_app.normalization_mode)

_w._toggle_startup(True)
check("WN-A17 ticking startup goes through the startup helper rather than touching the registry from here",
      _startup_seen["written"] == [True], _startup_seen["written"])

_w._toggle_custom_script(True)
_w._update_custom_script("  C:\\Tools\\after.bat  ")
check("WN-A18 the custom script box gates whether it runs; the path is kept either way, without the padding",
      _settings_app.run_custom_script is True and _settings_app.custom_script_path == r"C:\Tools\after.bat",
      _settings_app.custom_script_path)

_no_version_app = AppStandIn(ytdlp_version="")
_w2 = mod.SettingsDialog(_no_version_app)
check("WN-A19 a settings window that does not yet know the yt-dlp version asks the app to go and find it",
      _no_version_app.called("refresh_yt_dlp_version") == 1
      and "checking" in _w2.ytdlp_version_lbl.text(), (_no_version_app.calls, _w2.ytdlp_version_lbl.text()))
_w2._update_yt_dlp()
check("WN-A20 the update button asks the app to run the upgrade rather than running it from here",
      _no_version_app.called("update_yt_dlp_now") == 1, _no_version_app.calls)

_w2._open_import_package()
_w2._open_sync_manager()
check("WN-A21 import and sync-manager buttons hand the job back to the app that owns them",
      _no_version_app.called("open_import_dialog") == 1
      and _no_version_app.called("open_sync_manager") == 1, _no_version_app.calls)
check("WN-A22 export and reset are offered from settings, because what they act on is what settings holds",
      _w2.export_btn.text() == "Export..." and _w2.reset_btn.text() == "Reset to Default Config")

_reset_app = AppStandIn()
_reset_w = mod.SettingsDialog(_reset_app)
answering(False, lambda: _reset_w._reset_defaults())
check("WN-A23 resetting asks first, and answering no resets nothing",
      _reset_app.calls == [] and _Answers.asked and "Confirm Reset" in _Answers.asked[0][0],
      (_reset_app.calls, _Answers.asked))
answering(True, lambda: _reset_w._reset_defaults())
check("WN-A24 answering yes hands the reset to the app, and the warning it answered says what is wiped",
      _reset_app.called("reset_to_defaults") == 1
      and "every setting" in _Answers.asked[0][1].lower()
      and "music files are not touched" in _Answers.asked[0][1].lower(), _Answers.asked)

seam.restore("is_run_on_startup_enabled")
seam.restore("set_run_on_startup")
mod.TUNING.silence_pad_dur, mod.TUNING.silence_trim, mod.TUNING.custom_norm_cmd = _TUNE_BEFORE
check("WN-A25 this section left the tuning seam as it found it",
      (mod.TUNING.silence_pad_dur, mod.TUNING.silence_trim, mod.TUNING.custom_norm_cmd) == _TUNE_BEFORE,
      (mod.TUNING.silence_pad_dur, mod.TUNING.silence_trim, mod.TUNING.custom_norm_cmd))



# ===========================================================================
# WN-B: the windows that build a chain
# ===========================================================================
CHAINS_CFG = fixture("chains")
HOST_FOLDER = fixture("hosted folder")
audio_file(HOST_FOLDER, "one.mp3")
audio_file(HOST_FOLDER, "two.mp3")
audio_file(HOST_FOLDER, "notes.txt")
CLIENT_BASE = fixture("client base")

CM = mod.SyncConfigManager(str(CHAINS_CFG))
_host_dlg = mod.CreateHostChainDialog(None, CM)

check("WN-B1 a new host chain is offered a sync code that is already four digits",
      _host_dlg.code_edit.text().isdigit() and len(_host_dlg.code_edit.text()) == 4,
      _host_dlg.code_edit.text())
_host_dlg._update_file_count(str(HOST_FOLDER))
check("WN-B2 typing a real folder counts the audio in it and says so, ignoring the subfolders and the notes",
      "2 audio files detected" in _host_dlg.count_lbl.text(), _host_dlg.count_lbl.text())
_host_dlg._update_file_count(str(Path(CHAINS_CFG) / "no such folder"))
check("WN-B3 a folder that is not there is said so rather than counted as empty",
      "does not exist" in _host_dlg.count_lbl.text(), _host_dlg.count_lbl.text())

answering(True, lambda: _host_dlg._create_chain())
check("WN-B4 a chain with no name is refused, and nothing is written",
      _Answers.warned and _Answers.warned[0][0] == "Missing Name" and not CM.hosted_chains,
      (_Answers.warned, CM.hosted_chains))
_host_dlg.name_edit.setText("Rock Classics")
_host_dlg.folder_edit.setText(str(HOST_FOLDER))
_host_dlg._update_file_count(str(HOST_FOLDER))
_host_dlg.code_edit.setText("12")
answering(True, lambda: _host_dlg._create_chain())
check("WN-B5 a sync code that is not four digits is refused with the reason",
      _Answers.warned and _Answers.warned[-1][0] == "Invalid Code" and not CM.hosted_chains,
      (_Answers.warned, CM.hosted_chains))
_first_code = _host_dlg.code_edit.text()
_host_dlg.code_edit.setText("4821")
_host_dlg.delay_spin.setValue(9)
answering(True, lambda: _host_dlg._create_chain())
check("WN-B6 a valid chain is created, carried to the config manager, and closes the window",
      len(CM.hosted_chains) == 1 and CM.hosted_chains[0]["name"] == "Rock Classics"
      and CM.hosted_chains[0]["sync_code"] == "4821"
      and CM.hosted_chains[0]["notify_delay_mins"] == 9 and _host_dlg.result() == 1,
      CM.hosted_chains)
_read_back = mod.SyncConfigManager(str(CHAINS_CFG))
check("WN-B7 the chain outlives the window that made it: a fresh reader of the same config finds it",
      len(_read_back.hosted_chains) == 1 and _read_back.hosted_chains[0]["sync_code"] == "4821",
      _read_back.hosted_chains)
_another_dlg = mod.CreateHostChainDialog(None, CM)
check("WN-B8 the next chain is offered a different code, so two chains cannot answer to one number",
      _another_dlg.code_edit.text() != _first_code and len(_another_dlg.code_edit.text()) == 4,
      (_first_code, _another_dlg.code_edit.text()))

_client_dlg = mod.ConnectClientChainDialog(None, CM)
_client_dlg.ip_edit.setText("")
_client_dlg.code_edit.setText("4821")
answering(True, lambda: _client_dlg._connect_chain())
check("WN-B9 joining a chain without a host address is refused before anything is attempted",
      _Answers.warned and _Answers.warned[-1][0] == "Missing IP" and not CM.client_chains,
      (_Answers.warned, CM.client_chains))
_client_dlg.ip_edit.setText("192.168.1.50")
_client_dlg.code_edit.setText("48210")
answering(True, lambda: _client_dlg._connect_chain())
check("WN-B10 a host address is not enough: the code still has to be the four digits it promises",
      _Answers.warned[-1][0] == "Invalid Code" and not CM.client_chains, _Answers.warned)
_client_dlg.code_edit.setText("4821")
_client_dlg.folder_edit.setText(str(Path(CHAINS_CFG) / "gone"))
_client_dlg.playlist_name_edit.setText("Mix")
answering(True, lambda: _client_dlg._connect_chain())
check("WN-B11 the folder it would sync into has to exist, because the chain is about to write into it",
      _Answers.warned[-1][0] == "Invalid Folder" and not CM.client_chains, _Answers.warned)
_client_dlg.folder_edit.setText(str(CLIENT_BASE))
_client_dlg.playlist_name_edit.setText("")
answering(True, lambda: _client_dlg._connect_chain())
check("WN-B12 and the chain has to have a name, which is also the subfolder it keeps inside the base",
      _Answers.warned[-1][0] == "Missing Name" and not CM.client_chains, _Answers.warned)
_client_dlg.playlist_name_edit.setText("Mix")
_client_dlg.del_mode_combo.setCurrentIndex(1)
check("WN-B13 the two modes offered are mirror and additive, and the box carries the one chosen",
      [_client_dlg.del_mode_combo.itemData(i) for i in range(2)] == ["mirror", "additive"]
      and _client_dlg.del_mode_combo.currentData() == "additive",
      [_client_dlg.del_mode_combo.itemData(i) for i in range(2)])
answering(True, lambda: _client_dlg._connect_chain())
check("WN-B14 a joined chain is stored as base folder plus subfolder, with the host and the mode it will sync by",
      len(CM.client_chains) == 1
      and CM.client_chains[0]["folder_path"] == str(Path(CLIENT_BASE) / "Mix")
      and CM.client_chains[0]["last_known_host_ip"] == "192.168.1.50"
      and CM.client_chains[0]["deletion_mode"] == "additive" and _client_dlg.result() == 1,
      CM.client_chains)
check("WN-B15 it also asks how many files this chain may delete unheard - and offers no number for the mode that never deletes",
      _client_dlg.delete_limit_spin.value() == mod.DEFAULT_DELETE_CONFIRM_LIMIT
      and _client_dlg.delete_limit_spin.minimum() == 0
      and _client_dlg.delete_limit_spin.maximum() == mod.DELETE_CONFIRM_LIMIT_MAX
      and not _client_dlg.delete_limit_row.isVisibleTo(_client_dlg),
      (_client_dlg.delete_limit_spin.value(), _client_dlg.delete_limit_row.isVisibleTo(_client_dlg)))
_client_dlg.del_mode_combo.setCurrentIndex(0)
check("WN-B16 and it offers that number again the moment Mirror is chosen, because Mirror is the mode that deletes",
      _client_dlg.delete_limit_row.isVisibleTo(_client_dlg)
      and _client_dlg.delete_limit_spin.isEnabled(),
      (_client_dlg.delete_limit_row.isVisibleTo(_client_dlg), _client_dlg.delete_limit_spin.isEnabled()))
_GUARD_DLG = mod.ConnectClientChainDialog(None, CM)
_GUARD_DLG.ip_edit.setText("192.0.2.44")
_GUARD_DLG.code_edit.setText("5810")
_GUARD_DLG.folder_edit.setText(str(CLIENT_BASE))
_GUARD_DLG.playlist_name_edit.setText("Guarded")
_GUARD_DLG.delete_limit_spin.setValue(4)
answering(True, lambda: _GUARD_DLG._connect_chain())
check("WN-B17 the number typed into that box is the number the chain is saved with",
      CM.client_chains[-1]["delete_confirm_limit"] == 4, CM.client_chains[-1])

_vis_dlg = mod.CreateHostChainDialog(None, CM)
check("WN-B18 a hosted chain being made is asked whether it tells the network it exists, and Visible is what it is offered",
      _vis_dlg.visible_check.isChecked() and _vis_dlg.visible_check.text().startswith("Visible"),
      (_vis_dlg.visible_check.text(), _vis_dlg.visible_check.isChecked()))
_vis_dlg.name_edit.setText("Study Mix")
_vis_dlg.folder_edit.setText(str(HOST_FOLDER))
_vis_dlg._update_file_count(str(HOST_FOLDER))
_vis_dlg.visible_check.setChecked(False)
answering(True, lambda: _vis_dlg._create_chain())
check("WN-B19 and unchecking it saves a chain that says, in the config file, that it is private",
      CM.hosted_chains[-1]["name"] == "Study Mix" and CM.hosted_chains[-1]["visible"] is False
      and mod.SyncConfigManager(str(CHAINS_CFG)).hosted_chains[-1]["visible"] is False,
      CM.hosted_chains[-1])
check("WN-B20 a chain made without touching that box is saved as visible, which is what every chain this program made before it existed already was",
      mod.SyncConfigManager(str(CHAINS_CFG)).hosted_chains[0]["visible"] is True,
      mod.SyncConfigManager(str(CHAINS_CFG)).hosted_chains)

# ===========================================================================
# WN-C: the window that runs the chains
# ===========================================================================
class QuietSyncDialog(mod.SyncManagerDialog):
    """The real sync-manager window with its opening firewall probe replaced by a note.

    Opening that window normally binds an ephemeral port on every interface and sends a probe
    packet to see whether Windows will allow it. This suite keeps probe_sync's rule - no LAN
    address bound, no probe packet put on the network - so the probe is stubbed here, and the
    first check below confirms the window really does reach for it every time it opens.
    """

    def __init__(self, parent_app):
        self.firewall_probe_asked = False
        super().__init__(parent_app)

    def _check_firewall_rule(self):
        self.firewall_probe_asked = True


def _chain_cards(dlg):
    """The cards the manager has built, found by the chain each one is tagged with."""
    found = []
    for i in range(dlg.cards_layout.count()):
        item = dlg.cards_layout.itemAt(i)
        if item and item.widget() and item.widget().property("chain_id") is not None:
            found.append(item.widget())
    return found


def _card_for(dlg, chain_id):
    for card in _chain_cards(dlg):
        if card.property("chain_id") == chain_id:
            return card
    return None


def _texts(widget):
    return [label.text() for label in widget.findChildren(QLabel)]


SYNC_CFG = fixture("sync manager config")
SYNC_CM = mod.SyncConfigManager(str(SYNC_CFG))
HOST_CHAIN = SYNC_CM.add_hosted_chain("Hosted Mix", str(HOST_FOLDER), "4821", notify_delay_mins=5)
CLIENT_CHAIN = SYNC_CM.add_client_chain(name="Client Mix",
                                        folder_path=str(Path(CLIENT_BASE) / "Mix"),
                                        sync_code="7788", host_ip="192.168.1.50",
                                        deletion_mode="mirror")
_sync_app = AppStandIn(sync_config_manager=SYNC_CM,
                       chain_track_counts={HOST_CHAIN["id"]: 3})

seam.patch("get_local_ip", lambda: "192.0.2.7")
seam.patch("get_current_wifi_ssid", lambda: "patched network")

_dlg = QuietSyncDialog(_sync_app)
check("WN-C1 opening the manager reaches for the firewall rule every time, through the program's own probe",
      _dlg.firewall_probe_asked and callable(mod.SyncManagerDialog._check_firewall_rule))
check("WN-C2 it shows the machine the address its own network reads, not a guess",
      "192.0.2.7" in _dlg.ip_badge.text(), _dlg.ip_badge.text())
check("WN-C3 one card per chain, each tagged with the chain it belongs to",
      len(_chain_cards(_dlg)) == 2 and _card_for(_dlg, HOST_CHAIN["id"]) is not None
      and _card_for(_dlg, CLIENT_CHAIN["id"]) is not None,
      [card.property("chain_id") for card in _chain_cards(_dlg)])
check("WN-C4 the host card names the code a client would type and the folder being shared, with the track count the app already counted",
      any("4821" in text for text in _texts(_card_for(_dlg, HOST_CHAIN["id"])))
      and any(str(HOST_FOLDER) in text for text in _texts(_card_for(_dlg, HOST_CHAIN["id"])))
      and any("(3 tracks)" in text for text in _texts(_card_for(_dlg, HOST_CHAIN["id"]))),
      _texts(_card_for(_dlg, HOST_CHAIN["id"])))
check("WN-C5 the client card says it has never synced and names the mode it will sync in",
      any("Never" in text for text in _texts(_card_for(_dlg, CLIENT_CHAIN["id"])))
      and any("Mirror" in text for text in _texts(_card_for(_dlg, CLIENT_CHAIN["id"]))),
      _texts(_card_for(_dlg, CLIENT_CHAIN["id"])))

_dlg._update_interval(15)
_saved_settings = mod.SyncConfigManager(str(SYNC_CFG)).settings
check("WN-C6 the auto-sync interval is written to the config file and the app is asked to re-arm its own timer",
      _saved_settings.get("auto_sync_interval_mins") == 15
      and _sync_app.called("_update_sync_timer") == 1, (_saved_settings, _sync_app.calls))

_before_cards = _card_for(_dlg, HOST_CHAIN["id"])
_dlg.refresh_cards()
check("WN-C7 a refresh that found nothing changed keeps the cards it already built rather than tearing them down",
      _card_for(_dlg, HOST_CHAIN["id"]) is _before_cards)
_dlg.refresh_cards(force=True)
check("WN-C8 and a forced refresh does rebuild them, because a forced refresh means something did change",
      _card_for(_dlg, HOST_CHAIN["id"]) is not _before_cards)

def _button_texts(card):
    return [btn.text() for btn in card.findChildren(QPushButton)]


_client_card = _card_for(_dlg, CLIENT_CHAIN["id"])
check("WN-C9 a chain that is syncing normally offers to be paused",
      any(text.startswith("Pause Sync") for text in _button_texts(_client_card)), _button_texts(_client_card))

_dlg._pause_chain_sync(CLIENT_CHAIN["id"], -1)
_stored_client = mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0]
check("WN-C10 pausing it until it is re-enabled flips the card to Resume and stores the pause where a later reader finds it",
      any(text == "Resume Sync" for text in _button_texts(_card_for(_dlg, CLIENT_CHAIN["id"])))
      and mod.is_client_chain_paused(_stored_client)[0]
      and any("Paused Forever" in text for text in _texts(_card_for(_dlg, CLIENT_CHAIN["id"]))),
      (_button_texts(_card_for(_dlg, CLIENT_CHAIN["id"])), _stored_client.get("paused_until")))

_dlg._resume_chain_sync(CLIENT_CHAIN["id"])
_stored_client = mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0]
check("WN-C11 resuming takes the pause away on the card and in the file, not only on the card",
      any(text.startswith("Pause Sync") for text in _button_texts(_card_for(_dlg, CLIENT_CHAIN["id"])))
      and not mod.is_client_chain_paused(_stored_client)[0],
      (_button_texts(_card_for(_dlg, CLIENT_CHAIN["id"])), _stored_client.get("paused_until")))

_dlg._bind_chain_wifi(CLIENT_CHAIN["id"], "Cafe Network")
check("WN-C12 binding a chain to a wireless network is stored and shown on its card, so it only auto-syncs there",
      mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0].get("wifi_ssid") == "Cafe Network"
      and any("Wi-Fi: Cafe Network" in text for text in _texts(_card_for(_dlg, CLIENT_CHAIN["id"]))),
      (mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0].get("wifi_ssid"),
       _texts(_card_for(_dlg, CLIENT_CHAIN["id"]))))
_dlg._bind_chain_wifi(CLIENT_CHAIN["id"], "")
check("WN-C13 unbinding it clears the binding instead of leaving the old network behind",
      mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0].get("wifi_ssid", "") == "",
      mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0].get("wifi_ssid"))

answering(False, lambda: _dlg._delete_chain(HOST_CHAIN["id"]))
check("WN-C14 removing a chain asks first, and answering no keeps the chain and says nothing about the audio",
      HOST_CHAIN["id"] in [c["id"] for c in mod.SyncConfigManager(str(SYNC_CFG)).hosted_chains]
      and "Confirm Removal" in _Answers.asked[-1][0] and "untouched" in _Answers.asked[-1][1],
      (_Answers.asked, CM.hosted_chains))
answering(True, lambda: _dlg._delete_chain(HOST_CHAIN["id"]))
check("WN-C15 answering yes takes it out of the config, tells the app to re-arm its watchers, and rebuilds the cards without it",
      HOST_CHAIN["id"] not in [c["id"] for c in mod.SyncConfigManager(str(SYNC_CFG)).hosted_chains]
      and _sync_app.called("refresh_sync_watchers") == 1
      and _card_for(_dlg, HOST_CHAIN["id"]) is None
      and _card_for(_dlg, CLIENT_CHAIN["id"]) is not None,
      [card.property("chain_id") for card in _chain_cards(_dlg)])

FORCE_CFG = fixture("force sync config")
FORCE_CM = mod.SyncConfigManager(str(FORCE_CFG))
FORCE_CM.add_hosted_chain("Hosted Only", str(HOST_FOLDER), "2468")
PLUGGED = str(fixture("drive")) + os.sep + "Mix"
PULLED = str(Path("Z:\\pulled-out"))
_force_app = AppStandIn(sync_config_manager=FORCE_CM,
                        active_removable_drives={
                            PLUGGED: {"id": "rem-1", "name": "Drive Mix", "folder_path": PLUGGED,
                                      "status": ""},
                            PULLED: {"id": "rem-2", "name": "Gone", "folder_path": PULLED,
                                     "status": ""},
                        },
                        mount_state={PLUGGED: True, PULLED: False},
                        sync_host_server=None)
_lan_notifications = []
seam.patch("send_lan_update_notification", lambda *a, **k: _lan_notifications.append(a))
_force_dlg = QuietSyncDialog(_force_app)
_force_dlg._force_sync_all()
check("WN-C16 Force Sync All pushes the drives the app says are plugged in and leaves the one it says were pulled out",
      _force_app.called("_auto_sync_removable_chain") == 1, _force_app.calls)
check("WN-C17 and with no host server running it puts nothing on the network, however many hosted chains there are",
      _lan_notifications == [], _lan_notifications)
seam.restore("send_lan_update_notification")

EMPTY_CFG = fixture("no chains")
_empty_app = AppStandIn(sync_config_manager=mod.SyncConfigManager(str(EMPTY_CFG)))
_empty_dlg = QuietSyncDialog(_empty_app)
check("WN-C18 with nothing configured the manager says what would have to happen next instead of showing an empty pane",
      any("No active Sync Chains" in text for text in _texts(_empty_dlg.cards_container)),
      _texts(_empty_dlg.cards_container))
_empty_dlg.accept()
check("WN-C19 closing the manager hands the window back rather than destroying it, because the threads it started have to outlive the close",
      _empty_dlg.parent() is _empty_app and not _empty_dlg.isVisible(),
      (_empty_dlg.parent(), _empty_dlg.isVisible()))

seam.restore("get_local_ip")
seam.restore("get_current_wifi_ssid")
check("WN-C20 the network reads this section stood in for are back with the program",
      not seam.is_patched("get_local_ip") and not seam.is_patched("get_current_wifi_ssid")
      and "yt_msd.sync.lan" in seam.owned_by("get_local_ip"),
      (seam.owned_by("get_local_ip"), seam.owned_by("get_current_wifi_ssid")))

_GUARD_CARD = _card_for(_dlg, CLIENT_CHAIN["id"])
_GUARD_SPIN = _GUARD_CARD.property("delete_limit_spin")
check("WN-C21 a Mirror chain's card carries the number of files it may delete before it asks, starting at the default and allowing 0",
      _GUARD_SPIN is not None and _GUARD_SPIN.value() == mod.DEFAULT_DELETE_CONFIRM_LIMIT
      and _GUARD_SPIN.minimum() == 0 and _GUARD_SPIN.maximum() == mod.DELETE_CONFIRM_LIMIT_MAX
      and "files" in _GUARD_SPIN.suffix(), _GUARD_SPIN)
_before_guard_card = _GUARD_CARD
_dlg._update_delete_limit(CLIENT_CHAIN["id"], 4)
check("WN-C22 changing it lands on the chain and in the config file, so the next sync reads the number it was given",
      CLIENT_CHAIN["delete_confirm_limit"] == 4
      and mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0].get("delete_confirm_limit") == 4,
      mod.SyncConfigManager(str(SYNC_CFG)).client_chains[0])
check("WN-C23 and it does not rebuild the card it was changed on - the box being typed into is part of that card",
      _card_for(_dlg, CLIENT_CHAIN["id"]) is _before_guard_card)
SYNC_CM.add_client_chain(name="Additive Mix", folder_path=str(Path(CLIENT_BASE) / "Additive"),
                         sync_code="6161", host_ip="192.0.2.61", deletion_mode="additive")
_dlg.refresh_cards(force=True)
_additive_card = _card_for(_dlg, "cc_6161")
check("WN-C24 an Additive chain's card carries no such box at all, while the Mirror chain beside it still does",
      _additive_card is not None and _additive_card.property("delete_limit_spin") is None
      and _card_for(_dlg, CLIENT_CHAIN["id"]).property("delete_limit_spin") is not None,
      (_additive_card.property("delete_limit_spin") if _additive_card else "no card",
       _card_for(_dlg, CLIENT_CHAIN["id"]).property("delete_limit_spin")))
_OLD_CFG = fixture("chain saved without a limit")
(_OLD_CFG / "gui_config.json").write_text(json.dumps({"client_chains": [
    {"id": "cc_3141", "sync_code": "3141", "name": "Old Mix", "folder_path": str(CLIENT_BASE),
     "last_known_host_ip": "192.0.2.9", "host_port": 63350, "deletion_mode": "mirror",
     "paused_until": 0, "wifi_ssid": "", "created_at": 0, "last_synced": 0,
     "status": "Pending Sync"}]}), encoding="utf-8")
_OLD_DLG = QuietSyncDialog(AppStandIn(sync_config_manager=mod.SyncConfigManager(str(_OLD_CFG))))
_OLD_SPIN = _card_for(_OLD_DLG, "cc_3141").property("delete_limit_spin")
check("WN-C25 a chain saved by a build that had no such number gets the box anyway, set to the default it never carried",
      _OLD_SPIN is not None and _OLD_SPIN.value() == mod.DEFAULT_DELETE_CONFIRM_LIMIT, _OLD_SPIN)
_OLD_DLG.accept()

_VIS_CFG = fixture("hosted visibility")
_VIS_CM = mod.SyncConfigManager(str(_VIS_CFG))
_OPEN_CHAIN = _VIS_CM.add_hosted_chain("Open Mix", str(HOST_FOLDER), "4510")
_SHUT_CHAIN = _VIS_CM.add_hosted_chain("Study Mix", str(HOST_FOLDER), "4511", visible=False)
seam.patch("get_local_ip", lambda: "192.0.2.11")
seam.patch("get_current_wifi_ssid", lambda: "patched network")
_vis_app = AppStandIn(sync_config_manager=_VIS_CM)
_VIS_DLG = QuietSyncDialog(_vis_app)


def _visibility_badge(card):
    """The one widget on a hosted card that answers "can a search find this chain".

    It answers by being pressable: the word on the card and the control that changes the answer are
    the same QPushButton, so there is nothing to press that is not the state itself. None is returned
    when the card does not carry exactly one such widget, which is part of what the checks below are
    about - a label with a button beside it would be two widgets, and both words together would be one
    card answering the question twice.
    """
    found = [btn for btn in card.findChildren(QPushButton) if btn.text() in ("Visible", "Private")]
    return found[0] if len(found) == 1 else None


_open_card = _card_for(_VIS_DLG, _OPEN_CHAIN["id"])
_shut_card = _card_for(_VIS_DLG, _SHUT_CHAIN["id"])
_open_badge = _visibility_badge(_open_card)
_shut_badge = _visibility_badge(_shut_card)
check("WN-C26 a hosted chain's card answers whether a search can find it, and that answer is the thing you press",
      _open_badge is not None and _open_badge.text() == "Visible"
      and _shut_badge is not None and _shut_badge.text() == "Private"
      and not any(text.startswith("Make ") for text in _button_texts(_open_card))
      and not any(text.startswith("Make ") for text in _button_texts(_shut_card)),
      (_button_texts(_open_card), _button_texts(_shut_card)))
check("WN-C27 the badge says in its own tooltip what pressing it would do, and the card says the same underneath",
      _open_badge is not None and "Click to make it private" in _open_badge.toolTip()
      and "Click the green badge above" in " ".join(_texts(_open_card))
      and "Click the badge above" in " ".join(_texts(_shut_card)),
      (_open_badge.toolTip() if _open_badge else "no badge", _texts(_open_card), _texts(_shut_card)))
_open_badge.click()
check("WN-C28 pressing the Visible badge writes the decision into the chain and rebuilds the card so its badge reads Private",
      mod.SyncConfigManager(str(_VIS_CFG)).hosted_chains[0]["visible"] is False
      and _visibility_badge(_card_for(_VIS_DLG, _OPEN_CHAIN["id"])) is not None
      and _visibility_badge(_card_for(_VIS_DLG, _OPEN_CHAIN["id"])).text() == "Private",
      mod.SyncConfigManager(str(_VIS_CFG)).hosted_chains)
check("WN-C29 and it asks nobody to re-arm the watchers while doing it, because a host answers a search by re-reading its chains",
      _vis_app.called("refresh_sync_watchers") == 0, _vis_app.calls)
_shut_badge = _visibility_badge(_card_for(_VIS_DLG, _SHUT_CHAIN["id"]))
_shut_badge.click()
check("WN-C30 and the other way round works too, so a chain is not committed to the first answer given it",
      mod.SyncConfigManager(str(_VIS_CFG)).hosted_chains[1]["visible"] is True
      and _visibility_badge(_card_for(_VIS_DLG, _SHUT_CHAIN["id"])).text() == "Visible",
      mod.SyncConfigManager(str(_VIS_CFG)).hosted_chains)
_after_badge = _visibility_badge(_card_for(_VIS_DLG, _OPEN_CHAIN["id"]))
check("WN-C31 the badge is reachable by Tab, is named for a screen reader, and is never the window's default button - so a stray Enter cannot shut a chain and Space pressed on it can",
      _after_badge is not None and bool(int(_after_badge.focusPolicy()) & int(Qt.TabFocus))
      and _after_badge.autoDefault() is False and _after_badge.isDefault() is False
      and bool(_after_badge.accessibleName()),
      (int(_after_badge.focusPolicy()) if _after_badge else "no badge",
       _after_badge.accessibleName() if _after_badge else "",
       _after_badge.autoDefault() if _after_badge else ""))
_VIS_DLG.accept()
_LEGACY_CFG = fixture("hosted chain saved before visibility")
(_LEGACY_CFG / "gui_config.json").write_text(json.dumps({"hosted_chains": [
    {"id": "hc_2580", "sync_code": "2580", "name": "Made by 3.2", "folder_path": str(HOST_FOLDER),
     "notify_delay_mins": 5, "created_at": 0, "last_synced": 0, "status": "Active"}]}), encoding="utf-8")
_legacy_dlg = QuietSyncDialog(AppStandIn(sync_config_manager=mod.SyncConfigManager(str(_LEGACY_CFG))))
check("WN-C32 a hosted chain saved by a build that had no such choice shows as Visible, because visible is what it already was",
      _visibility_badge(_card_for(_legacy_dlg, "hc_2580")) is not None
      and _visibility_badge(_card_for(_legacy_dlg, "hc_2580")).text() == "Visible",
      _button_texts(_card_for(_legacy_dlg, "hc_2580")))
_legacy_dlg.accept()
seam.restore("get_local_ip")
seam.restore("get_current_wifi_ssid")

# ===========================================================================
# WN-D: the smaller windows
# ===========================================================================
_playlist_app = AppStandIn(recent_playlists=[{"name": "Morning Mix", "url": "https://example/morning"},
                                             "https://example/older"])
_pl = mod.PlaylistDialog(_playlist_app)
check("WN-D1 the playlist window offers the history the app keeps, by name where a name was kept",
      [_pl.url_cb.itemText(i) for i in range(_pl.url_cb.count())]
      == ["Morning Mix", "https://example/older"],
      [_pl.url_cb.itemText(i) for i in range(_pl.url_cb.count())])
check("WN-D2 it can still be typed into, because the playlist worth opening is often one never used before",
      _pl.url_cb.isEditable())
_pl_alone = mod.PlaylistDialog()
check("WN-D3 it builds without an app to ask, so the picker is usable on its own",
      _pl_alone.url_cb.count() == 0)


class QuietTrayPopup(mod.TrayProgressPopup):
    """The tray bubble with its bubble kept off the desktop.

    Showing it normally moves it to the bottom-right corner of the real screen and puts it there.
    The labels are what this suite is about, so the placement and the showing are recorded here
    instead of performed on the user's screen.
    """

    def __init__(self, parent=None):
        self.show_requested = False
        self.moved_to = None
        super().__init__(parent)

    def show(self):
        self.show_requested = True

    def move(self, *args):
        self.moved_to = args


_tray = QuietTrayPopup()
_tray.show_track_info("Daft Punk - Around the World", "1:12 / 3:45")
check("WN-D4 the bubble names the track and how far into it the player is",
      _tray.title_lbl.text() == "Daft Punk - Around the World"
      and _tray.progress_lbl.text() == "1:12 / 3:45",
      (_tray.title_lbl.text(), _tray.progress_lbl.text()))
_tray.show_track_info("Daft Punk - Around the World", "0:00 / 0:00")
check("WN-D5 a track that has not started is not reported as being at zero - it says Playing",
      _tray.progress_lbl.text() == "Playing", _tray.progress_lbl.text())
_tray.show_track_info("", "")
check("WN-D6 with nothing loaded it says so instead of leaving the last track on screen",
      _tray.title_lbl.text() == "No track currently playing" and _tray.progress_lbl.text() == "",
      (_tray.title_lbl.text(), _tray.progress_lbl.text()))
check("WN-D7 it asks to be placed and shown, and arranges to hide itself a few seconds later rather than sitting over the tray",
      _tray.show_requested and _tray.moved_to is not None
      and _tray.hide_timer.isActive() and _tray.hide_timer.interval() == 3500,
      (_tray.show_requested, _tray.moved_to, _tray.hide_timer.isActive()))
for _btn in _tray.findChildren(QPushButton):
    _btn.click()
_tray.hide_timer.stop()
check("WN-D8 its own close button dismisses it", _tray.isHidden(), _tray.isHidden())



# ===========================================================================
# WN-D (continued): the three update windows
# ===========================================================================
_avail = mod.UpdateAvailableDialog(None, "3.6", "v3.6", mod.APP_VERSION)
check("WN-D9 a copy started from its source file is offered the source file, not a setup program",
      _avail.packaged is False and _avail.wanted_asset == mod.SOURCE_ASSET,
      (_avail.packaged, _avail.wanted_asset))
check("WN-D10 when the release carries nothing it can take, it says so instead of offering a button that would fail",
      any("This release has no" in text for text in _texts(_avail)), _texts(_avail))
_avail2 = mod.UpdateAvailableDialog(None, "3.6", "v3.6", mod.APP_VERSION, "yt-msd-setup.exe")
check("WN-D11 when there is something to take, it names the file and says what it will do to this folder",
      any("Download: yt-msd-setup.exe" in text for text in _texts(_avail2))
      and any("source file is downloaded over" in text for text in _texts(_avail2)),
      _texts(_avail2))
check("WN-D12 a release with a title beyond its tag is named with it, so the window can say what it is offering",
      any("Release: v3.6" in text for text in _texts(_avail2)), _texts(_avail2))
_avail2.never_cb.setChecked(True)
_avail2._on_ignore()
check("WN-D13 ignoring an update still carries the never-notify answer back, and closes the window unaccepted",
      _avail2.never_notify is True and _avail2.result() == 0, (_avail2.never_notify, _avail2.result()))
_avail3 = mod.UpdateAvailableDialog(None, "3.6", "3.6", mod.APP_VERSION, "yt-msd.pyw")
_avail3._on_download()
check("WN-D14 downloading one closes it accepted, which is how the app knows to start the download",
      _avail3.result() == 1, _avail3.result())
check("WN-D14b a release named only by its tag is not named twice on the window",
      not any("Release: " in text for text in _texts(_avail3)), _texts(_avail3))

_swap = mod.UpdateReadyDialog(None, r"C:\yt-msd-new.pyw", r"C:\yt-msd.pyw", "3.6")
_installer = mod.UpdateReadyDialog(None, r"C:\yt-msd-setup.exe", r"C:\yt-msd.pyw", "3.6",
                                  mod.UPDATE_MODE_INSTALLER)
_replace = mod.UpdateReadyDialog(None, r"C:\yt-msd.pyw", r"C:\yt-msd.pyw", "3.6",
                                mod.UPDATE_MODE_REPLACE)
check("WN-D15 an update that is a setup program is described as replacing the folder, so this file is not what gets removed",
      any("replaces the whole yt-msd folder" in text for text in _texts(_installer))
      and not any("Old version file that would be removed" in text for text in _texts(_installer)),
      _texts(_installer))
check("WN-D16 an update written over the file being run is described as already there, needing only a restart",
      any("downloaded over the yt-msd file you are running" in text for text in _texts(_replace)),
      _texts(_replace))
check("WN-D17 only the swap offers to delete the old file, and it names that file before asking",
      any("Old version file that would be removed: C:\\yt-msd.pyw" in text for text in _texts(_swap))
      and _swap.mode == mod.UPDATE_MODE_SWAP, _texts(_swap))

_ytdlp = mod.YtDlpUpdateDialog(None, "2025.01.01", "2025.11.12")
check("WN-D18 the yt-dlp window names both the installed version and the newest one, and offers the system package manager rather than a bundled copy",
      any("Installed: 2025.01.01" in text for text in _texts(_ytdlp))
      and any("Newest: 2025.11.12" in text for text in _texts(_ytdlp))
      and any("winget" in btn.toolTip() for btn in _ytdlp.findChildren(QPushButton)),
      _texts(_ytdlp))
_ytdlp.never_cb.setChecked(True)
_ytdlp._on_update()
check("WN-D19 accepting it closes the window accepted, carrying the never-notify answer with it",
      _ytdlp.never_notify is True and _ytdlp.result() == 1, (_ytdlp.never_notify, _ytdlp.result()))

# ===========================================================================
# WN-E: the rename-from-metadata window
# ===========================================================================
RENAME_DIR = fixture("rename")
TRACKS = [
    audio_file(RENAME_DIR, "01 around the world.mp3"),
    audio_file(RENAME_DIR, "unknown artist.mp3"),
    audio_file(RENAME_DIR, "notes.txt"),
]
_rename_dlg = mod.MetadataRenameDialog(AppStandIn(), [str(p) for p in TRACKS])

check("WN-E1 one row per file chosen, and the file that is not audio is still offered rather than quietly dropped",
      len(_rename_dlg.rows) == 3 and [row["path"] for row in _rename_dlg.rows]
      == [str(p) for p in TRACKS], [row["path"] for row in _rename_dlg.rows])
check("WN-E2 a file with no tags to read still gets a guess taken from its own name, so the window is never blank",
      _rename_dlg.rows[0]["artist_edit"].text() or _rename_dlg.rows[0]["title_edit"].text(),
      (_rename_dlg.rows[0]["artist_edit"].text(), _rename_dlg.rows[0]["title_edit"].text()))

_rename_dlg.rows[0]["artist_edit"].setText("Daft Punk")
_rename_dlg.rows[0]["title_edit"].setText("Around the World")
check("WN-E3 the new name is previewed from the two boxes as they are typed into, keeping the file's own extension",
      "Daft Punk - Around the World.mp3" in _rename_dlg.rows[0]["new_lbl"].toolTip(),
      _rename_dlg.rows[0]["new_lbl"].toolTip())
_rename_dlg.rows[0]["artist_edit"].setText("Daft   Punk")
check("WN-E4 the preview keeps up with each box separately, and shortens what it shows without shortening what it would write",
      "Around the World" in _rename_dlg.rows[0]["new_lbl"].toolTip()
      and _rename_dlg.rows[0]["new_lbl"].text().startswith("Daft")
      and len(_rename_dlg.rows[0]["new_lbl"].text()) <= len(_rename_dlg.rows[0]["new_lbl"].toolTip()),
      (_rename_dlg.rows[0]["new_lbl"].text(), _rename_dlg.rows[0]["new_lbl"].toolTip()))

_rename_dlg.rows[1]["artist_edit"].setText("")
_rename_dlg.rows[1]["title_edit"].setText("Only A Title")
check("WN-E5 one of the two boxes empty still produces a name, because half a title is better than nothing",
      _rename_dlg._new_stem_for(_rename_dlg.rows[1]) == "Only A Title",
      _rename_dlg._new_stem_for(_rename_dlg.rows[1]))
_rename_dlg.rows[2]["artist_edit"].setText("")
_rename_dlg.rows[2]["title_edit"].setText("")
# The name column is 164 px wide whatever the display is doing, so on a large Windows scaling
# setting - or on Qt's offscreen plugin - the sentence this window shows is elided. The whole
# sentence is on the tooltip, which is what WN-E4 established the window keeps.
check("WN-E6 both boxes empty says so on the window instead of proposing an empty file name",
      _rename_dlg.rows[2]["new_lbl"].text().startswith("(enter an a")
      and "(enter an artist or a title)" in _rename_dlg.rows[2]["new_lbl"].toolTip(),
      (_rename_dlg.rows[2]["new_lbl"].text(), _rename_dlg.rows[2]["new_lbl"].toolTip()))
_rename_dlg.rows[2]["artist_edit"].setText("Bad: /name*?")
check("WN-E7 a name Windows cannot hold is made into one it can before it is offered",
      all(bad not in _rename_dlg._new_stem_for(_rename_dlg.rows[2]) for bad in ':/?*'),
      _rename_dlg._new_stem_for(_rename_dlg.rows[2]))
# Both boxes on this row are cleared again before the rename is applied, so the window
# is left with one row that has nothing to name its file from.
_rename_dlg.rows[2]["artist_edit"].setText("")

_still_there = []
for row in _rename_dlg.rows:
    p = Path(row["path"])
    if p.exists():
        _still_there.append(p.name)
check("WN-E8 building the window and previewing names touches no file - a rename window that renames on its own would be worse than the names it fixes",
      sorted(_still_there) == sorted(p.name for p in TRACKS), _still_there)

_rename_dlg.write_tags_cb.setChecked(False)
answering(True, lambda: _rename_dlg._apply_renames())
_renamed = sorted(p.name for p in RENAME_DIR.iterdir())
check("WN-E9 renaming lands the files on disk under the names the window previewed, with each row reporting what it did",
      "Daft Punk - Around the World.mp3" in _renamed and _rename_dlg.result() == 1
      and all(row_status["status"] in ("renamed", "skipped", "conflict", "unchanged", "failed", "missing")
              for row_status in _rename_dlg.results),
      (_renamed, _rename_dlg.results))
check("WN-E10 the row that had nothing in either box was skipped, and says why, rather than becoming a file with no name",
      any(row_status["status"] == "skipped" and "both empty" in row_status["message"]
          for row_status in _rename_dlg.results), _rename_dlg.results)
check("WN-E11 every rename reported names the file it started from, so a user can find it again",
      all(Path(row_status["old"]).parent == RENAME_DIR for row_status in _rename_dlg.results),
      _rename_dlg.results)


# ===========================================================================
# WN-G: the promises made to the machine - which file Windows is told to start, which yt-dlp is looked for
# ===========================================================================
# Both of these ask something of the machine the program is running on, so both are driven against
# a recorder rather than against this machine: `winreg` is replaced with `partial_module`, which
# keeps every name of the real `winreg` except the five calls below, so the real HKCU startup entry
# is neither read nor changed while the program's own startup code is being read.
_REAL_WINREG = seam.original("winreg")
_REGISTRY_OPENS = []
_REGISTRY_WRITES = []
_REGISTRY_DELETES = []
_REGISTRY_QUERIES = []
_STANDBY_KEY = object()


def _standin_open_key(root, path, reserved=0, access=0):
    _REGISTRY_OPENS.append((path, access))
    return _STANDBY_KEY


def _standin_query_value(key, name):
    _REGISTRY_QUERIES.append(name)
    raise FileNotFoundError  # this stand-in machine has nothing registered under that name


def _standin_set_value(key, name, reserved, value_type, value):
    _REGISTRY_WRITES.append((name, value_type, value))


def _standin_delete_value(key, name):
    _REGISTRY_DELETES.append(name)


def _standin_close_key(key):
    return None


_REGISTRY_STAND_IN = seam.partial_module(
    _REAL_WINREG,
    OpenKey=_standin_open_key, QueryValueEx=_standin_query_value, SetValueEx=_standin_set_value,
    DeleteValue=_standin_delete_value, CloseKey=_standin_close_key)

_started_from = os.path.dirname(os.path.abspath(__file__))
_startup_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

seam.patch("winreg", _REGISTRY_STAND_IN)
try:
    _enabled_when_nothing_registered = mod.is_run_on_startup_enabled()
    _startup_written = mod.set_run_on_startup(True)
    _startup_command = _REGISTRY_WRITES[-1][2] if _REGISTRY_WRITES else ""
    _startup_tokens = [token for token in _startup_command.split('"') if token.strip()]
    check("WN-G1 with nothing registered, the settings window reads the startup entry as off rather than failing",
          _enabled_when_nothing_registered is False and _REGISTRY_QUERIES == ["yt-msd"],
          (_enabled_when_nothing_registered, _REGISTRY_QUERIES))
    check("WN-G2 turning startup on writes the value Windows itself looks at, under the Run key and named yt-msd",
          _startup_written is True and _REGISTRY_WRITES and _REGISTRY_WRITES[-1][0] == "yt-msd"
          and _REGISTRY_WRITES[-1][1] == _REAL_WINREG.REG_SZ
          and _startup_key_path in [path_opened for path_opened, _access in _REGISTRY_OPENS],
          (_REGISTRY_OPENS, _REGISTRY_WRITES))
    check("WN-G3 and the command it writes starts the program itself, in a windowed python, not the module that asked",
          len(_startup_tokens) == 2
          and os.path.basename(_startup_tokens[0]).lower().startswith("pythonw")
          and os.path.isfile(_startup_tokens[0])
          and _startup_tokens[1] == os.path.abspath(__file__)
          and "startup.py" not in _startup_command,
          (_startup_command, os.path.abspath(__file__)))
    _startup_off = mod.set_run_on_startup(False)
    check("WN-G4 turning it off removes that value rather than writing a different one over it",
          _startup_off is True and _REGISTRY_DELETES == ["yt-msd"], (_startup_off, _REGISTRY_DELETES))

    _lookup_candidates = mod._yt_dlp_lookup_paths()
    _lookup_home = os.path.dirname(os.path.abspath(mod._yt_dlp_lookup_paths.__code__.co_filename))
    check("WN-G5 a yt-dlp.exe placed beside the program is one of the places the program looks - in the folder the program sits in, not the folder the looking code lives in",
          os.path.join(_started_from, "yt-dlp.exe") in _lookup_candidates
          and not any(os.path.dirname(candidate) == _lookup_home for candidate in _lookup_candidates),
          (_lookup_candidates, _lookup_home))
    check("WN-G6 the winget copy is still the first place it looks, because that is the copy it can keep up to date",
          _lookup_candidates and "WinGet" in _lookup_candidates[0] and _lookup_candidates[0].endswith("yt-dlp.exe"),
          _lookup_candidates[:2])
finally:
    seam.restore("winreg")

check("WN-G7 the real winreg is back, so nothing after this point is reading a recorder instead of the machine",
      seam.read("winreg") is _REAL_WINREG and not seam.is_patched("winreg"), seam.read("winreg"))
_start_answers = {name: seam.owners(name) for name in ("program_folder", "program_file")}
check("WN-G8 every module that asks which file or folder the program was started from asks the same one function, and the entry point keeps no copy of its own",
      all(len(_holders) >= 2 and len({getattr(_m, _name) for _m in _holders}) == 1 and mod not in _holders
          for _name, _holders in _start_answers.items()),
      {_name: seam.owned_by(_name) for _name in _start_answers})

_package_files = sorted(Path(SRC_DIR).joinpath("yt_msd").rglob("*.py"))
_own_file_reads = {}
for _package_file in _package_files:
    _tree = ast.parse(_package_file.read_text(encoding="utf-8"), filename=str(_package_file))
    _found = [node.lineno for node in ast.walk(_tree)
              if isinstance(node, ast.Name) and node.id == "__file__"]
    if _found:
        _own_file_reads[str(_package_file.relative_to(SRC_DIR))] = _found
check("WN-G9 no module under yt_msd reads its own __file__ for a location - since the split that names a module inside the package, and every promise made to the machine is about the file the program was started as",
      _own_file_reads == {}, _own_file_reads)

# ===========================================================================
# WN-F: the seam - a replacement lands where these windows read it
# ===========================================================================
_owner_pairs = {
    "SettingsDialog": ("get_accent_color", "set_run_on_startup"),
    "SyncManagerDialog": ("is_client_chain_paused", "get_local_ip"),
    "MetadataRenameDialog": ("read_metadata_tags", "write_metadata_tags"),
}
for _dialog_name, _helper_names in _owner_pairs.items():
    _dialog_modules = seam.owners(_dialog_name)
    _real = [m for m in _dialog_modules if m.__name__ != mod.__name__]
    _home = _real[0].__name__ if _real else mod.__name__
    check(f"WN-F1 {_dialog_name} is defined in exactly one module ({_home}) and the entry point's copy is that same object, not a second definition",
          len(_real) <= 1
          and all(getattr(_m, _dialog_name) is getattr(_dialog_modules[0], _dialog_name)
                  for _m in _dialog_modules),
          seam.owned_by(_dialog_name))
    check(f"WN-F1b {seam.owned_by(_dialog_name)} - every helper {_dialog_name} calls is held by a module other than the entry point too, so the seam reaches the copy its callers actually use and the window never depends on a name that only the .pyw has",
          all(any(_o != mod.__name__ for _o in seam.owned_by(_helper))
              for _helper in _helper_names),
          {_helper: seam.owned_by(_helper) for _helper in _helper_names})

_patched_settings = AppStandIn()
seam.patch("get_accent_color", lambda name: "#123456")
_patched_view = mod.SettingsDialog(_patched_settings)
check("WN-F2 the settings window paints its own mode buttons with the colour helper the program actually calls, not with a copy the harness left standing",
      any("#123456" in btn.styleSheet() for btn in _patched_view.mode_btns.values()),
      {name: btn.styleSheet() for name, btn in _patched_view.mode_btns.items()})
seam.restore("get_accent_color")
check("WN-F3 the helper the program owns is back afterwards, so the next window is painted normally",
      seam.read("get_accent_color") is not None
      and not seam.is_patched("get_accent_color")
      and seam.read("get_accent_color")("Blue") != "#123456",
      seam.read("get_accent_color")("Blue"))

seam.patch("is_client_chain_paused", lambda cc: (True, 0))
_SEAM_CFG = mod.SyncConfigManager(str(fixture("seam config")))
_SEAM_CLIENT = _SEAM_CFG.add_client_chain(name="Seam Mix", folder_path=str(CLIENT_BASE),
                                         sync_code="1357", host_ip="192.0.2.9")
_patched_sync_app = AppStandIn(sync_config_manager=_SEAM_CFG)
_patched_sync = QuietSyncDialog(_patched_sync_app)
check("WN-F4 a card decides whether to offer Pause or Resume by asking the program's own pause helper - so when a wave moves both, the patch still reaches the caller",
      any(text == "Resume Sync" for text in _button_texts(_card_for(_patched_sync, _SEAM_CLIENT["id"]))),
      _button_texts(_card_for(_patched_sync, _SEAM_CLIENT["id"])))
seam.restore("is_client_chain_paused")
# The manager keeps the cards it already built when nothing about the chains changed, so
# the card built under the patch is rebuilt here to show what the real helper answers.
_patched_sync.refresh_cards(force=True)
check("WN-F5 the same card, rebuilt by the same code, offers Pause again once the real helper is back",
      any(text.startswith("Pause Sync") for text in _button_texts(_card_for(_patched_sync, _SEAM_CLIENT["id"]))),
      _button_texts(_card_for(_patched_sync, _SEAM_CLIENT["id"])))

try:
    seam.patch("SettingsDialogThatIsNotInTheProgram", lambda: None)
    _refused = False
except seam.SeamError:
    _refused = True
check("WN-F6 a name nothing in the program owns is refused out loud instead of quietly doing nothing",
      _refused)

_self_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
_stray_writes = [f"line {node.lineno}" for node in ast.walk(_self_tree)
                 if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))
                 and any(isinstance(target, ast.Attribute)
                         and isinstance(target.value, ast.Name)
                         and target.value.id == "mod"
                         for target in ([node.target] if not isinstance(node, ast.Assign)
                                        else node.targets))]
check("WN-F7 this file writes nothing into the entry point by hand - every replacement goes through the seam",
      _stray_writes == [], _stray_writes)

_still_patched = [name for name in ("is_run_on_startup_enabled", "set_run_on_startup",
                                    "QMessageBox", "get_local_ip", "get_current_wifi_ssid",
                                    "send_lan_update_notification", "get_accent_color",
                                    "is_client_chain_paused", "winreg") if seam.is_patched(name)]
check("WN-F8 nothing this suite patched is left patched for the next suite to run against",
      _still_patched == [], _still_patched)

print("=" * 72)
print("WN-H. what MainApp is assembled from, since wave 6 lifted five of its methods out")

# Wave 6 moved five methods into modules MainApp now inherits. Nothing else in this suite would
# notice if that wiring were wrong: the checks drive MainApp's methods as unbound functions on
# stand-ins, so a shadowed method, a duplicated one or a base in the wrong place would leave every
# one of them green. These ask the wiring question directly, without building a window - MainApp's
# constructor starts VLC, watchers and LAN services, which is more than a class composition needs.
_lifted = {"__init__": "BootstrapMixin", "setup_ui": "LayoutMixin", "apply_theme": "StylesheetMixin",
           "reset_to_defaults": "SettingsResetMixin", "start_batch_download": "BatchDownloadMixin"}
_bases = [c.__name__ for c in mod.MainApp.__mro__]
_present = [o for o in _lifted.values() if o in _bases]
check("WN-H1 MainApp inherits the five modules wave 6 lifted into, with QMainWindow last",
      len(_present) == 5
      and _bases.index("QMainWindow") > max((_bases.index(o) for o in _present), default=-1),
      _bases[:8])
check("WN-H2 every lifted method is still reachable through MainApp, from the mixin it moved to",
      all(getattr(mod.MainApp, name).__qualname__.split(".")[0] == owner
          for name, owner in _lifted.items()),
      {name: getattr(mod.MainApp, name).__qualname__ for name, owner in _lifted.items()})
_redefined = [name for name in _lifted if name in vars(mod.MainApp)]
check("WN-H3 and none of the five is left defined in MainApp on top of the mixin that owns it",
      _redefined == [], _redefined)
_holders = {name: [c.__name__ for c in mod.MainApp.__mro__ if name in vars(c)] for name in _lifted}
check("WN-H4 no lifted name is held by two of the wave-6 mixins, and the constructor resolves to "
      "BootstrapMixin ahead of the Qt one behind it",
      all(len([c for c in where if c in _lifted.values()]) == 1 for where in _holders.values())
      and _holders["__init__"][0] == "BootstrapMixin", _holders)
_signals = {n: type(getattr(mod.MainApp, n)).__name__
            for n in ("status_signal", "search_results_signal", "stream_refreshed_signal")}
check("WN-H5 the signals MainApp wires its worker threads to are still declared on the class itself",
      all("Signal" in t for t in _signals.values()), _signals)

# ===========================================================================
# WN-I: the question a sync asks before it deletes
# ===========================================================================
# `ask_sync_confirm` is the door a sync worker walks through when it has more files to delete than
# its chain allows: it is called on the worker's thread, parks that thread, and the answer is given
# by the GUI-thread slot. The worker half of that is proved in probe_sync (SY-M); what is proved
# here is the gate itself - the park, the answer, the default, and the wording the user is shown.
# Restore Host puts two more questions through that same gate - the delete-or-keep-or-restore choice,
# and the four characters a client has to read off a host's screen - and the windows that carry all
# three answers are checked here too.
class _GateSignal:
    """A signal that answers itself, some time after it is emitted, as a queued one does on the GUI thread."""

    def __init__(self, app, answer_after=0.0, handler="_on_sync_confirm"):
        self.app = app
        self.answer_after = answer_after
        self.handler = handler
        self.emitted = []

    def emit(self, request_id, *args):
        self.emitted.append((request_id,) + tuple(args))
        timer = threading.Timer(self.answer_after,
                                lambda: getattr(self.app, self.handler)(request_id, *args))
        # A daemon, because one of these is deliberately never answered: the check that proves a
        # question nobody answers still finishes must not hold the run open for it.
        timer.daemon = True
        timer.start()


class _GateApp:
    """The gate without the window: every half of it is the program's own method, taken unbound.

    Building a MainApp to reach two methods would need a player, a tray and a config file. What is
    under test is the parking and the answering, so the attributes those methods touch are the
    only ones here.

    All three questions a sync can ask - the Yes/No limit, the delete-or-keep-or-restore choice, and
    the four characters a client reads off a host - share `sync_confirm_waiters` and the lock around
    it in the program, so they share them here. Each of the three signals knows which slot answers it.
    """

    ask_sync_confirm = mod.MainApp.ask_sync_confirm
    _on_sync_confirm = mod.MainApp._on_sync_confirm
    ask_sync_decision = mod.MainApp.ask_sync_decision
    _on_sync_decision = mod.MainApp._on_sync_decision
    ask_restore_code = mod.MainApp.ask_restore_code
    _on_restore_code = mod.MainApp._on_restore_code

    _sync_question_parent = mod.MainApp._sync_question_parent

    def __init__(self, answer_after=0.0):
        self.sync_confirm_waiters = {}
        self._sync_confirm_lock = threading.Lock()
        self._sync_confirm_counter = 0
        self.sync_manager_dialog = None
        self.sync_confirm_signal = _GateSignal(self, answer_after, "_on_sync_confirm")
        self.sync_decision_signal = _GateSignal(self, answer_after, "_on_sync_decision")
        self.restore_code_signal = _GateSignal(self, answer_after, "_on_restore_code")


_gate_yes = _GateApp()
_answer_yes = answering(True, lambda: _gate_yes.ask_sync_confirm(
    "Sync Chain 'Studio' - Delete Files?", "Delete 11 file(s)?"))
check("WN-I1 a worker's question is asked out loud, in the words the worker's chain put on it, and its answer comes back to the worker",
      _answer_yes is True and len(_gate_yes.sync_confirm_signal.emitted) == 1
      and _Answers.asked[0][0] == "Sync Chain 'Studio' - Delete Files?"
      and "Delete 11 file(s)?" in _Answers.asked[0][1], (_answer_yes, _Answers.asked))
check("WN-I2 the box offers exactly Yes and No, and No is the button it defaults to",
      _Answers.asked[0][2] == (_Answers.Yes | _Answers.No, _Answers.No), _Answers.asked[0][2])
check("WN-I3 answering it clears the waiter it was parked on, so a finished question cannot be left waiting",
      _gate_yes.sync_confirm_waiters == {}, _gate_yes.sync_confirm_waiters)

_gate_no = _GateApp()
_answer_no = answering(False, lambda: _gate_no.ask_sync_confirm("Sync Chain 'Studio' - Delete Files?", "Delete 11 file(s)?"))
check("WN-I4 a No is handed back as a No, which is the half that leaves every file where it is",
      _answer_no is False, _answer_no)

_gate_wait = _GateApp(answer_after=0.6)
_gate_started = time.time()
_answer_wait = answering(True, lambda: _gate_wait.ask_sync_confirm("t", "q"))
_gate_waited = time.time() - _gate_started
check("WN-I5 and it really waits: the answer that arrives half a second late is the answer the worker acts on, not the first one to hand",
      _answer_wait is True and _gate_waited >= 0.5, _gate_waited)

seam.patch("SYNC_CONFIRM_WAIT_LIMIT", 0.5)
_gate_stalled = _GateApp(answer_after=30.0)
_answer_stalled = answering(True, lambda: _gate_stalled.ask_sync_confirm("t", "q"))
seam.restore("SYNC_CONFIRM_WAIT_LIMIT")
check("WN-I6 a question nobody answers is a No, and the wait is bounded, so a sync cannot be held open by a box nobody read",
      _answer_stalled is False and _gate_stalled.sync_confirm_waiters == {}, _answer_stalled)

# The two windows Restore Host adds are stood in for while the gate that carries them is exercised -
# `exec()` blocks, and a check that drives a gate must not wait on a window. Each stand-in records the
# words it was built with and closes with the answer the check hands it, which is all the gate ever
# reads back out of the real window.
class _DecisionBoxStandIn:
    """The delete-or-keep-or-restore window, without a window on the screen."""
    built = []
    hands_back = mod.SYNC_DECISION_RESTORE

    def __init__(self, parent, title, question):
        type(self).built.append((parent, title, question))

    def exec(self):
        return 0

    @property
    def decision(self):
        return type(self).hands_back


class _CodeBoxStandIn:
    """The four-characters-a-client-types window, stood in for the same reason."""
    built = []
    hands_back = "K7PZ"

    def __init__(self, parent, title, host_label):
        type(self).built.append((parent, title, host_label))

    def exec(self):
        return 0

    @property
    def code(self):
        return type(self).hands_back


def _ask_on_worker(app, method_name, *args):
    """Ask one of the gate's questions the way a sync worker asks it - on a thread of its own, parked
    on an answer - and hand back whatever the gate finally returns."""
    out = [None]

    def _drive():
        out[0] = getattr(app, method_name)(*args)

    t = threading.Thread(target=_drive)
    t.daemon = True
    t.start()
    t.join(30)
    return out[0]


_stand_in_decision_cb = mod.make_sync_decision_cb(AppStandIn(), "Studio")
_stand_in_code_cb = mod.make_restore_code_cb(AppStandIn(), "Studio")
_gate_cb_app = _GateApp()
_decision_cb = mod.make_sync_decision_cb(_gate_cb_app, "Studio")
_code_cb = mod.make_restore_code_cb(_gate_cb_app, "Studio")
check("WN-I7 the callbacks a Restore Host sync is built with are handed over only by an app that can ask, and are nothing at all to one that cannot",
      _stand_in_decision_cb is None and _stand_in_code_cb is None
      and _decision_cb is not None and _code_cb is not None,
      (_stand_in_decision_cb, _stand_in_code_cb, _decision_cb, _code_cb))
_D_box = _DecisionBoxStandIn
_D_box.built.clear()
_D_box.hands_back = mod.SYNC_DECISION_DELETE
with seam.patched("SyncDeleteDecisionDialog", _D_box):
    _decision_via_cb = _decision_cb("The host has stopped offering 3000 file(s). Delete 3000 file(s)?")
check("WN-I8 and going through that callback is the same gate: the chain's name is on the title the window is opened with, and the answer comes back as the word the worker acts on",
      _decision_via_cb == mod.SYNC_DECISION_DELETE and len(_gate_cb_app.sync_decision_signal.emitted) == 1
      and _D_box.built and _D_box.built[0][1] == "Sync Chain 'Studio' - Delete Files?",
      (_decision_via_cb, _D_box.built))
_C_box = _CodeBoxStandIn
_C_box.built.clear()
_C_box.hands_back = "QD54"
with seam.patched("RestoreHostCodeDialog", _C_box):
    _code_via_cb = _code_cb("192.168.1.5:63351")
check("WN-I8b the code callback is the same gate too: it takes nothing, asks the worker's own question, and hands back the code as it was typed",
      _code_via_cb == "QD54" and _C_box.built and _C_box.built[0][1] == "Sync Chain 'Studio' - Restore Host",
      (_code_via_cb, _C_box.built))
check("WN-I9 the gate is a signal MainApp declares and a pair of methods it owns, so a worker thread has something to reach for",
      "Signal" in type(getattr(mod.MainApp, "sync_confirm_signal")).__name__
      and "ask_sync_confirm" in dir(mod.MainApp) and "_on_sync_confirm" in dir(mod.MainApp),
      type(getattr(mod.MainApp, "sync_confirm_signal")).__name__)
check("WN-I9b Restore Host's two extra questions are gates of the same shape on the same window - a signal each and a slot each - and the host server has a signal to talk back to this screen with",
      all("Signal" in type(getattr(mod.MainApp, _n)).__name__
          for _n in ("sync_decision_signal", "restore_code_signal", "host_restore_signal"))
      and all(_m in dir(mod.MainApp) for _m in ("ask_sync_decision", "_on_sync_decision",
                                                "ask_restore_code", "_on_restore_code",
                                                "_open_host_restore_dialog", "_cancel_host_restore_offer",
                                                "_on_host_restore_event")))


class _OpenManagerStandIn:
    """A Sync Chains window that is open on the screen, without a window on the screen."""

    def isVisible(self):
        return True


class _DeletedManagerStandIn:
    """A Sync Chains window that was deleted underneath a worker: the one parent that must not be used."""

    def isVisible(self):
        raise RuntimeError("wrapped C++ object has already been deleted")


# The delete-or-keep-or-restore answer: asked on the worker's thread, parked, answered from the other.
_D_box.built.clear()
_D_box.hands_back = mod.SYNC_DECISION_RESTORE
_gate_decision = _GateApp(answer_after=0.1)
with seam.patched("SyncDeleteDecisionDialog", _D_box):
    _decision_answer = _ask_on_worker(_gate_decision, "ask_sync_decision",
                                      "Sync Chain 'Studio' - Delete Files?",
                                      "The host has stopped offering 3000 file(s).")
check("WN-I10 the third answer comes back to the parked worker as the word the worker acts on, and the window that gave it was built with the words the chain put on it",
      _decision_answer == mod.SYNC_DECISION_RESTORE
      and len(_gate_decision.sync_decision_signal.emitted) == 1
      and _D_box.built and _D_box.built[0][1] == "Sync Chain 'Studio' - Delete Files?",
      (_decision_answer, _D_box.built))
check("WN-I11 with no Sync Chains window open, the question is raised against the main window itself",
      _D_box.built and _D_box.built[0][0] is _gate_decision, _D_box.built)
_D_box.built.clear()
_gate_decision.sync_manager_dialog = _OpenManagerStandIn()
with seam.patched("SyncDeleteDecisionDialog", _D_box):
    _ask_on_worker(_gate_decision, "ask_sync_decision", "t", "q")
check("WN-I11b with the Sync Chains window open, that is the window the question lands on - it is where anybody watching the sync is looking",
      len(_D_box.built) == 1 and isinstance(_D_box.built[0][0], _OpenManagerStandIn), _D_box.built)
_D_box.built.clear()
_gate_decision.sync_manager_dialog = _DeletedManagerStandIn()
with seam.patched("SyncDeleteDecisionDialog", _D_box):
    _ask_on_worker(_gate_decision, "ask_sync_decision", "t", "q")
check("WN-I11c a window that was deleted underneath the worker is not a parent: the question is still asked, on no parent at all",
      len(_D_box.built) == 1 and _D_box.built[0][0] is None, _D_box.built)
_gate_decision.sync_manager_dialog = None
check("WN-I12 answering it clears the waiter it was parked on, exactly as the Yes/No box does",
      _gate_decision.sync_confirm_waiters == {}, _gate_decision.sync_confirm_waiters)

_D_box.hands_back = mod.SYNC_DECISION_KEEP
_gate_decision_stalled = _GateApp(answer_after=30.0)
with seam.patched("SYNC_CONFIRM_WAIT_LIMIT", 0.5), seam.patched("SyncDeleteDecisionDialog", _D_box):
    _decision_timeout = _ask_on_worker(_gate_decision_stalled, "ask_sync_decision", "t", "q")
check("WN-I13 a decision nobody answers is Keep, and the wait is bounded, so a sync cannot be held open by a window nobody read",
      _decision_timeout == mod.SYNC_DECISION_KEEP
      and _gate_decision_stalled.sync_confirm_waiters == {}, _decision_timeout)

_D_box.hands_back = "delete them please"
_gate_decision_odd = _GateApp(answer_after=0.1)
with seam.patched("SyncDeleteDecisionDialog", _D_box):
    _odd_answer = _ask_on_worker(_gate_decision_odd, "ask_sync_decision", "t", "q")
check("WN-I14 an answer that is not one of the three words this program names an answer with is Keep, never permission to delete",
      _odd_answer == mod.SYNC_DECISION_KEEP, _odd_answer)

_D_box.built.clear()
_D_box.hands_back = mod.SYNC_DECISION_RESTORE
with seam.patched("SyncDeleteDecisionDialog", _D_box):
    _gate_decision._on_sync_decision("sd_no_such_request", "t", "q")
check("WN-I15 a decision window for a request nothing is waiting on is never built, so a late slot call cannot invent an answer",
      _D_box.built == [], _D_box.built)

# The four characters a client reads off a host's screen. They never travel down the connection the
# sync is parked on, so this window is the only road they have - and the host, not this PC, is the one
# that gives up on them.
_C_box.built.clear()
_C_box.hands_back = "K7PZ"
_gate_code = _GateApp(answer_after=0.1)
with seam.patched("RestoreHostCodeDialog", _C_box):
    _typed_code = _ask_on_worker(_gate_code, "ask_restore_code",
                                 "Sync Chain 'Studio' - Restore Host", "192.168.1.5:63351")
check("WN-I16 the code typed on this PC comes back to the worker that is holding the host's connection open, and the machine it is being typed for is written on the window",
      _typed_code == "K7PZ" and len(_gate_code.restore_code_signal.emitted) == 1
      and _C_box.built and _C_box.built[0][2] == "192.168.1.5:63351", (_typed_code, _C_box.built))
check("WN-I17 the request the worker parked on is gone the moment the code arrives, so one code cannot be handed to two syncs",
      _gate_code.sync_confirm_waiters == {}, _gate_code.sync_confirm_waiters)

_C_box.hands_back = None
_gate_code_cancelled = _GateApp(answer_after=0.1)
with seam.patched("RestoreHostCodeDialog", _C_box):
    _no_code = _ask_on_worker(_gate_code_cancelled, "ask_restore_code",
                              "Sync Chain 'Studio' - Restore Host", "192.168.1.5:63351")
check("WN-I18 nobody typing anything is no code at all - None, the answer that closes the host's offer from this end",
      _no_code is None and _gate_code_cancelled.sync_confirm_waiters == {}, _no_code)

_C_box.hands_back = "K7PZ"
_gate_code_stalled = _GateApp(answer_after=30.0)
with seam.patched("SYNC_CONFIRM_WAIT_LIMIT", 0.5), seam.patched("RestoreHostCodeDialog", _C_box):
    _code_timeout = _ask_on_worker(_gate_code_stalled, "ask_restore_code",
                                   "Sync Chain 'Studio' - Restore Host", "192.168.1.5:63351")
check("WN-I18b a code nobody waits for is given up on, on this PC's clock, and the waiter is left empty",
      _code_timeout is None and _gate_code_stalled.sync_confirm_waiters == {}, _code_timeout)

# The three windows themselves, built against a stand-in main window. Not one of them is exec()'d -
# exec() blocks - so each is driven through its own buttons and its own handlers, which is what an
# exec() of a window somebody pressed a button on comes to.
_restore_windows_app = AppStandIn()
_ACCEPTED = int(QDialog.Accepted)

_dec_window = mod.SyncDeleteDecisionDialog(
    _restore_windows_app, "Sync Chain 'Studio' - Delete Files?",
    "The host has stopped offering 3000 file(s) that are in:\n    C:\\Music")
check("WN-I19 the warning the Yes/No box used to carry is still the first thing said, in the host's own words",
      _dec_window.windowTitle() == "Sync Chain 'Studio' - Delete Files?"
      and "stopped offering 3000 file(s)" in _dec_window.question_lbl.text(),
      _dec_window.question_lbl.text())
check("WN-I19b all three answers are on the window, and the one the window opens with is the one that changes nothing",
      (_dec_window.restore_btn.text(), _dec_window.keep_btn.text(), _dec_window.delete_btn.text())
      == ("Restore Host", "Keep Them", "Delete Them")
      and _dec_window.keep_btn.isDefault() and _dec_window.decision == mod.SYNC_DECISION_KEEP,
      (_dec_window.restore_btn.text(), _dec_window.keep_btn.text(),
       _dec_window.delete_btn.text(), _dec_window.decision))
check("WN-I19c the window says what each answer does to this PC before anybody reads it: Delete takes files out of this folder and Restore takes none",
      "Nothing here is deleted" in _dec_window.restore_btn.toolTip()
      and "Delete the files listed above from this folder" in _dec_window.delete_btn.toolTip()
      and "Leave every file exactly where it is" in _dec_window.keep_btn.toolTip(),
      (_dec_window.restore_btn.toolTip(), _dec_window.delete_btn.toolTip()))
_dec_window.restore_btn.click()
check("WN-I20 pressing Restore Host is the answer the worker reads back, and the window closes on it",
      _dec_window.decision == mod.SYNC_DECISION_RESTORE and _dec_window.result() == _ACCEPTED,
      (_dec_window.decision, _dec_window.result()))
_dec_kept = mod.SyncDeleteDecisionDialog(_restore_windows_app, "t", "q")
_dec_kept.keep_btn.click()
check("WN-I20b pressing Keep Them closes the window on the answer that leaves the sync alone",
      _dec_kept.decision == mod.SYNC_DECISION_KEEP and _dec_kept.result() == _ACCEPTED,
      (_dec_kept.decision, _dec_kept.result()))
_dec_closed = mod.SyncDeleteDecisionDialog(_restore_windows_app, "t", "q")
_dec_closed.reject()
check("WN-I20c a window closed by its X, by Escape or by nobody at all is Keep: the safe answer is the one that needs no button pressed",
      _dec_closed.decision == mod.SYNC_DECISION_KEEP and _dec_closed.result() != _ACCEPTED,
      (_dec_closed.decision, _dec_closed.result()))

_code_window = mod.RestoreHostCodeDialog(_restore_windows_app,
                                         "Sync Chain 'Studio' - Restore Host", "192.168.1.5:63351")
check("WN-I21 nothing typed is no code, there is nothing to press until there is one, and the machine being written into is the one named on the window",
      _code_window.code is None and not _code_window.restore_btn.isEnabled()
      and _code_window.code_edit.maxLength() == RESTORE_CODE_LENGTH
      and _code_window.host_label == "192.168.1.5:63351",
      (_code_window.code, _code_window.code_edit.maxLength()))
_code_window.code_edit.setText("k7")
check("WN-I21b what is typed is upper-cased as it is typed - both ends compare a code upper case - and a half code stays unpressable",
      _code_window.code_edit.text() == "K7" and not _code_window.restore_btn.isEnabled()
      and "not the code" in _code_window.hint_lbl.text(),
      (_code_window.code_edit.text(), _code_window.hint_lbl.text()))
_code_window.code_edit.setText("IO01")
check("WN-I21c the four characters this code never uses are refused as a code instead of quietly normalised into one",
      _code_window.code_edit.text() == "IO01" and not _code_window.restore_btn.isEnabled()
      and "no I, O, 0 or 1" in _code_window.hint_lbl.text(), _code_window.hint_lbl.text())
_code_window.code_edit.setText("k7pz")
check("WN-I22 a whole code opens the button, and the window says the host is the one that will check it",
      _code_window.code_edit.text() == "K7PZ" and _code_window.restore_btn.isEnabled()
      and _code_window.hint_lbl.text().startswith("That is a code."),
      (_code_window.restore_btn.isEnabled(), _code_window.hint_lbl.text()))
_code_window.restore_btn.click()
check("WN-I22b the one thing this window hands back is the code, and it hands it back upper-cased",
      _code_window.code == "K7PZ" and _code_window.result() == _ACCEPTED,
      (_code_window.code, _code_window.result()))
_code_half = mod.RestoreHostCodeDialog(_restore_windows_app, "t", "192.168.1.5:63351")
_code_half.code_edit.setText("K7P")
_code_half._accept_code()
check("WN-I23 pressing Restore with a half code is refused rather than sent, and the window stays where it is",
      _code_half.code is None and _code_half.result() != _ACCEPTED,
      (_code_half.code, _code_half.result()))
_code_cancelled = mod.RestoreHostCodeDialog(_restore_windows_app, "t", "192.168.1.5:63351")
_code_cancelled.code_edit.setText("k7pz")
_code_cancelled.cancel_btn.click()
check("WN-I23b Cancel hands back no code even when a whole one was typed - the host is left exactly as it is",
      _code_cancelled.code is None and _code_cancelled.result() != _ACCEPTED,
      (_code_cancelled.code, _code_cancelled.result()))

# The window a Host shows its own code on. It is deliberately not modal - a host that froze its own
# screen while somebody typed four characters on another machine could not cancel the offer it had
# just made either - so it is built here and driven through its own timer and its own buttons.
_restore_cancellations = []


def _note_restore_cancel(sync_code, code):
    """What the server is handed when a code window decides it is finished: which chain, which code."""
    _restore_cancellations.append((str(sync_code), str(code)))


_expiry_window = mod.HostRestoreCodeDialog(_restore_windows_app, "4999", "Studio", "192.168.1.9",
                                           "K7PZ", 2.0, on_cancel=_note_restore_cancel)
check("WN-I24 the host's window names the machine waiting, shows the code a person has to read out to it, and is already counting down",
      _expiry_window.windowTitle() == "Restore Host - Code for Studio"
      and _expiry_window.code_lbl.text() == "K7PZ" and _expiry_window.client_ip == "192.168.1.9"
      and _expiry_window.count_timer.isActive() and "another 2 second" in _expiry_window.count_lbl.text(),
      (_expiry_window.code_lbl.text(), _expiry_window.count_lbl.text()))
check("WN-I24b while a code is open, nothing has been cancelled here and nothing has been written",
      _expiry_window.cancelled is False and _expiry_window.settled_by_program is False
      and _expiry_window.closed_reason == '' and not _restore_cancellations)
for _ in range(3):
    _expiry_window._tick()
check("WN-I25 when the time runs out the code is closed here, the machine waiting on it is told, and the offer is not left open for whoever asks next",
      _expiry_window.cancelled is True and _expiry_window.closed_reason == "its time ran out"
      and _restore_cancellations == [("4999", "K7PZ")] and not _expiry_window.count_timer.isActive()
      and "Restore not carried out - its time ran out" in _expiry_window.count_lbl.text(),
      (_expiry_window.closed_reason, _restore_cancellations, _expiry_window.count_lbl.text()))
check("WN-I25b a code that has closed stops being something a person here can act on: both of its buttons are shut",
      not _expiry_window.cancel_btn.isEnabled() and not _expiry_window.copy_btn.isEnabled())
_expiry_window._close_offer("a Cancel pressed afterwards")
check("WN-I25c and closing is not counted twice: a second Cancel reports nothing a second time",
      _restore_cancellations == [("4999", "K7PZ")], _restore_cancellations)

_restore_cancellations.clear()
_settled_window = mod.HostRestoreCodeDialog(_restore_windows_app, "4999", "Studio", "192.168.1.9",
                                            "QD54", 40.0, on_cancel=_note_restore_cancel)
_settled_window.settled_elsewhere("the code was named and the rebuild has begun")
check("WN-I26 when the rebuild takes the code off the screen the window closes without cancelling anything - the offer was already settled by the side that owns it",
      _settled_window.settled_by_program is True and _settled_window.cancelled is False
      and not _restore_cancellations and not _settled_window.count_timer.isActive(),
      (_settled_window.settled_by_program, _restore_cancellations))
_settled_window._close_offer("a Cancel pressed afterwards")
_settled_window.closeEvent(QCloseEvent())
check("WN-I27 a window the rebuild has already settled cannot report a cancellation over the top of the first one - not by its Cancel button, and not by its own X",
      _restore_cancellations == [] and _settled_window.cancelled is False, _restore_cancellations)

class _RecordingEmit:
    """Records what a signal on the main window would have put on the screen."""

    def __init__(self):
        self.emitted = []

    def emit(self, *args):
        self.emitted.append(args)


class _HostChainManagerStandIn:
    """The hosted chains the main window looks a chain up out of, and the two write-backs a push makes."""

    def __init__(self, hosted, trust_returns=True):
        self.hosted_chains = [dict(chain) for chain in hosted]
        self.trust_returns = trust_returns
        self.trusts = []

    def trust_push_client(self, chain_id, client_ip):
        self.trusts.append((chain_id, str(client_ip)))
        return self.trust_returns


class _HostServerStandIn:
    """The host server as the main window talks to it: which chains are mid-rebuild or mid-push, what
    the last push to each one did, and what a cancel call is answered with."""

    def __init__(self, restoring=(), cancel_returns=True, pushing=(), last_counts=()):
        self.restoring = {str(code) for code in restoring}
        self.pushing = {str(code): str(ip) for code, ip in pushing}
        self.last_counts = {str(code): tuple(counts) for code, counts in last_counts}
        self.cancel_returns = cancel_returns
        self.cancels = []
        self.push_cancels = []
        self.active_port = 63351

    def is_restoring(self, sync_code):
        return str(sync_code) in self.restoring

    def cancel_restore_request(self, sync_code, code=None):
        self.cancels.append((str(sync_code), str(code)))
        return self.cancel_returns

    def is_pushing(self, sync_code):
        return str(sync_code) in self.pushing

    def pushing_from(self, sync_code):
        return self.pushing.get(str(sync_code))

    def last_push_counts(self, sync_code):
        return self.last_counts.get(str(sync_code), (0, 0))

    def cancel_push_request(self, sync_code, code=None):
        self.push_cancels.append((str(sync_code), str(code)))
        return self.cancel_returns


class _HostRestoreApp(AppStandIn):
    """The main window as the receiving end of a Restore Host: a hosted chain, the server behind it,
    the two signals a restore reaches (both recorded), and the receiving half of MainApp's own methods,
    taken unbound - nothing here is a re-implementation of them."""

    _host_chain_for_code = mod.MainApp._host_chain_for_code
    _host_restore_dialog = mod.MainApp._host_restore_dialog
    _settle_host_restore_dialog = mod.MainApp._settle_host_restore_dialog
    _open_host_restore_dialog = mod.MainApp._open_host_restore_dialog
    _cancel_host_restore_offer = mod.MainApp._cancel_host_restore_offer
    _on_host_restore_event = mod.MainApp._on_host_restore_event
    _after_host_restore = mod.MainApp._after_host_restore
    _host_push_dialog = mod.MainApp._host_push_dialog
    _settle_host_push_dialog = mod.MainApp._settle_host_push_dialog
    _open_host_push_dialog = mod.MainApp._open_host_push_dialog
    _cancel_host_push_offer = mod.MainApp._cancel_host_push_offer
    _on_host_push_event = mod.MainApp._on_host_push_event
    _after_host_push = mod.MainApp._after_host_push
    _on_hosted_folder_changed = mod.MainApp._on_hosted_folder_changed
    _sync_question_parent = mod.MainApp._sync_question_parent

    def __init__(self, hosted, restoring=(), cancel_returns=True, current_path="",
                 pushing=(), last_counts=(), trust_returns=True):
        super().__init__(sync_config_manager=_HostChainManagerStandIn(hosted, trust_returns),
                         sync_host_server=_HostServerStandIn(restoring, cancel_returns, pushing,
                                                             last_counts),
                         local_current_path=current_path)
        self.status_signal = _RecordingEmit()
        self.local_list_refresh_signal = _RecordingEmit()
        self._host_restore_dialogs = {}
        self._host_push_dialogs = {}

    def said(self, words):
        return any(words in str(entry[0]) for entry in self.status_signal.emitted)


class _HostCodeWindowStandIn(QDialog):
    """The host's code window without a window on the screen: the same methods and the same registry,
    so a check can see which chains have a code showing and what took it off. `show()` is not the real
    one, because a host's code window stays open for minutes and this suite does not put windows on the
    desktop."""

    def __init__(self, parent_window, sync_code, chain_name, client_ip, code, expires_in, on_cancel=None,
                 purpose='restore'):
        super().__init__(None)
        self.parent_window = parent_window
        self.sync_code = str(sync_code)
        self.chain_name = chain_name
        self.client_ip = client_ip
        self.code = str(code)
        self.expires_in = expires_in
        self.on_cancel_cb = on_cancel
        # Which of the two questions this window is asking. A restore code and a push code are the same
        # window with different words on it, and a check has to be able to tell which one was raised.
        self.purpose = str(purpose)
        self.settled_with = None
        self.shown = 0

    def show(self, *args):
        self.shown += 1
        return True

    def raise_(self):
        pass

    def activateWindow(self):
        pass

    def settled_elsewhere(self, reason):
        self.settled_with = reason


_HOST_RESTORE_FOLDER = str(FIXTURE_ROOT / "host_restore_folder")
_host_restore_app = _HostRestoreApp([{"sync_code": "4999", "name": "Studio",
                                      "folder_path": _HOST_RESTORE_FOLDER}],
                                    current_path=_HOST_RESTORE_FOLDER)
# The host's own restore registry, holding a genuine offer for this chain: the socket thread fills this
# in when a client asks, and the window is built out of it rather than out of what arrived over the wire.
_restore_offer = _issue_restore_offer("4999", "192.168.1.9")

with seam.patched("HostRestoreCodeDialog", _HostCodeWindowStandIn):
    _host_restore_app._on_host_restore_event("4999", "192.168.1.9", "requested", "ZZZZ")
    _showing = _host_restore_app._host_restore_dialogs.get("4999")
    check("WN-I28 a client asking this machine to rebuild itself puts that chain's code on this machine's own screen, under the chain it belongs to",
          _showing is not None and _showing.chain_name == "Studio" and _showing.shown == 1,
          None if _showing is None else (_showing.chain_name, _showing.shown))
    check("WN-I28b the code shown is the one this host's own registry is holding and not the one that arrived over the connection - the window and the offer behind it have to be the same code",
          _showing is not None and _showing.code == _restore_offer['code'] and _showing.code != "ZZZZ"
          and _showing.expires_in > 60.0,
          None if _showing is None else (_showing.code, _restore_offer['code']))
    check("WN-I28c and the person sitting at this machine is told to read it out, in the chain's own name",
          _host_restore_app.said("Sync Chain 'Studio': 192.168.1.9 is asking to rebuild this host")
          and _host_restore_app.said("Read the code on the Restore Host window"),
          _host_restore_app.status_signal.emitted)

    # An offer that is gone by the time somebody gets around to showing it. The socket made it, the
    # window was raised a moment later, and in between it stopped being anything anybody could use.
    _issue_restore_offer("8123", "192.168.1.9", timeout=0.0)
    _host_restore_app.status_signal.emitted.clear()
    _host_restore_app._on_host_restore_event("8123", "192.168.1.9", "requested", "QD54")
    check("WN-I29 an offer that closed between the socket making it and the window raising it shows no code at all, and says so instead of showing a code nothing would accept",
          "8123" not in _host_restore_app._host_restore_dialogs
          and _host_restore_app.said("closed before a code could be shown")
          and _host_restore_app.said("Nothing was changed here"), _host_restore_app.status_signal.emitted)

    _first_showing = _showing
    _newer_offer = _issue_restore_offer("4999", "192.168.1.7")
    _host_restore_app._on_host_restore_event("4999", "192.168.1.7", "requested", _newer_offer['code'])
    check("WN-I30 a newer request for the same chain takes the older window off the screen before the new one goes up, exactly as it took the offer off the host",
          _first_showing.settled_with == "a newer request replaced it"
          and _host_restore_app._host_restore_dialogs["4999"].code == _newer_offer['code']
          and _newer_offer['code'] != _restore_offer['code'],
          (_first_showing.settled_with, _host_restore_app._host_restore_dialogs["4999"].code))

    _host_restore_app.status_signal.emitted.clear()
    _host_restore_app._on_host_restore_event("4999", "192.168.1.7", "started", "")
    check("WN-I31 the moment the code is named the window is off the screen, and the screen says what is about to happen to this host: only what it is missing is written, and nothing here is deleted",
          "4999" not in _host_restore_app._host_restore_dialogs
          and _host_restore_app.said("nothing here is being deleted")
          and _host_restore_app.said("only what this host is missing is being written"),
          _host_restore_app.status_signal.emitted)

    _host_restore_app._on_host_restore_event("4999", "192.168.1.7", "cancelled", "the code was wrong")
    check("WN-I32 a restore that did not happen is said out loud on this machine too, with the reason the host was given, and it says nothing here was changed",
          _host_restore_app.said("restore not carried out (the code was wrong)")
          and _host_restore_app.said("Nothing on this host was changed"),
          _host_restore_app.status_signal.emitted)

    # The offers this section put into the host's real registry are taken back out of it. An offer left
    # open is a code somebody could still be handed, and this suite has no business leaving one behind.
    _close_restore_offer("4999", None)
    check("WN-I32b and nothing is left open in the host's own registry when this section is done",
          mod.pending_restore_request("4999") is None and mod.pending_restore_request("8123") is None,
          (mod.pending_restore_request("4999"), mod.pending_restore_request("8123")))

_host_restore_app.sync_host_server.cancels.clear()
_host_restore_app.status_signal.emitted.clear()
with seam.patched("HostRestoreCodeDialog", _HostCodeWindowStandIn):
    _host_restore_app._cancel_host_restore_offer("4999", "QD54")
check("WN-I33 Cancel on this machine's own window closes the offer behind it, and says what that did to the machine waiting on it",
      _host_restore_app.sync_host_server.cancels == [("4999", "QD54")]
      and _host_restore_app.said("restore code closed here")
      and _host_restore_app.said("nothing on this host was changed"),
      (_host_restore_app.sync_host_server.cancels, _host_restore_app.status_signal.emitted))

_late_cancel_app = _HostRestoreApp([{"sync_code": "8123", "name": "Kitchen",
                                     "folder_path": _HOST_RESTORE_FOLDER}], cancel_returns=False)
_late_cancel_app._cancel_host_restore_offer("8123", "QD54")
check("WN-I33b a Cancel that arrives after that restore was already accepted or closed says so, instead of reporting a cancellation that never happened",
      _late_cancel_app.said("already been accepted or closed"), _late_cancel_app.status_signal.emitted)

_notifications = []
with seam.patched("send_lan_update_notification",
                  lambda code, port: _notifications.append((str(code), int(port)))):
    _host_restore_app.status_signal.emitted.clear()
    _host_restore_app._on_host_restore_event("4999", "192.168.1.7", "finished", "wrote 12 file(s)")
    check("WN-I34 a rebuild that finished is said out loud here, and the rest of the chain is told about a folder that is now whole",
          _host_restore_app.said("Sync Chain (Code 4999) rebuilt from 192.168.1.7: wrote 12 file(s)")
          and _notifications == [("4999", 63351)],
          (_host_restore_app.status_signal.emitted, _notifications))
    check("WN-I34b and the folder list on this machine is asked for again when the folder that was rebuilt is the one being looked at",
          len(_host_restore_app.local_list_refresh_signal.emitted) == 1,
          _host_restore_app.local_list_refresh_signal.emitted)

    _other_view_app = _HostRestoreApp([{"sync_code": "4999", "name": "Studio",
                                        "folder_path": _HOST_RESTORE_FOLDER}],
                                      current_path=str(FIXTURE_ROOT / "a_different_folder"))
    _notifications.clear()
    _other_view_app._after_host_restore("4999")
    check("WN-I34c the other clients are told even when this PC is looking at a different folder - the rebuild is theirs to hear about either way",
          _notifications == [("4999", 63351)]
          and _other_view_app.local_list_refresh_signal.emitted == [],
          (_notifications, _other_view_app.local_list_refresh_signal.emitted))

    _notifications.clear()
    _host_restore_app.sync_host_server.restoring.add("4999")
    _host_restore_app.status_signal.emitted.clear()
    _host_restore_app._on_hosted_folder_changed("4999")
    check("WN-I35 a hosted folder that is mid-rebuild tells the clients nothing, because a Mirror client that synced against a half-built folder would delete its own tracks to match it",
          _notifications == [] and _host_restore_app.status_signal.emitted == [],
          (_notifications, _host_restore_app.status_signal.emitted))
    _host_restore_app.sync_host_server.restoring.remove("4999")
    _host_restore_app._on_hosted_folder_changed("4999")
    check("WN-I35b the same folder once it is whole tells them once - the one notification the rebuild owed, sent once",
          _notifications == [("4999", 63351)]
          and _host_restore_app.said("Notified clients on LAN"),
          (_notifications, _host_restore_app.status_signal.emitted))

class _TrustQuestionStandIn(QDialog):
    """The host's push-permission question without a window on the desktop.

    `asked` records every question this section caused, in the order it was asked, and `answers` is what
    the harness chose for each address before the window was raised. A real window here would block the
    suite on a person who is not there.
    """

    asked = []
    answers = {}

    def __init__(self, parent_window, chain_name, client_ip, what_happened=''):
        super().__init__(None)
        self.parent_window = parent_window
        self.chain_name = chain_name
        self.client_ip = str(client_ip)
        self.what_happened = what_happened
        self.trust = bool(_TrustQuestionStandIn.answers.get(self.client_ip, False))

    def exec(self):
        _TrustQuestionStandIn.asked.append((self.chain_name, self.client_ip, self.what_happened))
        return 0


_HOST_PUSH_FOLDER = str(FIXTURE_ROOT / "host_push_folder")
# An offer genuinely open in the host's own push registry, for the same chain the rebuild section above
# used. The two registries are separate, and this is the check that a code on a push window is the push
# registry's code and not the rebuild one sitting beside it.
_push_offer_open = _issue_push_offer("4999", "192.168.1.7")
_host_push_app = _HostRestoreApp([{"id": "chain-4999", "sync_code": "4999", "name": "Studio",
                                   "folder_path": _HOST_PUSH_FOLDER}],
                                 current_path=_HOST_PUSH_FOLDER,
                                 pushing=[("4999", "192.168.1.7")],
                                 last_counts=[("4999", (3, 1))])

with seam.patched("HostRestoreCodeDialog", _HostCodeWindowStandIn):
    _host_push_app._on_host_push_event("4999", "192.168.1.7", "requested", "ZZZZ")
    _push_window = _host_push_app._host_push_dialog("4999")
    check("WN-I36 a client offering its own new files to this host puts a code on this machine's screen too, under the chain it belongs to, asking the push question rather than the rebuild one",
          _push_window is not None and _push_window.chain_name == "Studio"
          and _push_window.purpose == "push" and _push_window.shown == 1,
          None if _push_window is None else (_push_window.chain_name, _push_window.purpose,
                                             _push_window.shown))
    check("WN-I36b the code on it is the one this host's own push registry is holding, and it is not the code the rebuild offer for the same chain is holding - two windows on one screen must never show the same word",
          _push_window is not None and _push_window.code == _push_offer_open['code']
          and _push_window.code != "ZZZZ" and _push_window.code != _restore_offer['code'],
          None if _push_window is None else (_push_window.code, _push_offer_open['code']))
    check("WN-I36c and a push code window and a rebuild code window are kept apart, because one chain can be asked both at the same moment and each window cancels only the offer it is showing",
          _host_push_app._host_push_dialog("4999") is not None
          and "4999" not in _host_push_app._host_restore_dialogs
          and _host_push_app._host_restore_dialog("4999") is None,
          (list(_host_push_app._host_push_dialogs), list(_host_push_app._host_restore_dialogs)))
    check("WN-I36d the person sitting at this machine is told to read it out, in the chain's own name, and told which window to read it from",
          _host_push_app.said("Sync Chain 'Studio': 192.168.1.7 is asking to push files into this host")
          and _host_push_app.said("Read the code on the Push To Host window"),
          _host_push_app.status_signal.emitted)

    _host_push_app.status_signal.emitted.clear()
    _host_push_app._on_host_push_event("4999", "192.168.1.7", "started", "")
    check("WN-I37 the moment the code is named the window is off the screen, and this machine is told what is about to happen to its folder: files are arriving, and nothing this host already has is touched",
          _host_push_app._host_push_dialog("4999") is None
          and _push_window.settled_with == "the code was named and the files are on their way"
          and _host_push_app.said("is taking files from 192.168.1.7")
          and _host_push_app.said("nothing here is being deleted")
          and _host_push_app.said("only what this host is missing is being written"),
          (_push_window.settled_with, _host_push_app.status_signal.emitted))

    _host_push_app._on_host_push_event("4999", "192.168.1.7", "cancelled", "the code was wrong")
    check("WN-I38 a push that did not happen is said out loud on this machine too, with the reason the host was given, and it says nothing here was changed",
          _host_push_app.said("Sync Chain (Code 4999) push not carried out (the code was wrong)")
          and _host_push_app.said("Nothing on this host was changed"),
          _host_push_app.status_signal.emitted)

    _close_push_offer("4999", None)
    check("WN-I38b and nothing is left open in the host's own push registry when this section is done",
          mod.pending_push_request("4999") is None, mod.pending_push_request("4999"))

_host_push_app.sync_host_server.push_cancels.clear()
_host_push_app.status_signal.emitted.clear()
with seam.patched("HostRestoreCodeDialog", _HostCodeWindowStandIn):
    _host_push_app._cancel_host_push_offer("4999", "QD54")
check("WN-I39 Cancel on this machine's own push window closes the offer behind it, and says what that did to the machine waiting on it",
      _host_push_app.sync_host_server.push_cancels == [("4999", "QD54")]
      and _host_push_app.said("push code closed here")
      and _host_push_app.said("nothing on this host was changed"),
      (_host_push_app.sync_host_server.push_cancels, _host_push_app.status_signal.emitted))

_late_push_cancel_app = _HostRestoreApp([{"id": "chain-8123", "sync_code": "8123", "name": "Kitchen",
                                          "folder_path": _HOST_PUSH_FOLDER}], cancel_returns=False)
_late_push_cancel_app._cancel_host_push_offer("8123", "QD54")
check("WN-I39b a Cancel that arrives after that push was already accepted or closed says so, instead of reporting a cancellation that never happened",
      _late_push_cancel_app.said("already been accepted or closed"), _late_push_cancel_app.status_signal.emitted)

_TrustQuestionStandIn.asked.clear()
_TrustQuestionStandIn.answers = {"192.168.1.7": True}
_notifications.clear()
with seam.patched("send_lan_update_notification",
                  lambda code, port: _notifications.append((str(code), int(port)))), \
     seam.patched("HostPushTrustDialog", _TrustQuestionStandIn):
    _host_push_app.status_signal.emitted.clear()
    _host_push_app._on_host_push_event("4999", "192.168.1.7", "finished", "3 file(s) written")
    check("WN-I40 a push that finished is said out loud here with what it added and what it refused, and the rest of the chain is told about a folder that is bigger now",
          _host_push_app.said("took files from 192.168.1.7: 3 file(s) added, 1 refused")
          and _host_push_app.said("Clients on the LAN have been told.")
          and _notifications == [("4999", 63351)],
          (_host_push_app.status_signal.emitted, _notifications))
    check("WN-I40b and the machine that just wrote into this folder is asked about the next time - by address, with what it did named on the window",
          _TrustQuestionStandIn.asked == [("Studio", "192.168.1.7", "3 file(s) written")],
          _TrustQuestionStandIn.asked)
    check("WN-I40c answering that question the trusting way writes the address against this chain, and says so where the card that takes it back can be pointed at",
          _host_push_app.sync_config_manager.trusts == [("chain-4999", "192.168.1.7")]
          and _host_push_app.said("can push here without a code from now on")
          and _host_push_app.said("Take that back from the card in Sync Chains"),
          (_host_push_app.sync_config_manager.trusts, _host_push_app.status_signal.emitted))

    # The same folder, the same address, and an answer of "one time only" - which is also the answer a
    # window nobody read gives. Nothing is written to the chain, and the next push needs a code again.
    _TrustQuestionStandIn.asked.clear()
    _TrustQuestionStandIn.answers = {}
    _once_app = _HostRestoreApp([{"id": "chain-4999", "sync_code": "4999", "name": "Studio",
                                  "folder_path": _HOST_PUSH_FOLDER}],
                                current_path=_HOST_PUSH_FOLDER,
                                pushing=[("4999", "192.168.1.7")],
                                last_counts=[("4999", (2, 0))])
    _once_app._on_host_push_event("4999", "192.168.1.7", "finished", "2 file(s) written")
    check("WN-I41 answering it the other way writes nothing to the chain and says out loud that the next push needs a code again - the question is asked once per push, not answered forever",
          _once_app.sync_config_manager.trusts == []
          and _TrustQuestionStandIn.asked == [("Studio", "192.168.1.7", "2 file(s) written")]
          and _once_app.said("was allowed to push once")
          and _once_app.said("Its next push needs a code from this screen again"),
          (_once_app.sync_config_manager.trusts, _TrustQuestionStandIn.asked,
           _once_app.status_signal.emitted))

    # An address this host has already said "no code" to is not asked again: that decision has been
    # made, and asking it twice is a person being pushed to change their mind by repetition.
    _TrustQuestionStandIn.asked.clear()
    _notifications.clear()
    _trusted_app = _HostRestoreApp([{"id": "chain-4999", "sync_code": "4999", "name": "Studio",
                                     "folder_path": _HOST_PUSH_FOLDER,
                                     "push_trusted_ips": ["192.168.1.7"]}],
                                   current_path=_HOST_PUSH_FOLDER,
                                   pushing=[("4999", "192.168.1.7")],
                                   last_counts=[("4999", (1, 0))])
    _trusted_app._on_host_push_event("4999", "192.168.1.7", "finished", "1 file(s) written")
    check("WN-I42 an address this host has already trusted is not asked again - the rest of the chain is still told, the folder list is still refreshed, and no window appears",
          _TrustQuestionStandIn.asked == [] and _notifications == [("4999", 63351)]
          and _trusted_app.said("took files from 192.168.1.7: 1 file(s) added")
          and len(_trusted_app.local_list_refresh_signal.emitted) == 1,
          (_TrustQuestionStandIn.asked, _notifications,
           _trusted_app.local_list_refresh_signal.emitted))

    _notifications.clear()
    _host_push_app.sync_host_server.pushing["4999"] = "192.168.1.7"
    _host_push_app.status_signal.emitted.clear()
    _host_push_app._on_hosted_folder_changed("4999")
    check("WN-I43 a hosted folder that is mid-push tells the clients nothing, because the one notification a push owes is the one sent with every file down - not one per file written",
          _notifications == [] and _host_push_app.status_signal.emitted == [],
          (_notifications, _host_push_app.status_signal.emitted))
    _host_push_app.sync_host_server.pushing.pop("4999", None)
    _host_push_app._on_hosted_folder_changed("4999")
    check("WN-I43b and the same folder once the push is over tells them - the watcher is let back in the moment the folder stops being half-written",
          _notifications == [("4999", 63351)] and _host_push_app.said("Notified clients on LAN"),
          (_notifications, _host_push_app.status_signal.emitted))

# ===========================================================================
# WN-J: finding a host without being told where it is
# ===========================================================================
# What a host answers a search, and what a scan makes of that answer, is proved in probe_sync (SY-N),
# where loopback sockets stand in for the network. What is proved here is the window that hands the
# job over and then uses what comes back: the boxes it fills in, the port it remembers, the thread it
# will not let outlive it, and the once-only notice a Host is given about chains that were already
# visible before this choice existed.
_scan_dlg = mod.ConnectClientChainDialog(None, CM)
check("WN-J1 joining a chain is offered a search of the network as well as an address to type",
      _scan_dlg.scan_btn.text() == "Find Hosts On My Network"
      and not _scan_dlg.host_list.isVisibleTo(_scan_dlg)
      and not _scan_dlg.host_list_label.isVisibleTo(_scan_dlg),
      (_scan_dlg.scan_btn.text(), _scan_dlg.host_list.isVisibleTo(_scan_dlg)))
_scan_dlg._on_scan_host({"ip": "192.168.1.50", "port": 63351, "sync_code": "4821",
                         "chain_name": "Rock Classics", "visible": True, "host_name": "KITCHEN",
                         "advertised": True})
check("WN-J2 a host the search found goes on the list, and the first one found is picked without being asked for",
      _scan_dlg.host_list.count() == 1 and _scan_dlg.host_list.isVisibleTo(_scan_dlg)
      and _scan_dlg.host_list.currentItem() is _scan_dlg.host_list.item(0)
      and "192.168.1.50:63351" in _scan_dlg.host_list.item(0).text(),
      _scan_dlg.host_list.item(0).text())
check("WN-J3 and picking a host puts its address, its code and its chain name into the boxes a chain is made from",
      _scan_dlg.ip_edit.text() == "192.168.1.50" and _scan_dlg.code_edit.text() == "4821"
      and _scan_dlg.playlist_name_edit.text() == "Rock Classics",
      (_scan_dlg.ip_edit.text(), _scan_dlg.code_edit.text(), _scan_dlg.playlist_name_edit.text()))
_scan_dlg._on_scan_host({"ip": "192.168.1.77", "port": 63350, "sync_code": "7788",
                         "chain_name": "Study", "visible": False, "host_name": "STUDY",
                         "advertised": True})
check("WN-J4 a private chain says it is private on the list, so what was found is not mistaken for what is open",
      "private" in _scan_dlg.host_list.item(1).text(), _scan_dlg.host_list.item(1).text())
_scan_dlg._on_scan_host({"ip": "192.168.1.9", "port": 63350, "sync_code": "", "chain_name": "",
                         "visible": True, "host_name": "OLD-PC", "advertised": False})
check("WN-J5 a host that will not name its chains is listed as the host it is, with the code left to the user",
      "older version" in _scan_dlg.host_list.item(2).text()
      and "type its sync code" in _scan_dlg.host_list.item(2).text(),
      _scan_dlg.host_list.item(2).text())
_scan_dlg.host_list.setCurrentRow(1)
check("WN-J6 picking a different host takes the boxes back and fills them in again",
      _scan_dlg.ip_edit.text() == "192.168.1.77" and _scan_dlg.code_edit.text() == "7788",
      (_scan_dlg.ip_edit.text(), _scan_dlg.code_edit.text()))
_scan_dlg.host_list.setCurrentRow(0)
_scan_dlg.folder_edit.setText(str(CLIENT_BASE))
_scan_dlg.playlist_name_edit.setText("Found Mix")
answering(True, lambda: _scan_dlg._connect_chain())
check("WN-J7 the port a host was found answering on is saved with the chain, because a host takes the first free port and 63351 is not 63350",
      CM.client_chains[-1]["host_port"] == 63351
      and CM.client_chains[-1]["last_known_host_ip"] == "192.168.1.50", CM.client_chains[-1])
_scan_dlg.ip_edit.setText("192.0.2.88")
_scan_dlg.playlist_name_edit.setText("Typed In")
answering(True, lambda: _scan_dlg._connect_chain())
check("WN-J8 and an address typed in afterwards is not quietly given the port of the address the search picked",
      CM.client_chains[-1]["host_port"] == seam.original("SYNC_PORT_START")
      and CM.client_chains[-1]["last_known_host_ip"] == "192.0.2.88", CM.client_chains[-1])
_scan_dlg.reject()


class _ConnectedSignal:
    """A signal a window can connect to, that records what was connected rather than emitting."""

    def __init__(self):
        self.handlers = []

    def connect(self, handler):
        self.handlers.append(handler)


class _ScanStub:
    """A HostScanThread that does not search, so the window's handling of it can be watched.

    Letting the real one run here would put a search for real hosts onto this machine's network,
    which is the one thing this suite keeps out of the suite. What is watched instead is that the
    window hands the job over, says it is doing it, and stops it before the window goes away.
    """

    def __init__(self, requested_code='', parent=None):
        self.requested_code = str(requested_code)
        self.parent = parent
        self.started = False
        self.interrupted = False
        self.waited_for = None
        self.host_found = _ConnectedSignal()
        self.scan_finished = _ConnectedSignal()

    def start(self):
        self.started = True

    def requestInterruption(self):
        self.interrupted = True

    def wait(self, milliseconds):
        self.waited_for = milliseconds


check("WN-J9 the search is a thread of its own, so searching the network cannot hold the window still",
      issubclass(seam.original("HostScanThread"), QThread), seam.original("HostScanThread"))
seam.patch("HostScanThread", _ScanStub)
_thread_dlg = mod.ConnectClientChainDialog(None, CM)
_thread_dlg.code_edit.setText("4821")
_thread_dlg._start_scan()
_running_scan = _thread_dlg._scan_thread
check("WN-J10 pressing the search hands the job to that thread, carrying the code already typed so a private chain answers it",
      isinstance(_running_scan, _ScanStub) and _running_scan.started
      and _running_scan.requested_code == "4821", _running_scan.requested_code)
check("WN-J11 and the window says it is searching, and will not start a second search while the first is going",
      not _thread_dlg.scan_btn.isEnabled() and "Searching" in _thread_dlg.scan_btn.text(),
      (_thread_dlg.scan_btn.text(), _thread_dlg.scan_btn.isEnabled()))
_thread_dlg.reject()
check("WN-J12 closing the window stops a search still running and waits for it, because a thread that outlives its window takes the program with it",
      _thread_dlg._scan_thread is None and _running_scan.interrupted and _running_scan.waited_for == 3000,
      (_running_scan.interrupted, _running_scan.waited_for))
_thread_dlg._on_scan_done(0, "finished")
check("WN-J13 a search that found nothing says what to check, rather than leaving an empty list and a silent window",
      "No host found" in _thread_dlg.scan_status.text()
      and "Visible" in _thread_dlg.scan_status.text(), _thread_dlg.scan_status.text())
_thread_dlg._on_scan_done(2, "finished")
check("WN-J14 and the button is ready to be pressed again afterwards either way",
      _thread_dlg.scan_btn.isEnabled() and "2 host" in _thread_dlg.scan_status.text(),
      (_thread_dlg.scan_btn.text(), _thread_dlg.scan_status.text()))
seam.restore("HostScanThread")
check("WN-J15 the search this section stood in for is back with the program",
      not seam.is_patched("HostScanThread")
      and "yt_msd.sync.discovery" in seam.owned_by("HostScanThread"),
      seam.owned_by("HostScanThread"))


class _NoticeManager:
    """The sync config the startup notice reads and writes, with no config file behind it."""

    def __init__(self, hosted_chains, settings=None):
        self.hosted_chains = hosted_chains
        self.settings = settings if settings is not None else dict(mod.DEFAULT_SYNC_SETTINGS)
        self.saves = 0

    def save(self):
        self.saves += 1


class _EmittedSignal:
    def __init__(self):
        self.emitted = []

    def emit(self, title, body):
        self.emitted.append((title, body))


class _NoticeApp:
    """Both halves of the startup notice, taken from MainApp with no main window behind them."""

    _notify_legacy_visible_chains = mod.MainApp._notify_legacy_visible_chains
    _on_chain_visibility_notice = mod.MainApp._on_chain_visibility_notice

    def __init__(self, manager):
        self.sync_config_manager = manager
        self.sync_manager_dialog = None
        self.chain_visibility_signal = _EmittedSignal()
        self.emitted = self.chain_visibility_signal.emitted


_legacy_manager = _NoticeManager([{"id": "hc_2580", "sync_code": "2580", "name": "Made by 3.2"},
                                  {"id": "hc_1111", "sync_code": "1111", "name": "Made by 3.5",
                                   "visible": True}])
_notice_app = _NoticeApp(_legacy_manager)
_notice_app._notify_legacy_visible_chains()
check("WN-J16 a Host still holding chains saved before this choice existed is told about them, by name and by code",
      len(_notice_app.emitted) == 1 and "Made by 3.2" in _notice_app.emitted[0][1]
      and "2580" in _notice_app.emitted[0][1] and "Made by 3.5" not in _notice_app.emitted[0][1],
      _notice_app.emitted)
check("WN-J17 the notice says where the choice is, because a privacy setting nobody can find is not one",
      '"Visible" badge' in _notice_app.emitted[0][1], _notice_app.emitted[0][1])
check("WN-J18 and it is marked as given and saved before it is opened, so it is a notice and not something read every launch",
      _legacy_manager.settings[mod.VISIBILITY_NOTICE_SETTING] is True and _legacy_manager.saves == 1,
      (_legacy_manager.settings, _legacy_manager.saves))
_notice_app._notify_legacy_visible_chains()
check("WN-J19 the next launch is silent", len(_notice_app.emitted) == 1 and _legacy_manager.saves == 1,
      _legacy_manager.saves)
_new_manager = _NoticeManager([{"id": "hc_9090", "sync_code": "9090", "name": "Made by 3.5",
                                "visible": False}])
_new_app = _NoticeApp(_new_manager)
_new_app._notify_legacy_visible_chains()
check("WN-J20 a machine whose chains all carry the choice is told nothing, and nothing is written for it",
      _new_app.emitted == [] and _new_manager.saves == 0, (_new_app.emitted, _new_manager.saves))
_no_chains_app = _NoticeApp(_NoticeManager([]))
_no_chains_app._notify_legacy_visible_chains()
check("WN-J21 and a machine hosting nothing is told nothing either", _no_chains_app.emitted == [],
      _no_chains_app.emitted)
answering(True, lambda: _notice_app._on_chain_visibility_notice("a title", "a body"))
check("WN-J22 the notice is opened as a box on the main window, and not as a question the user has to answer",
      len(_Answers.told) == 1 and _Answers.told[0][0] is None and _Answers.told[0][2] == "a body"
      and _Answers.asked == [], (_Answers.told, _Answers.asked))
_open_dialog = QWidget()
_open_dialog.show()
_dialog_app = _NoticeApp(_NoticeManager([]))
_dialog_app.sync_manager_dialog = _open_dialog
answering(True, lambda: _dialog_app._on_chain_visibility_notice("a title", "a body"))
check("WN-J23 and it opens on the Sync Chains window when that window is already open, because that is where the badge it names is",
      _Answers.told[0][0] is _open_dialog, _Answers.told)
_open_dialog.hide()
check("WN-J24 the notice is a signal MainApp declares and a pair of methods it owns, so the startup check has somewhere to put it",
      "Signal" in type(getattr(mod.MainApp, "chain_visibility_signal")).__name__
      and "_notify_legacy_visible_chains" in dir(mod.MainApp)
      and "_on_chain_visibility_notice" in dir(mod.MainApp),
      type(getattr(mod.MainApp, "chain_visibility_signal")).__name__)
_bootstrap_attrs = {node.attr for node in ast.walk(ast.parse(
    (Path(SRC_DIR) / "yt_msd" / "ui" / "bootstrap.py").read_text(encoding="utf-8")))
    if isinstance(node, ast.Attribute)}
check("WN-J25 and it is wired where the sync subsystem is built: the signal is connected, and the check is scheduled",
      "_on_chain_visibility_notice" in _bootstrap_attrs
      and "_notify_legacy_visible_chains" in _bootstrap_attrs,
      sorted(name for name in _bootstrap_attrs if "visibility" in name))

# ===========================================================================
# WN-K: a name the program never gave itself
# ===========================================================================
#
#   setup_ui puts the last search back in the box, puts the saved session back on the screen
#   when "remember my place" is on, and then starts a background re-search to refresh the
#   cache. That re-search is told which track it must not cancel, and the name holding it used
#   to be assigned only inside the session branch. A start with the session option off - which
#   is how the program ships, save_place defaults to False in ui/bootstrap.py - never reached
#   the line that assigned it, and the window died in setup_ui with an UnboundLocalError
#   before it was drawn. The installed copy on a second machine proved it, and none of the
#   1081 checks here ever did, because every start they described either had a session to
#   restore or had no saved search to re-search.
#
#   The same shape sits at the end of this section, in the rename pass.
#
#   These checks run the shipped text. The restore half of setup_ui touches no widget - it
#   reads the saved settings and calls back into the app - so those lines are lifted out of
#   yt_msd/ui/layout.py whole, put behind a stub holding only the attributes they ask for, and
#   run the way __init__ runs them. Nothing is opened, no folder written, no network asked.
_layout_lines = (Path(SRC_DIR) / "yt_msd" / "ui" / "layout.py").read_text(encoding="utf-8").splitlines()
_restore_first = next(i for i, line in enumerate(_layout_lines) if "# Restore last search" in line)
_restore_last = next(i for i, line in enumerate(_layout_lines) if "keep_fetch_vid_id=" in line)
_restore_lines = _layout_lines[_restore_first:_restore_last + 1]
_restore_indent = min(len(line) - len(line.lstrip()) for line in _restore_lines if line.strip())
_restore_src = "def _startup(self):\n" + "".join(
    ("    " + line[_restore_indent:] if line.strip() else "") + "\n" for line in _restore_lines)
_startup_env = {}
exec(compile(_restore_src, "yt_msd/ui/layout.py", "exec"), _startup_env)
_startup = _startup_env["_startup"]


class _SearchBox:
    def __init__(self):
        self.texts = []

    def setText(self, text):
        self.texts.append(text)


class _StartUp:
    """Only the attributes the restore half of setup_ui asks for, and a record of each call
    it makes, so a check can say what the start did as well as that it survived."""

    def __init__(self, last_search="", save_place=False, session_data=None, recent_playlists=()):
        self.last_search = last_search
        self.save_place = save_place
        self.recent_playlists = list(recent_playlists)
        if session_data is not None:
            self.session_data = session_data
        self.search_entry = _SearchBox()
        self.playback_index = -1
        self.handed = []
        self.started = []
        self.searches = []

    def _on_search_results(self, results, is_playlist, reset_view=True):
        self.handed.append((results, reset_view))

    def play_result(self, video, paused_at_start=False):
        self.started.append((video, paused_at_start))

    def perform_search(self, is_playlist=False, keep_fetch_vid_id=None):
        self.searches.append((is_playlist, keep_fetch_vid_id))


def _start(app):
    """Run the real lines over one described start, and hand back whatever they raised."""
    try:
        _startup(app)
        return None
    except Exception as exc:
        return exc


_plain = _StartUp(last_search="https://www.youtube.com/watch?v=abc")
_plain_raised = _start(_plain)
check("WN-K1 the start every new install makes - a saved search, the session option off - raises nothing",
      _plain_raised is None, repr(_plain_raised))
check("WN-K2 and it still re-searches that search, saying there is no track to keep",
      _plain.searches == [(False, None)], _plain.searches)
check("WN-K3 the last search goes back in the box it was typed into",
      _plain.search_entry.texts == ["https://www.youtube.com/watch?v=abc"], _plain.search_entry.texts)

_no_session = _StartUp(last_search="a search", save_place=True, session_data={})
_no_session_raised = _start(_no_session)
check("WN-K4 the session option on with nothing saved is the same start, not a different one",
      _no_session_raised is None and _no_session.handed == [] and _no_session.searches == [(False, None)],
      (repr(_no_session_raised), _no_session.handed, _no_session.searches))

_SESSION = {"search_results": [{"id": "vid1", "title": "one"}, {"id": "vid2", "title": "two"}],
            "playback_index": 1, "current_video_id": "vid2"}
_saved = _StartUp(last_search="a search", save_place=True, session_data=_SESSION)
_saved_raised = _start(_saved)
check("WN-K5 a machine that does remember its place gets its list back, without moving where the reader was looking",
      _saved_raised is None and len(_saved.handed) == 1 and _saved.handed[0][1] is False
      and _saved.playback_index == 1,
      (repr(_saved_raised), _saved.handed, _saved.playback_index))
check("WN-K6 the track it was holding is put back on the player paused, ready for the listener to resume it",
      _saved.started == [(_SESSION["search_results"][1], True)], _saved.started)
check("WN-K7 the re-search that follows is told to leave that track's fetch alone - the reason it is passed an id at all",
      _saved.searches == [(False, "vid2")], _saved.searches)

_local = _StartUp(last_search="a search", save_place=True,
                  session_data={"search_results": [], "playback_index": -1, "current_video_id": "local"})
_local_raised = _start(_local)
check("WN-K8 a place remembered on the local pane starts nothing on the player, and the re-search still runs",
      _local_raised is None and _local.started == [] and len(_local.searches) == 1,
      (repr(_local_raised), _local.started, _local.searches))

_playlist = _StartUp(last_search="https://www.youtube.com/playlist?list=PL1", save_place=False,
                     recent_playlists=[{"name": "my list", "url": "https://www.youtube.com/playlist?list=PL1"}])
_playlist_raised = _start(_playlist)
check("WN-K9 a saved playlist is re-searched as a playlist, so its rows come back under the name it was given",
      _playlist_raised is None and _playlist.searches == [(True, None)],
      (repr(_playlist_raised), _playlist.searches))

_first_run = _StartUp(last_search="")
_first_run_raised = _start(_first_run)
check("WN-K10 a first run with nothing saved re-searches nothing - the one start that never hit the bug, which is why it hid",
      _first_run_raised is None and _first_run.searches == [], repr(_first_run_raised))

_setup_ui = next(node for node in ast.walk(ast.parse(
    (Path(SRC_DIR) / "yt_msd" / "ui" / "layout.py").read_text(encoding="utf-8")))
    if isinstance(node, ast.FunctionDef) and node.name == "setup_ui")
_top_level_v_id = [st for st in _setup_ui.body
                   if isinstance(st, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "v_id" for t in st.targets)]
check("WN-K11 the id the re-search passes is given a value at the top of setup_ui, not inside a branch a start may never take",
      len(_top_level_v_id) == 1, _top_level_v_id)
check("WN-K12 and the lines these checks ran are the shipped ones: the saved search through the re-search, nothing between",
      "# Restore last search" in _restore_lines[0] and _restore_lines[-1].strip().startswith("self.perform_search("),
      (_restore_lines[0], _restore_lines[-1]))

_renamer_src = (Path(SRC_DIR) / "yt_msd" / "audio" / "renamer.py").read_text(encoding="utf-8")
check("WN-K13 the rename pass only cleans a name the prompt actually settled on - 'prev' at the first file settles on none",
      "if not is_manually_inputted and final_name:" in _renamer_src)
check("WN-K14 and the branch that skips a file with no name still gets its turn, so the pass moves on instead of dying",
      _renamer_src.index("if not is_manually_inputted and final_name:")
      < _renamer_src.index("if not final_name:") <= _renamer_src.index("Invalid name. Skipped."),
      _renamer_src[_renamer_src.index("if not is_manually_inputted and final_name:"):][:220])



# ============================================================================
# WN-L: the window that joins a chain, and the size it gives itself
# ============================================================================
# *Connect To Remote Chain* used to be `setFixedSize(520, 640)` with a found-host list inside it that
# only exists once a search answers. A window that is not allowed to grow pays for the list by taking
# room off everything else, and that is what it did: the search button cut short at the side, the line
# beside it cut short, and the hosts a search had really found cut off and unclickable. The window now
# asks its own layout how much room its rows want (AI Readme gotcha 55).
#
# What follows is measured off the real widgets. A window that has never been put on the screen still
# knows the room each of its rows asks for - its minimum size, its layout's total, the width a button's
# own text needs in the font it will be drawn in - and those numbers are the whole difference between a
# row that fits and a row that is cut.
from PySide6.QtGui import QFontMetrics

_wl_cfg = fixture("connect sizing config")
_wl_cm = mod.SyncConfigManager(str(_wl_cfg))
_wl_dlg = mod.ConnectClientChainDialog(None, _wl_cm)
_wl_font = QFontMetrics(_wl_dlg.scan_btn.font())

check("WN-L1 the window is no longer pinned to a size it cannot grow past",
      _wl_dlg.minimumSize() != _wl_dlg.maximumSize()
      and _wl_dlg.minimumWidth() == seam.original("CLIENT_DIALOG_WIDTH"),
      (_wl_dlg.minimumSize().width(), _wl_dlg.minimumSize().height(),
       _wl_dlg.maximumSize().width()))
check("WN-L2 before a search has found anything, it is already roomier than its rows ask for",
      _wl_dlg.width() >= _wl_dlg.layout().totalMinimumSize().width()
      and _wl_dlg.height() >= _wl_dlg.layout().totalMinimumSize().height(),
      (_wl_dlg.width(), _wl_dlg.height(), _wl_dlg.layout().totalMinimumSize().width(),
       _wl_dlg.layout().totalMinimumSize().height()))
_wl_before = _wl_dlg.height()
_wl_dlg._on_scan_host({"ip": "192.168.1.50", "port": 63351, "sync_code": "4821",
                       "chain_name": "Other", "visible": True, "host_name": "KITCHEN",
                       "advertised": True})
check("WN-L3 hosts arriving make the window taller rather than squeezing the rows that were already there",
      _wl_dlg.height() > _wl_before
      and _wl_dlg.layout().totalMinimumSize().height() <= _wl_dlg.height(),
      (_wl_before, _wl_dlg.height(), _wl_dlg.layout().totalMinimumSize().height()))
check("WN-L4 the found-host list holds a height of its own to read them in",
      _wl_dlg.host_list.minimumHeight() >= 100
      and _wl_dlg.host_list.maximumHeight() >= _wl_dlg.host_list.minimumHeight(),
      (_wl_dlg.host_list.minimumHeight(), _wl_dlg.host_list.maximumHeight()))
check("WN-L5 the search button is at least as wide as the sentence it carries, and is not pinned",
      _wl_dlg.scan_btn.minimumWidth() >= _wl_font.horizontalAdvance(_wl_dlg.scan_btn.text())
      and _wl_dlg.scan_btn.minimumWidth() != _wl_dlg.scan_btn.maximumWidth(),
      (_wl_dlg.scan_btn.minimumWidth(), _wl_font.horizontalAdvance(_wl_dlg.scan_btn.text()),
       _wl_dlg.scan_btn.maximumWidth()))
_wl_dlg.scan_btn.setText("Searching...")
check("WN-L6 and the searching state does not shrink it out from under the cursor",
      _wl_dlg.scan_btn.minimumWidth() >= _wl_font.horizontalAdvance(_wl_dlg.scan_btn.text()),
      (_wl_dlg.scan_btn.minimumWidth(), _wl_font.horizontalAdvance(_wl_dlg.scan_btn.text())))
_wl_dlg.scan_btn.setText("Find Hosts On My Network")
check("WN-L7 what the search did is said on a line of its own across the window, wrapping when it is long",
      _wl_dlg.layout().indexOf(_wl_dlg.scan_status) >= 0 and _wl_dlg.scan_status.wordWrap(),
      (_wl_dlg.layout().indexOf(_wl_dlg.scan_status), _wl_dlg.scan_status.wordWrap()))
# The name a host gives its own chain, and what a client does with it. The example is a host
# hosting two chains, "Other" and "Christian": the search lists both, and whichever row is picked is
# the chain the client is joining - its name goes into the box the local folder is named from.
_wl_base = fixture("connect base")
_wl_dlg.folder_edit.setText(str(_wl_base))
_wl_dlg._on_scan_host({"ip": "192.168.1.50", "port": 63351, "sync_code": "7788",
                       "chain_name": "Christian", "visible": True, "host_name": "KITCHEN",
                       "advertised": True})
_wl_dlg.host_list.setCurrentRow(1)
check("WN-L8 two chains on one host are two rows, and the row picked names the chain being joined",
      _wl_dlg.host_list.count() == 2 and "Other" in _wl_dlg.host_list.item(0).text()
      and "Christian" in _wl_dlg.host_list.item(1).text()
      and _wl_dlg.playlist_name_edit.text() == "Christian",
      (_wl_dlg.host_list.item(0).text(), _wl_dlg.host_list.item(1).text(),
       _wl_dlg.playlist_name_edit.text()))
_wl_dlg.host_list.setCurrentRow(0)
check("WN-L9 picking the other row changes the name to that chain's, instead of keeping the first one found",
      _wl_dlg.playlist_name_edit.text() == "Other", _wl_dlg.playlist_name_edit.text())
_wl_dlg._connect_chain()
_wl_chain = _wl_cm.client_chains[-1]
check("WN-L10 the chain made from that pick carries the host's chain name - as its own name, as the folder it names, and as what the host said",
      _wl_chain['name'] == 'Other' and Path(_wl_chain['folder_path']).name == 'Other'
      and _wl_chain['host_chain_name'] == 'Other', _wl_chain)
_wl_dlg.playlist_name_edit.setText("My Own Name")
_wl_dlg.host_list.setCurrentRow(1)
check("WN-L11 a name typed at the box outranks the name a search filled it with",
      _wl_dlg.playlist_name_edit.text() == "My Own Name", _wl_dlg.playlist_name_edit.text())
_wl_dlg._connect_chain()
_wl_typed = _wl_cm.client_chains[-1]
check("WN-L12 and the host's own name is kept beside it, because that is what the other machine calls the chain",
      _wl_typed['name'] == 'My Own Name' and _wl_typed['host_chain_name'] == 'Christian', _wl_typed)
_wl_dlg.ip_edit.setText("192.0.2.88")
_wl_dlg.code_edit.setText("9012")
_wl_dlg._connect_chain()
check("WN-L13 an address typed in afterwards is not quietly given another machine's chain name",
      _wl_cm.client_chains[-1]['host_chain_name'] == ''
      and _wl_cm.client_chains[-1]['last_known_host_ip'] == '192.0.2.88',
      _wl_cm.client_chains[-1])
_wl_dlg.reject()

_wl_sync_cfg = fixture("host chain name cards")
_wl_sync_cm = mod.SyncConfigManager(str(_wl_sync_cfg))
_wl_named = _wl_sync_cm.add_client_chain(name="Local Folder",
                                         folder_path=str(_wl_sync_cfg / "Local Folder"),
                                         sync_code="6421", host_ip="192.168.1.50",
                                         host_chain_name="Christian")
_wl_plain = _wl_sync_cm.add_client_chain(name="Joined By Typing",
                                         folder_path=str(_wl_sync_cfg / "Joined By Typing"),
                                         sync_code="6422", host_ip="192.168.1.51")
check("WN-L14 the name is written into the chain's own record, empty included when no host has ever told it",
      _wl_named['host_chain_name'] == 'Christian' and _wl_plain['host_chain_name'] == '',
      (_wl_named, _wl_plain))
_wl_mgr = QuietSyncDialog(AppStandIn(sync_config_manager=_wl_sync_cm))
check("WN-L15 the client card says what the host calls this chain, beside the address its host answers on",
      any('Host chain: <b>Christian</b>' in text for text in _texts(_card_for(_wl_mgr, _wl_named['id']))),
      _texts(_card_for(_wl_mgr, _wl_named['id'])))
check("WN-L16 and a chain no host has ever named says nothing about one",
      not any('Host chain' in text for text in _texts(_card_for(_wl_mgr, _wl_plain['id']))),
      _texts(_card_for(_wl_mgr, _wl_plain['id'])))
_wl_plain['host_chain_name'] = 'Study'
_wl_mgr.refresh_cards()
check("WN-L17 a card is rebuilt when the name is learned, because the name is part of what a refresh compares",
      any('Host chain: <b>Study</b>' in text for text in _texts(_card_for(_wl_mgr, _wl_plain['id']))),
      _texts(_card_for(_wl_mgr, _wl_plain['id'])))
_wl_client_src = (Path(SRC_DIR) / 'yt_msd' / 'sync' / 'client.py').read_text(encoding='utf-8')
check("WN-L18 the name is taken from the host's own answers - the AUTH of a sync and the search that finds a host whose address moved",
      "auth_resp.get('chain_name')" in _wl_client_src
      and "host_ip, host_port, host_chain = found" in _wl_client_src,
      [line for line in _wl_client_src.splitlines() if 'chain_name' in line])

# What every one of these windows needs to be wide enough for. A control that lands past the right edge
# of the area it is in is a control nobody using the window ever sees, and the only way to catch that is
# to measure the window against the rows it holds.
_wl_mgr.show()
_wl_mgr.resize(920, 620)
QApplication.processEvents()
_wl_viewport = _wl_mgr.cards_scroll.viewport().width()
_wl_client_card = _card_for(_wl_mgr, _wl_named['id'])
_wl_past_the_edge = [btn.text() for btn in _wl_client_card.findChildren(QPushButton)
                     if btn.geometry().x() + btn.geometry().width() > _wl_viewport]
check("WN-L19 every button on a client chain's card lands inside the part of the window that can be seen - a control past the right edge of the card area is a control nobody using the window finds, and a card that needs more width than the window gives it is exactly that",
      _wl_viewport >= _wl_client_card.sizeHint().width() and _wl_past_the_edge == [],
      (_wl_viewport, _wl_client_card.sizeHint().width(), _wl_past_the_edge))
_wl_host_dlg = mod.CreateHostChainDialog(None, _wl_cm)
_wl_host_dlg.show()
QApplication.processEvents()
check("WN-L20 the window that makes a hosted chain keeps its own rows inside the width it is pinned to, because a row wider than a fixed-size window has its number box squeezed out of it",
      _wl_host_dlg.layout().totalMinimumSize().width() <= _wl_host_dlg.width(),
      (_wl_host_dlg.layout().totalMinimumSize().width(), _wl_host_dlg.width()))



# ===========================================================================
# WN-M: the box that says this copy has just become a new version, and the host's
#       "every chain, fetch now" message
# ===========================================================================
# Two things that both begin when a machine starts. A copy that has just become a new version says
# so once, from a record it keeps in its own settings file; and a machine that hosts chains tells the
# clients of those chains there is something to fetch, instead of leaving each of them to find out
# when its own interval comes round. What is proved below is the deciding and the message: which
# version counts as news, where the record of it lives, what its link points at, which codes go out,
# and what a client makes of them when it reads one. No update is downloaded by any check here, and
# no packet is put on the LAN: both senders are replaced through the seam, and the real socket traffic
# is proved over loopback in probe_sync instead.
version_notes_are_due = seam.original("version_notes_are_due")
release_notes_url = seam.original("release_notes_url")
_UPDATE_REPO = seam.original("UPDATE_REPO")
_SYNC_REQUEST_DELAY = seam.original("HOST_UP_SYNC_REQUEST_DELAY_MS")


class _StatusLine:
    """Records what a handler meant to put on the window's status bar."""
    def __init__(self):
        self.lines = []

    def emit(self, text, sticky=False, color=""):
        self.lines.append((text, sticky, color))


class _VersionNotesApp(AppStandIn):
    """The main window as the version box knows it: a status bar, and a settings file it saves to."""
    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.status_signal = _StatusLine()


check("WN-M1 a version this machine has never reported is news - including the first start after an update from a version that kept no record at all",
      version_notes_are_due("3.5", "") is True and version_notes_are_due("3.5", None) is True,
      (version_notes_are_due("3.5", ""), version_notes_are_due("3.5", None)))
check("WN-M2 the same version never says it twice, however many times this machine is started",
      version_notes_are_due("3.5", "3.5") is False and version_notes_are_due("3.5", "RELEASE-3.5") is False,
      (version_notes_are_due("3.5", "3.5"), version_notes_are_due("3.5", "RELEASE-3.5")))
check("WN-M3 an upgrade is news, a step back is not, and 3.10 is newer than 3.9 rather than a smaller number after a point",
      version_notes_are_due("3.5", "3.4") is True and version_notes_are_due("3.4", "3.5") is False
      and version_notes_are_due("3.10", "3.9") is True,
      [version_notes_are_due(a, b) for a, b in (("3.5", "3.4"), ("3.4", "3.5"), ("3.10", "3.9"))])
check("WN-M4 a build carrying no version worth reporting says nothing about a version",
      version_notes_are_due("", "") is False and version_notes_are_due("", "3.4") is False
      and version_notes_are_due("development", "") is False,
      [version_notes_are_due(a, b) for a, b in (("", ""), ("", "3.4"), ("development", ""))])
check("WN-M5 the changelog link is the release page for the version now running, named the way every release in this repository is named",
      release_notes_url("3.5") == f"https://github.com/{_UPDATE_REPO}/releases/tag/RELEASE-3.5"
      and release_notes_url("RELEASE-3.4") == f"https://github.com/{_UPDATE_REPO}/releases/tag/RELEASE-3.4"
      and release_notes_url("v3.6.0") == f"https://github.com/{_UPDATE_REPO}/releases/tag/RELEASE-3.6"
      and release_notes_url("3.5.1") == f"https://github.com/{_UPDATE_REPO}/releases/tag/RELEASE-3.5.1",
      (release_notes_url("3.5"), release_notes_url("RELEASE-3.4"), release_notes_url("v3.6.0"),
       release_notes_url("3.5.1")))
check("WN-M6 a version with no number in it gets the page that lists every release, because that page always exists",
      release_notes_url("") == f"https://github.com/{_UPDATE_REPO}/releases"
      and release_notes_url("development") == f"https://github.com/{_UPDATE_REPO}/releases",
      (release_notes_url(""), release_notes_url("development")))

_notes_box = mod.VersionNotesDialog(None, "3.5", "3.4")
_notes_texts = [lbl.text() for lbl in _notes_box.findChildren(QLabel)]
check("WN-M7 the box names the version it is reporting and the one it came from, so what is reported is the change",
      any("3.5" in text for text in _notes_texts) and any("updated from 3.4" in text for text in _notes_texts),
      _notes_texts)
check("WN-M8 its link is the release page for the version now running, and it is a link the desktop browser opens",
      "tag/RELEASE-3.5" in _notes_box.link_lbl.text() and _notes_box.notes_url == release_notes_url("3.5")
      and _notes_box.link_lbl.openExternalLinks(),
      (_notes_box.link_lbl.text(), _notes_box.notes_url))
_box2 = mod.VersionNotesDialog(None, "3.5", "")
_box2_texts = [lbl.text() for lbl in _box2.findChildren(QLabel)]
check("WN-M9 with nothing to compare against it says what this is instead of inventing the version it came from",
      any("This is yt-msd 3.5" in text for text in _box2_texts)
      and not any("updated from" in text for text in _box2_texts), _box2_texts)
check("WN-M10 it is closed by its own button and does not hold the window it was opened from",
      any(btn.text() == "Got it" for btn in _notes_box.findChildren(QPushButton)) and not _notes_box.isModal(),
      [btn.text() for btn in _notes_box.findChildren(QPushButton)])


# The box is built by a startup timer, so driving it means standing in for the box itself: a real one
# on screen for every check below is what the rest of this suite avoids. What is recorded is what the
# startup handler decided - which version it reported, which version it believed this machine had
# already seen, and whether it put the window on screen.
_built_boxes = []


class _RecordedNotesDialog:
    def __init__(self, parent_window, current_version, previous_version=""):
        self.parent_window = parent_window
        self.current_version = current_version
        self.previous_version = previous_version
        self.notes_url = release_notes_url(current_version)
        self.shown = False
        _built_boxes.append(self)

    def show(self):
        self.shown = True

    def raise_(self):
        pass

    def activateWindow(self):
        pass


seam.patch("VersionNotesDialog", _RecordedNotesDialog)
_fresh_app = _VersionNotesApp(last_seen_version="")
mod.MainApp._show_version_notes(_fresh_app)
check("WN-M11 the first start as a new version builds one box for the version now running, and puts it on screen",
      len(_built_boxes) == 1 and _built_boxes[0].current_version == mod.APP_VERSION
      and _built_boxes[0].shown, (_built_boxes, mod.APP_VERSION))
check("WN-M12 and it records that this version has been reported before the window is ever answered, so the same upgrade is not reported again on the next start",
      _fresh_app.last_seen_version == mod.APP_VERSION and _fresh_app.called("save_config") == 1,
      (_fresh_app.last_seen_version, _fresh_app.calls))
check("WN-M13 the status bar says what happened in the same breath as the box",
      any(mod.APP_VERSION in line[0] for line in _fresh_app.status_signal.lines),
      _fresh_app.status_signal.lines)
mod.MainApp._show_version_notes(_fresh_app)
check("WN-M14 starting the same version a second time builds nothing and saves nothing",
      len(_built_boxes) == 1 and _fresh_app.called("save_config") == 1,
      (_built_boxes, _fresh_app.calls))
# A record older than any version this build could be, so this check says the same thing whatever
# APP_VERSION currently holds.
_upgrade_app = _VersionNotesApp(last_seen_version="0.1")
mod.MainApp._show_version_notes(_upgrade_app)
check("WN-M15 an upgrade from a version this machine did record says which one it came from",
      len(_built_boxes) == 2 and _built_boxes[1].previous_version == "0.1"
      and any("from 0.1" in line[0] for line in _upgrade_app.status_signal.lines),
      (_built_boxes[-1].previous_version, _upgrade_app.status_signal.lines))
_backwards_app = _VersionNotesApp(last_seen_version="99.0")
mod.MainApp._show_version_notes(_backwards_app)
check("WN-M16 a copy found running an older version than the one it reported says nothing, and keeps the record it has so the next upgrade is still reported",
      len(_built_boxes) == 2 and _backwards_app.last_seen_version == "99.0"
      and _backwards_app.status_signal.lines == [],
      (_backwards_app.last_seen_version, _backwards_app.status_signal.lines))
seam.restore("VersionNotesDialog")
check("WN-M17 the box this section stood in for is back with the program",
      not seam.is_patched("VersionNotesDialog") and seam.read("VersionNotesDialog") is mod.VersionNotesDialog,
      seam.owned_by("VersionNotesDialog"))


class _ComboText:
    """The two boxes save_config reads their format and bitrate out of, as the two values they hold."""
    def __init__(self, text):
        self._text = text

    def currentText(self):
        return self._text

    def text(self):
        return self._text


class _SavedConfigApp(QWidget):
    """A window carrying only what save_config and load_config read out of it.

    The record of what has been reported is only worth keeping if it survives the settings file, and
    the settings file is the one thing every way of updating yt-msd leaves where it is - the installer
    skips it, the swap helper writes beside it, and an update downloaded inside the app writes beside
    it too. So this is the real save_config and the real load_config, driven against a file under the
    fixture folder, rather than a check that the key appears somewhere in the source.
    """
    def __init__(self, config_path):
        super().__init__(None)
        self.config_path = str(config_path)
        self.format_combo = _ComboText("mp3")
        self.bitrate_combo = _ComboText("192")
        self.appearance_mode = "Dark"
        self.accent_color_name = "Blue"
        self.recent_folders = [str(fixture("saved config folders"))]
        self.local_folders = []
        self.local_current_path = ""
        self.volume_val = 100
        self.minimize_to_tray = False
        self.use_custom_args = False
        self.custom_args = ""
        self.recent_playlists = []
        self.splitter_sizes = [300, 800, 300]
        self.save_place = False
        self.run_renamer = False
        self.normalization_mode = "ask"
        self.auto_rename = False
        self.silence_pad_dur = 2.0
        self.silence_trim = True
        self.use_custom_norm_cmd = False
        self.custom_norm_cmd = ""
        self.download_threads = 3
        self.normalization_threads = 2
        self.search_results = []
        self.playback_index = -1
        self.current_video_id = ""
        self.last_search = ""


_VERSION_CFG_DIR = fixture("version record")
_VERSION_CFG_FILE = _VERSION_CFG_DIR / "gui_config.json"
_writer_app = _SavedConfigApp(_VERSION_CFG_FILE)
_writer_app.last_seen_version = mod.APP_VERSION
mod.MainApp.save_config(_writer_app)
_written_cfg = json.loads(_VERSION_CFG_FILE.read_text(encoding="utf-8"))
check("WN-M18 the record of what has been reported is written into the settings file, which is the one file every way of updating yt-msd leaves where it is",
      _written_cfg.get("last_seen_version") == mod.APP_VERSION, _written_cfg.get("last_seen_version"))
_reader_app = _SavedConfigApp(_VERSION_CFG_FILE)
mod.MainApp.load_config(_reader_app)
check("WN-M19 and the next start reads it back, which is what turns a second start on the same version into a silent one",
      _reader_app.last_seen_version == mod.APP_VERSION
      and version_notes_are_due(mod.APP_VERSION, _reader_app.last_seen_version) is False,
      _reader_app.last_seen_version)
_OLD_CFG_DIR = fixture("settings written by 3.4")
_OLD_CFG_FILE = _OLD_CFG_DIR / "gui_config.json"
_OLD_CFG_FILE.write_text(json.dumps({"format": "mp3", "bitrate": "192", "volume": 80,
                                     "disable_update_checks": False}), encoding="utf-8")
_old_reader = _SavedConfigApp(_OLD_CFG_FILE)
mod.MainApp.load_config(_old_reader)
check("WN-M20 a settings file written by a version that kept no such record reads as no record, which is why the upgrade out of an older build still gets its one box",
      _old_reader.last_seen_version == ""
      and version_notes_are_due(mod.APP_VERSION, _old_reader.last_seen_version) is True,
      (_old_reader.last_seen_version, version_notes_are_due(mod.APP_VERSION, "")))
check("WN-M21 and reading a file that has no such key changes nothing else about what was read from it",
      _old_reader.volume_val == 80 and _old_reader.disable_update_checks is False
      and _old_reader.format_var == "mp3",
      (_old_reader.volume_val, _old_reader.disable_update_checks, _old_reader.format_var))
_CHAINS_CFG_DIR = fixture("version record beside chains")
_CHAINS_CFG_FILE = _CHAINS_CFG_DIR / "gui_config.json"
_CHAINS_CFG_FILE.write_text(json.dumps({
    "hosted_chains": [{"id": "hc_2468", "name": "Front Room", "sync_code": "2468",
                       "folder_path": str(_CHAINS_CFG_DIR), "visible": True}],
    "sync_settings": {"auto_sync_interval_minutes": 30},
}), encoding="utf-8")
_beside_app = _SavedConfigApp(_CHAINS_CFG_FILE)
_beside_app.last_seen_version = "3.5"
mod.MainApp.save_config(_beside_app)
_after_save = json.loads(_CHAINS_CFG_FILE.read_text(encoding="utf-8"))
check("WN-M22 writing it joins the file the sync chains live in instead of rewriting it, so a version note never costs anybody a chain",
      _after_save.get("last_seen_version") == "3.5"
      and [c["sync_code"] for c in _after_save.get("hosted_chains", [])] == ["2468"]
      and _after_save.get("sync_settings", {}).get("auto_sync_interval_minutes") == 30,
      _after_save)

# The host's side of the moment both machines come up. The message itself - what it is shaped like on
# the wire, and what a beacon does when it reads one - is proved over loopback sockets in probe_sync;
# what belongs here is the deciding done by the window: which chains get named, whether a machine that
# hosts nothing or hosts nothing anybody may be told about says nothing, and what a client does with a
# message that names one of the chains it follows.
sync_requests_sent = []
chain_updates_sent = []


class _HostServerStandIn:
    """The host server as these two handlers know it: the port it answers on, or none at all."""
    def __init__(self, active_port):
        self.active_port = active_port


ASK_CFG = mod.SyncConfigManager(str(fixture("announcement config")))
ASK_VISIBLE = ASK_CFG.add_hosted_chain("Front Room", str(fixture("front room master")), "2468")
ASK_PRIVATE = ASK_CFG.add_hosted_chain("Study", str(fixture("study master")), "1357")
ASK_CFG.set_host_chain_visibility(ASK_PRIVATE["id"], False)


def _wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        time.sleep(0.02)
    return predicate()


seam.patch("send_lan_sync_request", lambda port, codes: sync_requests_sent.append((port, list(codes))))
seam.patch("send_lan_update_notification", lambda code, port: chain_updates_sent.append((code, port)))

_announce_app = AppStandIn(sync_config_manager=ASK_CFG, sync_host_server=_HostServerStandIn(63350),
                           status_signal=_StatusLine())
mod.MainApp._announce_hosted_chains_for_sync(_announce_app)
_wait_for(lambda: sync_requests_sent)
check("WN-M23 a machine that came up as a host says so once, naming the chains it advertises and the port its clients fetch from",
      len(sync_requests_sent) == 1 and sync_requests_sent[0][0] == 63350
      and sync_requests_sent[0][1] == ["2468"], sync_requests_sent)
check("WN-M24 and the status bar names the chains it asked for, which is the only notice a host gets that its clients were told anything",
      any("Front Room" in line[0] for line in _announce_app.status_signal.lines),
      _announce_app.status_signal.lines)
sync_requests_sent.clear()
_no_server_app = AppStandIn(sync_config_manager=ASK_CFG, sync_host_server=None, status_signal=_StatusLine())
mod.MainApp._announce_hosted_chains_for_sync(_no_server_app)
check("WN-M25 with nothing listening on this machine it sends nobody looking for a host that is not there, and says nothing",
      sync_requests_sent == [] and _no_server_app.status_signal.lines == [],
      (sync_requests_sent, _no_server_app.status_signal.lines))
_PRIVATE_ONLY_CFG = mod.SyncConfigManager(str(fixture("private only config")))
_PRIVATE_ONLY = _PRIVATE_ONLY_CFG.add_hosted_chain("Study Only", str(fixture("study only master")), "1357")
_PRIVATE_ONLY_CFG.set_host_chain_visibility(_PRIVATE_ONLY["id"], False)
_private_app = AppStandIn(sync_config_manager=_PRIVATE_ONLY_CFG,
                          sync_host_server=_HostServerStandIn(63350), status_signal=_StatusLine())
mod.MainApp._announce_hosted_chains_for_sync(_private_app)
check("WN-M26 a chain its owner made private is not named in it: a message sent every time somebody starts yt-msd is not how a private chain's code gets onto a network",
      sync_requests_sent == [] and _private_app.status_signal.lines == [],
      (sync_requests_sent, _private_app.status_signal.lines))
_no_chains_app = AppStandIn(sync_config_manager=mod.SyncConfigManager(str(fixture("no hosted chains"))),
                            sync_host_server=_HostServerStandIn(63350), status_signal=_StatusLine())
mod.MainApp._announce_hosted_chains_for_sync(_no_chains_app)
check("WN-M27 and a machine hosting no chain at all puts nothing on the network",
      sync_requests_sent == [], sync_requests_sent)

sync_requests_sent.clear()
chain_updates_sent.clear()
_force_all_app = AppStandIn(sync_config_manager=ASK_CFG, sync_host_server=_HostServerStandIn(63350),
                            status_signal=_StatusLine())
_force_all_dlg = QuietSyncDialog(_force_all_app)
_force_all_dlg._force_sync_all()
_wait_for(lambda: sync_requests_sent)
check("WN-M28 Force Sync All now says the same thing to those clients in its own right: one message for every chain, beside the one it has always sent for each chain",
      [code for code, _port in chain_updates_sent] == ["2468", "1357"]
      and len(sync_requests_sent) == 1 and sync_requests_sent[0][1] == ["2468"],
      (chain_updates_sent, sync_requests_sent))
sync_requests_sent.clear()
chain_updates_sent.clear()
_force_no_server = AppStandIn(sync_config_manager=ASK_CFG, sync_host_server=None, status_signal=_StatusLine())
QuietSyncDialog(_force_no_server)._force_sync_all()
check("WN-M29 and with no host server running that button still puts nothing on the network, in either message",
      sync_requests_sent == [] and chain_updates_sent == [],
      (sync_requests_sent, chain_updates_sent))


class _ClientApp(AppStandIn):
    """A main window whose client chains record the sync pass they were asked to run."""
    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.status_signal = _StatusLine()
        self.sync_passes = 0

    def _auto_sync_client_chains(self):
        self.sync_passes += 1


REQUEST_CFG = mod.SyncConfigManager(str(fixture("requested client config")))
JOINED_CHAIN = REQUEST_CFG.add_client_chain(name="Front Room Mirror",
                                            folder_path=str(fixture("front room mirror")),
                                            sync_code="2468", host_ip="192.0.2.9")
OTHER_CHAIN = REQUEST_CFG.add_client_chain(name="Study Mirror", folder_path=str(fixture("study mirror")),
                                           sync_code="9999", host_ip="192.0.2.10")

_client_asked = _ClientApp(sync_config_manager=REQUEST_CFG, sync_host_server=None)
mod.MainApp._on_lan_sync_request(_client_asked, "192.0.2.9", ["2468", "1357"])
check("WN-M30 a client that follows one of the chains named in a host's message runs its normal sync pass, and says which chain and which machine asked",
      _client_asked.sync_passes == 1
      and any("Front Room Mirror" in line[0] and "192.0.2.9" in line[0] for line in _client_asked.status_signal.lines),
      (_client_asked.sync_passes, _client_asked.status_signal.lines))
_unrelated_app = _ClientApp(sync_config_manager=REQUEST_CFG, sync_host_server=None)
mod.MainApp._on_lan_sync_request(_unrelated_app, "192.0.2.9", ["1357"])
check("WN-M31 a message naming none of the chains this machine follows starts nothing: a broadcast reaches every machine on the network, and this one has nothing to do with the machine that sent it",
      _unrelated_app.sync_passes == 0 and _unrelated_app.status_signal.lines == [],
      (_unrelated_app.sync_passes, _unrelated_app.status_signal.lines))
_no_client_app = _ClientApp(sync_config_manager=mod.SyncConfigManager(str(fixture("client no chains"))),
                            sync_host_server=None)
mod.MainApp._on_lan_sync_request(_no_client_app, "192.0.2.9", ["2468"])
_empty_ask_app = _ClientApp(sync_config_manager=REQUEST_CFG, sync_host_server=None)
mod.MainApp._on_lan_sync_request(_empty_ask_app, "192.0.2.9", [])
check("WN-M32 a machine following no chain starts nothing, and a message naming no chain at all does not ask for one",
      _no_client_app.sync_passes == 0 and _empty_ask_app.sync_passes == 0,
      (_no_client_app.sync_passes, _empty_ask_app.sync_passes))

_pyw_src = (Path(SRC_DIR) / "yt-msd-gui.pyw").read_text(encoding="utf-8")
_bootstrap_src = (Path(SRC_DIR) / "yt_msd" / "ui" / "bootstrap.py").read_text(encoding="utf-8")
_sync_handler_body = _pyw_src.split("def _on_lan_sync_request", 1)[1].split("\n    def ", 1)[0]
check("WN-M33 what a host's message starts is the ordinary auto-sync pass - the same call the periodic timer and the startup pass make - so a paused chain stays paused and a chain bound to another wireless network stays bound",
      "self._auto_sync_client_chains()" in _sync_handler_body
      and "QTimer.singleShot(2500, self._auto_sync_client_chains)" in _bootstrap_src
      and "def _auto_sync_client_chains" in _pyw_src,
      _sync_handler_body)
check("WN-M34 the wait before a host speaks is twenty seconds, and it lives beside the other sync timings rather than inside the window that uses it",
      _SYNC_REQUEST_DELAY == 20000
      and "yt_msd.sync.lan" in seam.owned_by("HOST_UP_SYNC_REQUEST_DELAY_MS"),
      (_SYNC_REQUEST_DELAY, seam.owned_by("HOST_UP_SYNC_REQUEST_DELAY_MS")))
check("WN-M35 the startup arms that announcement with the constant rather than a second copy of the number, and wires the beacon to read what comes back",
      "QTimer.singleShot(HOST_UP_SYNC_REQUEST_DELAY_MS, self._announce_hosted_chains_for_sync)" in _bootstrap_src
      and "on_sync_request_cb=self._on_lan_sync_request" in _bootstrap_src,
      [line.strip() for line in _bootstrap_src.splitlines()
       if "sync_request" in line or "_announce_hosted_chains_for_sync" in line])
check("WN-M36 the version box is armed from the startup the same way - a timer, not a box that holds the window open - and the record it compares against starts out empty",
      "QTimer.singleShot(2600, self._show_version_notes)" in _bootstrap_src
      and "self.last_seen_version" in _bootstrap_src
      and "c.get('last_seen_version'" in _pyw_src and "'last_seen_version': getattr(self" in _pyw_src,
      [line.strip() for line in _bootstrap_src.splitlines() if "version" in line])
check("WN-M37 all three handlers belong to the main window, so a beacon thread and a startup timer reach them the way they reach the chain update handler they sit beside",
      all(hasattr(mod.MainApp, name) for name in ("_show_version_notes", "_announce_hosted_chains_for_sync",
                                                  "_on_lan_sync_request", "_on_lan_chain_updated")),
      [name for name in ("_show_version_notes", "_announce_hosted_chains_for_sync",
                         "_on_lan_sync_request") if not hasattr(mod.MainApp, name)])
_new_names = ("send_lan_sync_request", "version_notes_are_due", "release_notes_url",
              "HOST_UP_SYNC_REQUEST_DELAY_MS", "VersionNotesDialog")
check("WN-M38 every name this feature added is a module-level one the seam reaches, and none of them is held only by the entry point",
      all(seam.owned_by(name) and any(owner != mod.__name__ for owner in seam.owned_by(name))
          for name in _new_names),
      {name: seam.owned_by(name) for name in _new_names})
_real_sync_sender = seam.original("send_lan_sync_request")
seam.restore("send_lan_sync_request")
seam.restore("send_lan_update_notification")
check("WN-M39 both senders this section stood in for are back with the program, and the copy the window reads is the real one",
      not seam.is_patched("send_lan_sync_request") and not seam.is_patched("send_lan_update_notification")
      and mod.send_lan_sync_request is _real_sync_sender
      and "yt_msd.sync.discovery" in seam.owned_by("send_lan_sync_request"),
      seam.owned_by("send_lan_sync_request"))

# ===========================================================================
# WN-N: putting another machine's config on this one
# ===========================================================================
# Two ways a settings file written by another copy of yt-msd arrives on this machine: the Import button
# in the settings window taking a bare gui_config.json, and the button on a client chain's card asking
# the host at the other end of that chain for the settings it runs with. What belongs to those two
# windows is proved here - which keys cross from one machine to another and which do not, what a file
# has to be before it is taken for a settings file at all, and whether a config that arrives actually
# stays arrived once the window has taken it. Which settings a client chain may ask for, and what a host
# is willing to hand over, is proved over loopback sockets in probe_sync's SY-S.
build_host_config_import = mod.build_host_config_import
read_settings_file = mod.read_settings_file

OURS = {
    "format": "mp3", "bitrate": "192", "mode": "Dark", "accent": "Blue", "volume": 100,
    "last_search": "my own search", "recent_playlists": [{"name": "My playlist"}],
    "normalization_mode": "ask", "silence_pad_dur": 2.0, "download_threads": 3,
    "disable_update_checks": False, "save_place": False, "splitter_sizes": [300, 800, 300],
    "hosted_chains": [{"id": "hc_1111", "sync_code": "1111", "name": "This PC Hosts"}],
    "client_chains": [{"id": "cc_2468", "sync_code": "2468", "name": "This PC Follows",
                       "folder_path": "C:\\Our Music"}],
    "sync_settings": {"auto_sync_interval_mins": 30},
    "folders": ["C:\\Our Downloads"], "local_folders": ["C:\\Our Music"],
    "local_current_path": "C:\\Our Music", "renamer_path": "C:\\Our Tools\\renamer.py",
    "custom_script_path": "C:\\Our Tools\\script.py", "last_seen_version": "3.4",
    "session_data": {"search_results": [{"video_id": "ours"}], "playback_index": 1,
                     "local_current_path": "C:\\Our Music", "local_playback_index": 3},
}
THEIRS = {
    "format": "m4a", "bitrate": "320", "mode": "Light", "accent": "Green", "volume": 42,
    "last_search": "their search", "recent_playlists": [{"name": "Their playlist"}],
    "normalization_mode": "on", "silence_pad_dur": 5.0, "download_threads": 7,
    "disable_update_checks": True, "save_place": True, "splitter_sizes": [200, 700, 400],
    "hosted_chains": [{"id": "hc_7002", "sync_code": "7002", "name": "Their PC Hosts"}],
    "client_chains": [{"id": "cc_8888", "sync_code": "8888", "name": "Their PC Follows",
                       "folder_path": "D:\\Their Music"}],
    "sync_settings": {"auto_sync_interval_mins": 11},
    "folders": ["D:\\Their Downloads"], "local_folders": ["D:\\Their Music"],
    "local_current_path": "D:\\Their Music", "renamer_path": "D:\\Their Tools\\renamer.py",
    "custom_script_path": "D:\\Their Tools\\script.py", "last_seen_version": "3.5",
    "session_data": {"search_results": [{"video_id": "theirs"}], "playback_index": 6,
                     "local_current_path": "D:\\Their Music", "local_playback_index": 8},
    "a_setting_this_build_has_never_heard_of": "carried across anyway",
}
MERGED_HOST = build_host_config_import(OURS, THEIRS)

_MERGED_KEYS = ("format", "bitrate", "mode", "accent", "volume", "last_search", "recent_playlists",
                "normalization_mode", "silence_pad_dur", "download_threads", "disable_update_checks",
                "save_place", "splitter_sizes")
check("WN-N1 a host's settings land here for everything that is a setting: the theme, the accent, the volume, the format and bitrate, the saved playlist, the saved search, the normalisation, the thread counts, the update opt-out, the layout-save choice and the panel widths",
      [MERGED_HOST[key] for key in _MERGED_KEYS] == [THEIRS[key] for key in _MERGED_KEYS],
      {key: MERGED_HOST.get(key) for key in ("format", "mode", "volume", "download_threads")})
check("WN-N2 the chains stay this machine's own: the chains it hosts, the chains it follows, and the interval and options it syncs them on are read back out of its own settings and not out of the host's",
      MERGED_HOST["hosted_chains"] == OURS["hosted_chains"]
      and MERGED_HOST["client_chains"] == OURS["client_chains"]
      and MERGED_HOST["sync_settings"] == OURS["sync_settings"],
      (MERGED_HOST["client_chains"], THEIRS["client_chains"]))
check("WN-N3 so do the local file paths: the download folders, the file-browser folders, the folder open in it, and the renamer and custom-script paths this machine runs",
      MERGED_HOST["folders"] == OURS["folders"]
      and MERGED_HOST["local_folders"] == OURS["local_folders"]
      and MERGED_HOST["local_current_path"] == OURS["local_current_path"]
      and MERGED_HOST["renamer_path"] == OURS["renamer_path"]
      and MERGED_HOST["custom_script_path"] == OURS["custom_script_path"],
      {key: MERGED_HOST.get(key) for key in ("folders", "local_current_path", "renamer_path")})
check("WN-N4 no path belonging to the other machine is left anywhere in the settings this machine ends up with",
      "Their Downloads" not in json.dumps(MERGED_HOST) and "Their Music" not in json.dumps(MERGED_HOST)
      and "Their Tools" not in json.dumps(MERGED_HOST),
      [key for key, value in MERGED_HOST.items() if "Their" in json.dumps(value)])
check("WN-N5 the record of which version this copy has already told its user about is its own, because what a host has already reported about itself is nothing this machine can learn from",
      MERGED_HOST["last_seen_version"] == "3.4", MERGED_HOST["last_seen_version"])
check("WN-N6 the host's saved session comes across with its search results and where in them it stopped, and loses the two entries that named places on the host's own disk",
      MERGED_HOST["session_data"]["search_results"] == [{"video_id": "theirs"}]
      and MERGED_HOST["session_data"]["playback_index"] == 6
      and "local_current_path" not in MERGED_HOST["session_data"]
      and "local_playback_index" not in MERGED_HOST["session_data"],
      MERGED_HOST["session_data"])
check("WN-N7 a setting the host's file does not name is missing from the result rather than kept from the file it replaces - which is how this program already reads a settings file, since load_config() takes a key it cannot find as the value it would have started with, so a setting from before the import cannot survive behind a config that claims to be the host's",
      build_host_config_import({"volume": 11, "accent": "Red"}, {"accent": "Green"}) == {"accent": "Green"}
      and "volume" not in build_host_config_import({"volume": 11}, {"accent": "Green"}),
      build_host_config_import({"volume": 11, "accent": "Red"}, {"accent": "Green"}))
check("WN-N8 a key this build has never heard of travels with the settings that carried it, so a config written by a newer copy is not quietly edited down by an older one",
      MERGED_HOST["a_setting_this_build_has_never_heard_of"] == "carried across anyway",
      sorted(MERGED_HOST))
check("WN-N9 neither side's settings are edited on the way through: the settings that arrived and the settings this machine already had are the same as they were afterwards as before",
      THEIRS["session_data"]["local_current_path"] == "D:\\Their Music"
      and OURS["client_chains"][0]["folder_path"] == "C:\\Our Music"
      and THEIRS["hosted_chains"][0]["name"] == "Their PC Hosts",
      (THEIRS["session_data"], OURS["client_chains"]))
check("WN-N10 what an import refuses to copy across is written down in one list, beside the sync-chain keys the export already owned",
      set(mod.MACHINE_OWN_CONFIG_KEYS) == {"hosted_chains", "client_chains", "sync_settings", "folders",
                                           "local_folders", "local_current_path", "renamer_path",
                                           "custom_script_path", "last_seen_version"}
      and all(key in mod.MACHINE_OWN_CONFIG_KEYS for key in mod.SYNC_ONLY_CONFIG_KEYS)
      and set(mod.SESSION_LOCAL_PATH_KEYS) == {"local_current_path", "local_playback_index"},
      (mod.MACHINE_OWN_CONFIG_KEYS, mod.SESSION_LOCAL_PATH_KEYS))

# What a file has to be before it is taken for a settings file at all. An import throws away every
# setting this machine has, so the reading is where a file that is not one is stopped.
_READ_DIR = fixture("settings file readings")
_READ_GOOD = _READ_DIR / "gui_config.json"
_READ_GOOD.write_text(json.dumps(THEIRS), encoding="utf-8")
check("WN-N11 a settings file written by another copy reads back whole, including the chains and folders that this import will go on to copy across",
      read_settings_file(_READ_GOOD) == THEIRS, sorted(read_settings_file(_READ_GOOD)))
(_READ_DIR / "not-json.json").write_text("{this is not json", encoding="utf-8")
(_READ_DIR / "list.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
(_READ_DIR / "empty.json").write_text("{}", encoding="utf-8")
(_READ_DIR / "somebody-else-s-data.json").write_text(json.dumps({"dependencies": {"left-pad": "1.0"}}),
                                                     encoding="utf-8")
_READ_REFUSALS = {}
for _refusal_name in ("not-json.json", "list.json", "empty.json", "somebody-else-s-data.json"):
    try:
        read_settings_file(_READ_DIR / _refusal_name)
        _READ_REFUSALS[_refusal_name] = "accepted it"
    except ValueError as exc:
        _READ_REFUSALS[_refusal_name] = str(exc)
check("WN-N12 a file that is not JSON, not an object, empty, or an object naming nothing this program writes, is refused with the reason a confirmation box could show",
      all(reason != "accepted it" for reason in _READ_REFUSALS.values())
      and "not JSON" in _READ_REFUSALS["not-json.json"]
      and "not a settings object" in _READ_REFUSALS["list.json"]
      and "empty" in _READ_REFUSALS["empty.json"]
      and "not a yt-msd settings file" in _READ_REFUSALS["somebody-else-s-data.json"],
      _READ_REFUSALS)
try:
    read_settings_file(_READ_DIR / "no-such-file.json")
    _READ_MISSING = "accepted it"
except ValueError as exc:
    _READ_MISSING = str(exc)
check("WN-N13 a file that is not there is reported as that rather than as an empty settings file",
      "could not be read" in _READ_MISSING, _READ_MISSING)


# Now the arrival: an imported config put onto a window, and read back out of the file that window
# writes. This is the part the reset-to-defaults once got wrong - a file written, and every setting the
# window was still holding written straight back over it - so it is proved with the real save_config and
# the real load_config against a real settings file, and with the real controls save_config reads its
# format, its bitrate, its search text, its ticks and its panel widths out of.
class _TuningStandIn:
    """The renamer's shared tuning settings, recorded instead of changed."""
    pushed = []

    @classmethod
    def from_settings(cls, trim, pad, custom_cmd_on, custom_cmd):
        cls.pushed.append((trim, pad, custom_cmd_on, custom_cmd))

    @classmethod
    def reset(cls):
        cls.pushed.append(("reset",))


class _ImportApp(_SavedConfigApp):
    """A main window holding a real settings file, the real save_config and load_config, and the real
    controls those two read - which is what a settings import has to leave in agreement."""

    def __init__(self, config_path, **overrides):
        super().__init__(config_path)
        from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QSlider, QSplitter
        self.format_combo = QComboBox()
        self.format_combo.addItems([str(item) for item in mod.DOWNLOAD_FORMATS])
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["128", "192", "256", "320"])
        self.path_combo = QComboBox()
        self.search_entry = QLineEdit()
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.local_meta_cb = QCheckBox()
        self.run_renamer_cb = QCheckBox()
        self.channel_prefix_cb = QCheckBox()
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(QWidget())
        self.main_splitter.addWidget(QWidget())
        self.content_splitter = QSplitter(Qt.Horizontal)
        self.content_splitter.addWidget(QWidget())
        self.content_splitter.addWidget(QWidget())
        self.recent_playlists = [{"name": "My playlist"}]
        self.accent_color_name = "Blue"
        self.appearance_mode = "Dark"
        self.last_search = "my own search"
        self.volume_val = 100
        self.recent_folders = ["C:\\Our Downloads"]
        self.download_path = "C:\\Our Downloads"
        self.local_folders = ["C:\\Our Music"]
        self.local_current_path = "C:\\Our Music"
        self.renamer_path = "C:\\Our Tools\\renamer.py"
        self.custom_script_path = "C:\\Our Tools\\script.py"
        self.show_local_metadata = False
        self.channel_prefix_rename = True
        self.splitter_sizes = [300, 800, 300]
        self.normalization_mode = "ask"
        self.silence_pad_dur = 2.0
        self.download_threads = 3
        self.disable_update_checks = False
        self.save_place = False
        self.last_seen_version = "3.4"
        self.format_combo.setCurrentText("mp3")
        self.bitrate_combo.setCurrentText("192")
        self.search_entry.setText(self.last_search)
        self.vol_slider.setValue(100)
        self.calls = []
        self.status_lines = []
        self.sync_threads = {}
        self.sync_progress_state = {}
        self.sync_manager_dialog = None
        self.sync_host_server = None
        self._config_import_busy = False
        self._export_import_busy = False
        self.sync_config_manager = None
        for key, value in overrides.items():
            setattr(self, key, value)

    def _note(self, name):
        self.calls.append(name)

    def _on_status_update(self, text, sticky=False, color=""):
        self.status_lines.append((text, sticky, color))

    def apply_theme(self):
        self._note("apply_theme")

    def set_local_explorer_address(self, path, add_to_recent=False):
        self._note("set_local_explorer_address")
        self.local_explorer_shown = path

    def refresh_local_list(self):
        self._note("refresh_local_list")

    def _update_local_rescan_timer(self):
        self._note("_update_local_rescan_timer")

    def _update_sync_timer(self):
        self._note("_update_sync_timer")

    def refresh_sync_watchers(self):
        self._note("refresh_sync_watchers")

    def save_config(self):
        mod.MainApp.save_config(self)

    def load_config(self):
        mod.MainApp.load_config(self)

    def _config_payload_for_host(self):
        return mod.MainApp._config_payload_for_host(self)

    def _current_config_snapshot(self):
        return mod.MainApp._current_config_snapshot(self)

    def _write_settings_file(self, payload):
        return mod.MainApp._write_settings_file(self, payload)

    def _reload_settings_into_ui(self):
        mod.MainApp._reload_settings_into_ui(self)

    def _start_bare_config_import(self, json_path):
        mod.MainApp._start_bare_config_import(self, json_path)

    def _bare_config_worker(self, json_path):
        mod.MainApp._bare_config_worker(self, json_path)

    def _on_config_file_read(self, json_path, payload):
        mod.MainApp._on_config_file_read(self, json_path, payload)

    def import_config_from_host(self, chain_config):
        mod.MainApp.import_config_from_host(self, chain_config)

    def _on_host_config_fetched(self, ok, message, payload, chain_config):
        mod.MainApp._on_host_config_fetched(self, ok, message, payload, chain_config)

    def _apply_whole_config_import(self, payload, source_label, keep_own_keys):
        return mod.MainApp._apply_whole_config_import(self, dict(payload), source_label, keep_own_keys)


class _RunningSync:
    """A chain mid-sync: the one thing that makes an import wait."""

    def __init__(self, running=True):
        self._running = running

    def isRunning(self):
        return self._running


def _import_config_dir(name):
    """A settings file to import onto, in its own folder, with this machine's own settings in it."""
    folder = fixture(name)
    cfg = dict(OURS)
    (folder / "gui_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return folder, folder / "gui_config.json"


class _RecordingSplitter(QSplitter):
    """A panel divider that remembers the arrangement it was given.

    A real QSplitter that has never been shown rescales what it is asked for, so the check below is
    about what the import asked the window for and what the window kept privately afterwards - not
    about how Qt lays out two empty panels.
    """

    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.requested_sizes = []
        self._last_custom_sizes = [999, 999]

    def setSizes(self, sizes):
        self.requested_sizes.append(list(sizes))

    def sizes(self):
        # save_config() reads the panel widths straight back off these two, so a divider that never
        # showed has to answer with the widths it was last asked for rather than with nothing.
        return list(self.requested_sizes[-1]) if self.requested_sizes else list(self._last_custom_sizes)


class _ConfigImportApp(_ImportApp):
    """A window with a settings file of its own, and the two import paths wired the way the real one is."""

    def __init__(self, name, **overrides):
        _folder, _cfg_path = _import_config_dir(name)
        super().__init__(_cfg_path, **overrides)
        self.settings_dir = _folder
        self.config_file = _cfg_path
        self.main_splitter = _RecordingSplitter()
        self.content_splitter = _RecordingSplitter()
        self.import_failed_signal = _RecordingEmit()
        self.config_file_ready_signal = _RecordingEmit()
        self.status_signal = _RecordingEmit()
        # A settings import rearms the local pane's auto-rescan through this attribute, exactly the way
        # load_config does: without it the window simply has no timer to rearm, and the check below
        # would be about a stand-in rather than about what the import asked for.
        self.local_rescan_timer = object()
        self.settings_dialog = None
        self.fetched = []
        self.fetch_started = []

    def read_file(self):
        return json.loads(self.config_file.read_text(encoding="utf-8"))

    def imported(self, payload, source, keep_own_keys):
        """One whole-config import onto this window, with the renamer's tuning settings recorded."""
        with seam.patched("TUNING", _TuningStandIn):
            return mod.MainApp._apply_whole_config_import(self, dict(payload), source, keep_own_keys)


# The settings file a client-chain import produces. This is the check that matters most here, because
# it is the one the reset-to-defaults once failed: a settings file written, and every setting the window
# was still holding written straight back over it by the next save.
_CHECKED_SETTINGS = ("format", "mode", "accent", "volume", "download_threads", "silence_pad_dur",
                     "recent_playlists", "last_search", "disable_update_checks", "normalization_mode",
                     "save_place", "bitrate")
_host_import_app = _ConfigImportApp("host config import")
with seam.patched("TUNING", _TuningStandIn):
    mod.MainApp._apply_whole_config_import(_host_import_app, dict(THEIRS),
                                           "the host of sync chain 'Front Room'", True)
_after_host_import = _host_import_app.read_file()
check("WN-N14 a host's settings are written into this machine's settings file, whole, while this machine's own chains and paths are still in there",
      all(_after_host_import[key] == THEIRS[key] for key in _CHECKED_SETTINGS)
      and _after_host_import["hosted_chains"] == OURS["hosted_chains"]
      and _after_host_import["client_chains"] == OURS["client_chains"]
      and _after_host_import["sync_settings"] == OURS["sync_settings"]
      and _after_host_import["folders"] == OURS["folders"]
      and _after_host_import["local_folders"] == OURS["local_folders"]
      and _after_host_import["local_current_path"] == OURS["local_current_path"]
      and _after_host_import["renamer_path"] == OURS["renamer_path"]
      and _after_host_import["custom_script_path"] == OURS["custom_script_path"]
      and _after_host_import["last_seen_version"] == "3.4",
      _after_host_import)
check("WN-N15 and they stay written: this window is asked to save its settings again straight afterwards - the thing every settings window, every download and every close does - and the file still says what the host's settings said. A reset to defaults once failed in exactly this way, and it is why the file is written first and then read back into the window and into the controls the window saves out of",
      (_host_import_app.save_config(), all(_host_import_app.read_file()[key] == THEIRS[key]
                                           for key in _CHECKED_SETTINGS))[1],
      {key: (_after_host_import[key], _host_import_app.read_file()[key]) for key in _CHECKED_SETTINGS})
check("WN-N16 and the settings that stayed this machine's own are still its own after that save, because the controls holding them were filled from them and not from the host",
      _host_import_app.read_file()["folders"] == OURS["folders"]
      and _host_import_app.read_file()["local_folders"] == OURS["local_folders"]
      and _host_import_app.read_file()["local_current_path"] == OURS["local_current_path"]
      and _host_import_app.read_file()["renamer_path"] == OURS["renamer_path"]
      and _host_import_app.read_file()["last_seen_version"] == "3.4",
      _host_import_app.read_file())
check("WN-N17 the window itself took the imported settings and not only the file: the attributes load_config owns, the controls save_config reads its format, bitrate and saved search out of, and the widths each panel divider is asked for",
      _host_import_app.format_var == "m4a" and _host_import_app.bitrate_var == "320"
      and _host_import_app.appearance_mode == "Light" and _host_import_app.accent_color_name == "Green"
      and _host_import_app.volume_val == 42 and _host_import_app.download_threads == 7
      and _host_import_app.silence_pad_dur == 5.0 and _host_import_app.normalization_mode == "on"
      and _host_import_app.disable_update_checks is True
      and _host_import_app.format_combo.currentText() == "m4a"
      and _host_import_app.bitrate_combo.currentText() == "320"
      and _host_import_app.search_entry.text() == "their search"
      and _host_import_app.vol_slider.value() == 42
      and _host_import_app.main_splitter.requested_sizes == [[200, 1100]]
      and _host_import_app.content_splitter.requested_sizes == [[700, 400]],
      (_host_import_app.format_combo.currentText(), _host_import_app.search_entry.text(),
       _host_import_app.main_splitter.requested_sizes))
check("WN-N18 the arrangement the host's config named is what each panel divider keeps from then on: the widths this machine had arranged for itself privately are dropped, so a double-click on a handle cannot bring the old layout back over the imported one",
      _host_import_app.main_splitter._last_custom_sizes == []
      and _host_import_app.content_splitter._last_custom_sizes == [],
      (_host_import_app.main_splitter._last_custom_sizes,
       _host_import_app.content_splitter._last_custom_sizes))
check("WN-N19 the theme was re-applied, the local pane was re-pointed at this machine's own folder and re-scanned, the auto-rescan timer was rearmed, and the sync timer and the hosted-folder watchers were re-made from the chains this machine kept",
      all(name in _host_import_app.calls for name in ("apply_theme", "set_local_explorer_address",
                                                      "refresh_local_list", "_update_local_rescan_timer",
                                                      "_update_sync_timer", "refresh_sync_watchers"))
      and _host_import_app.local_explorer_shown == OURS["local_current_path"],
      _host_import_app.calls)
check("WN-N20 and the renamer's half of the program is told: an imported pad or trim reaches the shared tuning settings the renamer reads, and not only the window that downloaded the file",
      _TuningStandIn.pushed[-1] == (True, 5.0, False, ""), _TuningStandIn.pushed)
check("WN-N21 the status line says what was imported and which things were left alone, because a config that changed underneath somebody is the sort of thing they have to be told about",
      any("Imported settings from the host of sync chain 'Front Room'" in line[0]
          and "sync chains" in line[0] and "left exactly as they were" in line[0]
          for line in _host_import_app.status_lines),
      _host_import_app.status_lines)

# The settings-file import: the same arrival with nothing held back. A file picked out of a folder
# becomes this machine's settings, its chains included.
_bare_app = _ConfigImportApp("bare config import")
# The manager the real window is given: the same folder, so the same gui_config.json the import writes.
# A chain list kept in some other file would let this check pass while the live window kept the old one.
_bare_manager = mod.SyncConfigManager(str(_bare_app.settings_dir))
_bare_before = ([chain["sync_code"] for chain in _bare_manager.hosted_chains],
                [chain["sync_code"] for chain in _bare_manager.client_chains])
_bare_app.sync_config_manager = _bare_manager
_bare_result = _bare_app.imported(THEIRS, "gui_config.json", False)
_after_bare = _bare_app.read_file()
check("WN-N22 a bare settings file is taken exactly as it stands: every setting in it lands here, the chains it named are now this machine's chains, and its paths are now this machine's paths",
      _bare_result is True and _after_bare["format"] == "m4a" and _after_bare["volume"] == 42
      and _after_bare["folders"] == ["D:\\Their Downloads"]
      and _after_bare["local_current_path"] == "D:\\Their Music"
      and _after_bare["renamer_path"] == "D:\\Their Tools\\renamer.py"
      and _after_bare["session_data"]["local_current_path"] == "D:\\Their Music"
      and [chain["sync_code"] for chain in _after_bare["hosted_chains"]] == ["7002"]
      and [chain["sync_code"] for chain in _after_bare["client_chains"]] == ["8888"]
      and _after_bare["sync_settings"] == {"auto_sync_interval_mins": 11},
      _after_bare)
check("WN-N23 the chains this machine had are gone from the file and from the manager that runs them: the live copies are emptied before the new file is read back, which is the other way a reset to defaults once left behind every chain it claimed to remove",
      _bare_before == (["1111"], ["2468"])
      and [chain["sync_code"] for chain in _bare_manager.hosted_chains] == ["7002"]
      and [chain["sync_code"] for chain in _bare_manager.client_chains] == ["8888"]
      and "This PC Hosts" not in json.dumps([_bare_manager.hosted_chains,
                                             _bare_manager.client_chains]),
      (_bare_before, _bare_manager.hosted_chains, _bare_manager.client_chains))
_bare_app.save_config()
_after_bare_save = _bare_app.read_file()
check("WN-N24 and it reads as this machine's own settings afterwards: the window saves, and the folders and chains that came with the imported file are still the ones on disk - the local pane was re-pointed at the folder the imported file named, because that is the folder this machine now runs on",
      _after_bare_save["folders"] == ["D:\\Their Downloads"]
      and _after_bare_save["local_current_path"] == "D:\\Their Music"
      and _after_bare_save["format"] == "m4a" and _after_bare_save["volume"] == 42
      and _after_bare_save["last_seen_version"] == "3.5"
      and [chain["sync_code"] for chain in _after_bare_save["hosted_chains"]] == ["7002"]
      and _bare_app.local_explorer_shown == "D:\\Their Music",
      _after_bare_save)
check("WN-N25 its status line names the file and says the chains came with it, since a machine that suddenly hosts somebody else's chain has to be told that happened",
      any("Imported settings from gui_config.json" in line[0] and "now this machine's chains" in line[0]
          for line in _bare_app.status_lines),
      _bare_app.status_lines)


# The asking: what a user is told before any of the above is allowed to happen, and what is not written
# until somebody says yes. The fetch itself is proved over loopback sockets in probe_sync's SY-S; what
# belongs here is the confirmation and the guards around it.
_FETCH_STARTED = []


class _FetchSignal:
    """A signal on a fetch thread, wired the way a real one is: connections, then emissions."""

    def __init__(self):
        self.handlers = []
        self.emitted = []

    def connect(self, handler):
        self.handlers.append(handler)

    def emit(self, *args):
        self.emitted.append(args)
        for handler in list(self.handlers):
            handler(*args)


class _FetchStandIn:
    """The chain's host, asked for its settings, as this suite runs it: nothing on the network at all."""

    def __init__(self, chain_config):
        self.chain_config = chain_config
        self.status_signal = _FetchSignal()
        self.finished_signal = _FetchSignal()

    def start(self):
        _FETCH_STARTED.append(dict(self.chain_config))

    def answer(self, ok, message, payload):
        """Hand this fetch the answer a host gave, and let the window take it the way it really would."""
        self.finished_signal.emit(ok, message, payload)


HOST_CHAIN_RECORD = {"id": "cc_2468", "sync_code": "2468", "name": "Front Room",
                     "folder_path": "C:\\Our Music", "last_known_host_ip": "192.0.2.9"}


def _asking(answer_yes, drive):
    """Run `drive` with the fetch thread stood in for, and every confirmation answered `answer_yes`."""
    with seam.patched("HostConfigFetchThread", _FetchStandIn):
        return answering(answer_yes, drive)


_refused_app = _ConfigImportApp("host import refused")
_refused_app.sync_threads = {"cc_2468": _RunningSync()}
_asking(True, lambda: mod.MainApp.import_config_from_host(_refused_app, dict(HOST_CHAIN_RECORD)))
check("WN-N26 with a sync running there is no question to answer and nothing is fetched: a chain mid-sync is working from the chain record and the folder rule an import is about to replace",
      _FETCH_STARTED == [] and _refused_app._config_import_busy is False
      and any("a sync is running" in line[0] for line in _refused_app.status_lines)
      and _refused_app.read_file() == OURS,
      (_FETCH_STARTED, _refused_app.status_lines))

_answered_app = _ConfigImportApp("host import asked")
_asking(False, lambda: mod.MainApp.import_config_from_host(_answered_app,
                                                           dict(HOST_CHAIN_RECORD)))
_what_it_asked = _Answers.asked[0] if _Answers.asked else ("", "", ())
check("WN-N27 a host chosen from the Sync window's menu asks first, defaults to No, and says in the question itself that it overwrites the entire config and that there is no undoing it - the two things a menu entry on a chain window cannot be trusted to be obvious about",
      bool(_Answers.asked) and _what_it_asked[2] == (_Answers.Yes | _Answers.No, _Answers.No)
      and _FETCH_STARTED == []
      and "Import Settings From Host" in _what_it_asked[0]
      and "overwrites your entire config" in _what_it_asked[1]
      and "no undoing it" in _what_it_asked[1]
      and _answered_app.read_file() == OURS and _answered_app._config_import_busy is False,
      (_Answers.asked, _FETCH_STARTED, _answered_app.status_lines))
check("WN-N28 and the same question names the two things that will not be overwritten, because somebody deciding whether to press Yes has to be able to tell what they are keeping",
      "sync chains" in _what_it_asked[1] and "local file paths" in _what_it_asked[1]
      and "Front Room" in _what_it_asked[1] and "192.0.2.9" in _what_it_asked[1],
      _what_it_asked[1])

_yes_app = _ConfigImportApp("host import accepted")
_asking(True, lambda: mod.MainApp.import_config_from_host(_yes_app, dict(HOST_CHAIN_RECORD)))
check("WN-N29 said yes, the fetch is what runs: the chain as this machine holds it, handed to the client half of a chain, and nothing written to this machine's settings out of the answer alone",
      _FETCH_STARTED == [HOST_CHAIN_RECORD] and _yes_app._config_import_busy is True
      and _yes_app.read_file() == OURS,
      (_FETCH_STARTED, _yes_app.read_file()))
mod.MainApp._on_host_config_fetched(_yes_app, False, "Settings refused by the host: this host does not "
                                    "offer its settings. Nothing here was changed.", None,
                                    dict(HOST_CHAIN_RECORD))
check("WN-N30 a host that refuses is reported as refusing, the import is over rather than left waiting, and this machine's settings file is exactly what it was",
      _yes_app.read_file() == OURS and _yes_app._config_import_busy is False
      and any("Settings not imported from Front Room" in line[0]
              and "does not offer its settings" in line[0] for line in _yes_app.status_lines),
      (_yes_app.read_file(), _yes_app.status_lines))

# The settings-file path: read first, ask second, write last.
_bad_dir = fixture("a file that is not settings")
_bad_file = _bad_dir / "package.json"
_bad_file.write_text(json.dumps({"name": "somebody-else-s-project"}), encoding="utf-8")
_good_file = _bad_dir / "gui_config.json"
_good_file.write_text(json.dumps(THEIRS), encoding="utf-8")

_read_failed_app = _ConfigImportApp("bare import bad file")
mod.MainApp._bare_config_worker(_read_failed_app, str(_bad_file))
check("WN-N31 a file that is not a yt-msd settings file is refused on the reading thread before anything is asked about it, and the reason it is not one is what the user is told",
      _read_failed_app.read_file() == OURS and _read_failed_app._config_import_busy is False
      and _read_failed_app.config_file_ready_signal.emitted == []
      and len(_read_failed_app.import_failed_signal.emitted) == 1
      and "not a yt-msd settings file" in _read_failed_app.import_failed_signal.emitted[0][0]
      and "names none of the settings" in _read_failed_app.import_failed_signal.emitted[0][0],
      (_read_failed_app.import_failed_signal.emitted, _read_failed_app.read_file()))

_read_ready_app = _ConfigImportApp("bare import good file")
mod.MainApp._bare_config_worker(_read_ready_app, str(_good_file))
check("WN-N32 a settings file that does read all right comes back through the signal the window confirms on, with the path it came from and the settings it named, and nothing has been written yet - the confirmation comes before the writing",
      _read_ready_app.config_file_ready_signal.emitted == [(str(_good_file), THEIRS)]
      and _read_ready_app.read_file() == OURS and _read_ready_app.import_failed_signal.emitted == [],
      (_read_ready_app.config_file_ready_signal.emitted, _read_ready_app.read_file()))

_said_no_app = _ConfigImportApp("bare import said no")
answering(False, lambda: mod.MainApp._on_config_file_read(_said_no_app, str(_good_file), dict(THEIRS)))
_what_it_asked_about = _Answers.asked[0] if _Answers.asked else ("", "")
check("WN-N33 a settings file is written only once somebody has said yes to the file that was actually found, and the question names what is about to be replaced and what a file with chains in it will do to this machine",
      _said_no_app.read_file() == OURS and _said_no_app._config_import_busy is False
      and "Overwrite Settings With This File" in _what_it_asked_about[0]
      and "no undoing it" in _what_it_asked_about[1],
      (_Answers.asked, _said_no_app.read_file()))

_no_chains_file = _bad_dir / "no-chains.json"
_no_chains_file.write_text(json.dumps({"format": "m4a", "volume": 9}), encoding="utf-8")
_said_yes_app = _ConfigImportApp("bare import said yes")
mod.MainApp._bare_config_worker(_said_yes_app, str(_no_chains_file))
answering(True, lambda: mod.MainApp._on_config_file_read(_said_yes_app, str(_no_chains_file),
                                                         read_settings_file(_no_chains_file)))
check("WN-N34 a settings file naming no chains says so in the question and leaves this machine hosting none and following none afterwards, because a machine that silently loses its chains is the thing an import has to warn about",
      any("names no sync chains" in asked[1] for asked in _Answers.asked)
      and _said_yes_app.read_file()["format"] == "m4a"
      and _said_yes_app.read_file().get("hosted_chains") is None
      and _said_yes_app.read_file().get("client_chains") is None,
      (_Answers.asked, _said_yes_app.read_file()))

_busy_app = _ConfigImportApp("import while busy")
_busy_app._export_import_busy = True
_fetches_before_this_one = len(_FETCH_STARTED)
_asking(True, lambda: mod.MainApp.import_config_from_host(_busy_app, dict(HOST_CHAIN_RECORD)))
check("WN-N35 a settings import and a package import or export take turns with each other: a settings file picked out of a folder and a settings file fetched off a chain both write over the same settings, so only one of them runs at a time",
      len(_FETCH_STARTED) == _fetches_before_this_one and _busy_app.read_file() == OURS
      and _busy_app._config_import_busy is False
      and any("import or export is already running" in line[0] for line in _busy_app.status_lines),
      _busy_app.status_lines)

_blocked_app = _ConfigImportApp("import onto a running sync")
_blocked_app.sync_threads = {"cc_other": _RunningSync()}
_bare_blocked = _blocked_app.imported(THEIRS, "gui_config.json", False)
check("WN-N36 and an import that has already been agreed is refused at the last moment if a sync started in the meantime - the file is not written, and the window says that it stopped rather than saying it finished",
      _bare_blocked is False and _blocked_app.read_file() == OURS
      and any("A sync is running. Nothing was imported." in line[0]
              for line in _blocked_app.status_lines),
      (_blocked_app.read_file(), _blocked_app.status_lines))

_settings_open_app = _ConfigImportApp("import with settings window open")
_settings_open_app.settings_dialog = QWidget()
_settings_open_app.imported(THEIRS, "gui_config.json", False)
check("WN-N37 a settings window left open while its own settings are replaced is closed, because the cached one reads these values only when it is built and would go on writing the settings it still shows back into the file",
      _settings_open_app.settings_dialog is None
      and _settings_open_app.read_file()["format"] == "m4a",
      _settings_open_app.settings_dialog)

# The Import button in the settings window takes a bare gui_config.json beside a package, and hands it
# to the main window rather than to the package reader.
_import_choice_app = _ConfigImportApp("import dialog choice")
_picked_filters = []
with seam.patched("QFileDialog", type("QFileDialogStandIn", (), {
        "getOpenFileName": staticmethod(lambda parent, title, start, filters=None:
                                       (_picked_filters.append((title, filters)),
                                        (str(_good_file), filters))[1])})):
    mod.MainApp.open_import_dialog(_import_choice_app)
_waits_for_read = _wait_for(lambda: _import_choice_app.config_file_ready_signal.emitted
                            or _import_choice_app.import_failed_signal.emitted, 4.0)
check("WN-N38 the Import button offers a settings file beside a package, and a .json goes to the settings import rather than to the package reader - and what that path does first is read the file and hand it back for the confirmation, with nothing on this machine changed yet",
      _picked_filters and "yt-msd Settings (*.json)" in _picked_filters[0][1]
      and "yt-msd Package (*.zip)" in _picked_filters[0][1]
      and _picked_filters[0][1].index("yt-msd Package (*.zip)") < _picked_filters[0][1].index("yt-msd Settings (*.json)")
      and _waits_for_read
      and _import_choice_app.config_file_ready_signal.emitted == [(str(_good_file), THEIRS)]
      and _import_choice_app.import_failed_signal.emitted == []
      and _import_choice_app._export_import_busy is False
      and _import_choice_app.read_file() == OURS,
      (_picked_filters, _import_choice_app.config_file_ready_signal.emitted))
_package_choice_app = _ConfigImportApp("import dialog package")
_package_worker_saw = []
_package_choice_app._import_worker = lambda path: _package_worker_saw.append(path)
with seam.patched("QFileDialog", type("QFileDialogStandIn", (), {
        "getOpenFileName": staticmethod(lambda parent, title, start, filters=None:
                                        (r"C:\Exported\yt-msd-package.zip", filters))})):
    mod.MainApp.open_import_dialog(_package_choice_app)
_waits_for_package = _wait_for(lambda: _package_worker_saw, 4.0)
check("WN-N39 and a .zip still goes the way it has always gone, with the settings file offered beside it and not in front of it",
      _waits_for_package and _package_worker_saw == [r"C:\Exported\yt-msd-package.zip"]
      and _package_choice_app._config_import_busy is False,
      (_package_worker_saw, _package_choice_app._config_import_busy))
_pyw_source = (Path(SRC_DIR) / "yt-msd-gui.pyw").read_text(encoding="utf-8")
_bootstrap_source = (Path(SRC_DIR) / "yt_msd" / "ui" / "bootstrap.py").read_text(encoding="utf-8")
_sync_client_source = (Path(SRC_DIR) / "yt_msd" / "sync" / "client.py").read_text(encoding="utf-8")
_sync_host_source = (Path(SRC_DIR) / "yt_msd" / "sync" / "host.py").read_text(encoding="utf-8")
check("WN-N40 the host menu hands the chain to the main window and nothing else: a chain that has lent its host's settings out is still the same chain, and the settings are written in exactly one place in the program",
      all(hasattr(mod.SyncManagerDialog, name) for name in ("_import_config_from_host",
                                                            "_sync_single_client_chain",
                                                            "_push_client_chain"))
      and "import_settings = getattr(self.parent_app, 'import_config_from_host', None)"
          in (Path(SRC_DIR) / "yt_msd" / "sync" / "dialogs.py").read_text(encoding="utf-8")
      and _pyw_source.count("def import_config_from_host") == 1,
      _pyw_source.count("def import_config_from_host"))


_sync_dialog_app = AppStandIn(sync_config_manager=SYNC_CM, sync_host_server=None,
                              status_signal=_StatusLine())
_dlg_for_import = QuietSyncDialog(_sync_dialog_app)
_forwarded = []
_sync_dialog_app.import_config_from_host = lambda cc: _forwarded.append(dict(cc))
_client_card = _card_for(_dlg_for_import, CLIENT_CHAIN["id"])
_card_import_buttons = [btn for btn in _client_card.findChildren(QPushButton)
                        if "Import" in btn.text()]
_top_import_buttons = [btn for btn in _dlg_for_import.findChildren(QPushButton)
                       if btn.text().startswith("Import Settings From Host")]
check("WN-N41 the import lives at the top of the window with the buttons that make and join chains: one button for the whole window and no client card carrying one of its own - a control that overwrites somebody's entire config does not belong in a card header already holding six",
      len(_top_import_buttons) == 1 and _top_import_buttons[0] is _dlg_for_import.import_host_btn
      and _card_import_buttons == [] and _forwarded == [],
      ([btn.text() for btn in _dlg_for_import.findChildren(QPushButton)], _card_import_buttons))

# The menu of machines. Five chains reach one host, one chain reaches another, and one has never found
# its host at all: what the menu says about that machine-count is the whole of the design.
_MENU_CFG = fixture("host import menu chains")
_MENU_CM = mod.SyncConfigManager(str(_MENU_CFG))
_MENU_OTHER = _MENU_CM.add_client_chain(name="Other", folder_path=str(_MENU_CFG / "other"),
                                        sync_code="5001", host_ip="192.0.2.44", deletion_mode="additive")
_MENU_CHRISTIAN = _MENU_CM.add_client_chain(name="Christian", folder_path=str(_MENU_CFG / "christian"),
                                            sync_code="5002", host_ip="192.0.2.44", deletion_mode="additive")
_MENU_COMMUTE = _MENU_CM.add_client_chain(name="Commute", folder_path=str(_MENU_CFG / "commute"),
                                          sync_code="5003", host_ip="192.0.2.44", deletion_mode="mirror")
_MENU_FOCUS = _MENU_CM.add_client_chain(name="Focus", folder_path=str(_MENU_CFG / "focus"),
                                        sync_code="5004", host_ip="192.0.2.44", deletion_mode="mirror")
_MENU_SLEEP = _MENU_CM.add_client_chain(name="Sleep", folder_path=str(_MENU_CFG / "sleep"),
                                        sync_code="5005", host_ip="192.0.2.44", deletion_mode="mirror")
_MENU_NIGHT = _MENU_CM.add_client_chain(name="Night Drive", folder_path=str(_MENU_CFG / "night"),
                                        sync_code="5006", host_ip="192.0.2.77", deletion_mode="mirror")
_MENU_NOWHERE = _MENU_CM.add_client_chain(name="Nowhere", folder_path=str(_MENU_CFG / "nowhere"),
                                          sync_code="5007", host_ip="", deletion_mode="mirror")
# The pairing proven most recently, on the host with five chains and on the host with one. Every other
# chain on this fixture has never synced.
_MENU_CHRISTIAN["last_synced"] = 1730000000.0
_MENU_NIGHT["last_synced"] = 1700000000.0

_MENU_FORWARD = []
_MENU_APP = AppStandIn(sync_config_manager=_MENU_CM, sync_host_server=None, status_signal=_StatusLine())
_MENU_APP.import_config_from_host = lambda cc: _MENU_FORWARD.append(dict(cc))
_MENU_DLG = QuietSyncDialog(_MENU_APP)
_MENU_DLG._rebuild_import_host_menu()
_MENU_ACTIONS = _MENU_DLG.import_host_menu.actions()
_MENU_TEXTS = [act.text() for act in _MENU_ACTIONS]
check("WN-N42 the menu names machines and not chains: five chains reaching one host are one entry naming the chains that host reaches, a second host is its own entry, and the entries come in address order with a host nobody has reached last",
      _MENU_TEXTS == ["192.0.2.44 - Host of Other, Christian, Commute, etc.",
                      "192.0.2.77 - Host of Night Drive",
                      "Host address not known yet - Host of Nowhere"],
      _MENU_TEXTS)
check("WN-N43 every entry can actually be chosen, and each one says on its tooltip which machine it asks and which chain it asks through - somebody choosing from this menu has to be able to tell that a five-chain host is one machine with one settings file",
      all(act.isEnabled() for act in _MENU_ACTIONS)
      and "192.0.2.44" in _MENU_ACTIONS[0].toolTip() and "Christian" in _MENU_ACTIONS[0].toolTip()
      and "192.0.2.77" in _MENU_ACTIONS[1].toolTip(),
      [act.toolTip() for act in _MENU_ACTIONS])
_MENU_ACTIONS[0].trigger()
check("WN-N44 choosing a host hands one of that host's chains to the window that writes settings - the chain whose pairing was proven most recently, because a host answers for any chain it hosts and the most recently synced is the least likely to have been removed on the host - and the sync window itself neither warns nor writes",
      len(_MENU_FORWARD) == 1 and _MENU_FORWARD[0]["sync_code"] == "5002"
      and _MENU_FORWARD[0]["last_known_host_ip"] == "192.0.2.44"
      and _MENU_APP.status_signal.lines == [],
      (_MENU_FORWARD, _MENU_APP.status_signal.lines))
_MENU_CM.add_client_chain(name="Morning", folder_path=str(_MENU_CFG / "morning"),
                          sync_code="5008", host_ip="192.0.2.88", deletion_mode="additive")
_MENU_DLG._rebuild_import_host_menu()
check("WN-N45 the menu is filled from the chains as they stand when it is opened and not from the chains as they were when the window was built, so a machine this PC started following while the window was open is offered and no machine is offered twice",
      [act.text() for act in _MENU_DLG.import_host_menu.actions()] ==
      ["192.0.2.44 - Host of Other, Christian, Commute, etc.",
       "192.0.2.77 - Host of Night Drive",
       "192.0.2.88 - Host of Morning",
       "Host address not known yet - Host of Nowhere"],
      [act.text() for act in _MENU_DLG.import_host_menu.actions()])

_EMPTY_CFG = fixture("no chains to import from")
_EMPTY_CM = mod.SyncConfigManager(str(_EMPTY_CFG))
_EMPTY_FORWARD = []
_EMPTY_APP = AppStandIn(sync_config_manager=_EMPTY_CM, sync_host_server=None, status_signal=_StatusLine())
_EMPTY_APP.import_config_from_host = lambda cc: _EMPTY_FORWARD.append(dict(cc))
_EMPTY_DLG = QuietSyncDialog(_EMPTY_APP)
_EMPTY_DLG._rebuild_import_host_menu()
_EMPTY_ACTIONS = _EMPTY_DLG.import_host_menu.actions()
check("WN-N46 a PC following no chain still opens the menu and is told there is nothing to import from, in a line that cannot be chosen, rather than being given a button that does nothing when pressed",
      len(_EMPTY_ACTIONS) == 1 and _EMPTY_ACTIONS[0].text() == "No chain on this PC follows another machine"
      and _EMPTY_ACTIONS[0].isEnabled() is False and _EMPTY_FORWARD == [],
      [act.text() for act in _EMPTY_ACTIONS])
check("WN-N47 what a host's entry sends is one of its own chains as this machine holds it: the fetch is the client half of a chain, so it travels on a chain this machine already has, which is the only reason a host answers it at all",
      _MENU_FORWARD[0] == {key: value for key, value in _MENU_CHRISTIAN.items()},
      (_MENU_FORWARD[0], _MENU_CHRISTIAN))
check("WN-N48 the main window is the one that answers a client asking for its settings, and it is handed to the host server the same way the hosted chains and the restore events are",
      "get_config_cb=self._config_payload_for_host" in _bootstrap_source
      and "def _config_payload_for_host" in _pyw_source
      and "_CONFIG_WRITE_LOCK" in _pyw_source.split("def _config_payload_for_host", 1)[1]
          .split("def ", 1)[0],
      [line.strip() for line in _bootstrap_source.splitlines() if "get_config_cb" in line])
check("WN-N49 a settings import is wired to the window the way every other worker is wired: a signal on the main window, connected in the startup beside the import and export signals it sits next to",
      "config_file_ready_signal = Signal(str, object)" in _pyw_source
      and "self.config_file_ready_signal.connect(self._on_config_file_read)" in _bootstrap_source
      and "self._config_import_busy = False" in _bootstrap_source,
      [line.strip() for line in _bootstrap_source.splitlines()
       if "config" in line and "signal" in line])
_new_names = ("build_host_config_import", "read_settings_file", "MACHINE_OWN_CONFIG_KEYS",
              "SESSION_LOCAL_PATH_KEYS", "SETTINGS_FILE_MARKERS", "HostConfigFetchThread",
              "MAX_CONFIG_PAYLOAD_BYTES")
check("WN-N50 every name this added is a module-level one the seam reaches, and none of them is held only by the entry point",
      all(seam.owned_by(name) and any(owner != mod.__name__ for owner in seam.owned_by(name))
          for name in _new_names),
      {name: seam.owned_by(name) for name in _new_names})
check("WN-N51 both whole-config imports finish by making the window, the file and the next save say the same thing - the file written, the settings read back into the attributes that own them, and every control save_config reads out of refilled - and that is the order the reset to defaults got wrong",
      "_apply_whole_config_import" in _pyw_source and "_reload_settings_into_ui" in _pyw_source
      and "_write_settings_file" in _pyw_source and "self.load_config()" in _pyw_source
      and "GET_CONFIG" in _sync_client_source and "GET_CONFIG" in _sync_host_source,
      [name for name in ("_apply_whole_config_import", "_reload_settings_into_ui",
                         "_write_settings_file") if name not in _pyw_source])

shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
check("WN-F9 every folder this suite wrote is gone again", not FIXTURE_ROOT.exists())

print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)

