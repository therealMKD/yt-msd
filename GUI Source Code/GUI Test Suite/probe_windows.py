"""The windows regression harness.

Sections WN-A..WN-G cover the windows half of `GUI Source Code/yt-msd-gui.pyw`: the settings window
and where each of its controls writes, the three windows that build a sync chain (host, client,
removable drive), the sync manager that lists and pauses and removes them, the playlist picker, the
tray progress bubble, the three update windows, the rename-from-metadata window, and the two things
the program promises the machine - which file Windows is told to start, and which yt-dlp it looks for.

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

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

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


def answering(answer_yes, drive):
    """Run `drive`, with confirmations answered `answer_yes` and warnings recorded."""
    _Answers.answer_yes = answer_yes
    _Answers.asked.clear()
    _Answers.warned.clear()
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
check("WN-E6 both boxes empty says so on the window instead of proposing an empty file name",
      "(enter an artist or a title)" in _rename_dlg.rows[2]["new_lbl"].text(),
      _rename_dlg.rows[2]["new_lbl"].text())
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
class _GateSignal:
    """A signal that answers itself, some time after it is emitted, as a queued one does on the GUI thread."""

    def __init__(self, app, answer_after=0.0):
        self.app = app
        self.answer_after = answer_after
        self.emitted = []

    def emit(self, request_id, title, question):
        self.emitted.append((request_id, title, question))
        timer = threading.Timer(self.answer_after,
                                lambda: self.app._on_sync_confirm(request_id, title, question))
        # A daemon, because one of these is deliberately never answered: the check that proves a
        # question nobody answers still finishes must not hold the run open for it.
        timer.daemon = True
        timer.start()


class _GateApp:
    """The gate without the window: both halves are the program's own methods, taken unbound.

    Building a MainApp to reach two methods would need a player, a tray and a config file. What is
    under test is the parking and the answering, so the attributes those two methods touch are the
    only ones here.
    """

    ask_sync_confirm = mod.MainApp.ask_sync_confirm
    _on_sync_confirm = mod.MainApp._on_sync_confirm

    def __init__(self, answer_after=0.0):
        self.sync_confirm_waiters = {}
        self._sync_confirm_lock = threading.Lock()
        self._sync_confirm_counter = 0
        self.sync_manager_dialog = None
        self.sync_confirm_signal = _GateSignal(self, answer_after)


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

_stand_in_cb = mod.make_delete_confirm_cb(AppStandIn(), "Studio")
_real_cb = mod.make_delete_confirm_cb(_GateApp(), "Studio")
check("WN-I7 the callback a sync is built with is handed over only by an app that can ask, and is nothing at all to one that cannot",
      _stand_in_cb is None and _real_cb is not None, _stand_in_cb)
_answer_cb = answering(True, lambda: _real_cb("Delete 12 file(s)?"))
check("WN-I8 and going through that callback is the same gate: the chain's name is in the title the box is opened with",
      _answer_cb is True and _Answers.asked[-1][0] == "Sync Chain 'Studio' - Delete Files?",
      _Answers.asked[-1])
check("WN-I9 the gate is a signal MainApp declares and a pair of methods it owns, so a worker thread has something to reach for",
      "Signal" in type(getattr(mod.MainApp, "sync_confirm_signal")).__name__
      and "ask_sync_confirm" in dir(mod.MainApp) and "_on_sync_confirm" in dir(mod.MainApp),
      type(getattr(mod.MainApp, "sync_confirm_signal")).__name__)

shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
check("WN-F9 every folder this suite wrote is gone again", not FIXTURE_ROOT.exists())

print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)

