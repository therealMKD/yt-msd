"""The export-package regression harness.

Sections EX-A..EX-H cover the export/import half of `GUI Source Code/yt-msd-gui.pyw`: what may
leave a machine in a yt-msd package and what must not, the `export.yaml` manifest that describes a
package and the hand-written YAML helpers that write and read it, the folder walk that copies music
into the archive, the archive names that keep two folders of the same name both survivable, reading
a package back, putting its music somewhere that is not inside itself, and the window that asks for
all of it.

Recipe (AI Readme section 20): same as probe_playback and probe_sync - the `.pyw` is copied to a
throwaway `.py` in this folder's `copy/` and imported, and the functions are driven directly.
Nothing is written into the entry point by hand; anything replaced goes through harness_seam.py.

One relaxation, bounded the way probe_sync bounds its own: this suite writes files, but only fixture
folders under `copy/export_fixture/`, rebuilt at the start of every run and deleted again at the end.
No check writes to Downloads, to the app's own config folder, to the music library, or to any folder
the suite did not build. Where a helper's answer is a path outside those fixtures - the "that machine
does not have this folder any more" fallback in music_import_destination - the check reads the string
and never follows it.
"""
import ast
import importlib.util
import json
import os
import shutil
import sys
import zipfile

from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

HERE = os.path.dirname(os.path.abspath(__file__))              # .../GUI Source Code/GUI Test Suite
SRC = os.path.join(os.path.dirname(HERE), "yt-msd-gui.pyw")    # the master copy, one folder up
SRC_DIR = os.path.dirname(SRC)       # GUI Source Code, which now also holds the yt_msd package
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)      # the copy below imports that package, so it must be reachable
COPY_DIR = os.path.join(HERE, "copy")
os.makedirs(COPY_DIR, exist_ok=True)
TMP_PY = os.path.join(COPY_DIR, "yt_msd_export_under_test.py")
shutil.copyfile(SRC, TMP_PY)
_spec = importlib.util.spec_from_file_location("yt_msd_export_under_test", TMP_PY)
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
FIXTURE_ROOT = Path(COPY_DIR) / "export_fixture"
shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)


def fixture(name):
    """A folder under the fixture root, always fresh."""
    folder = FIXTURE_ROOT / name
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def touch(folder, name, body=b"fake track bytes"):
    """A file inside a fixture folder, with whatever path the name spells."""
    path = Path(folder) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


# ===========================================================================
# EX-A: the vocabulary a package is known by
# ===========================================================================
check("EX-A1 a package is export.yaml, config/gui-config.json and sync/sync-chains.json - those three names are how it is recognised",
      (mod.EXPORT_MANIFEST_NAME, mod.EXPORT_CONFIG_ENTRY, mod.EXPORT_SYNC_ENTRY)
      == ("export.yaml", "config/gui-config.json", "sync/sync-chains.json"),
      (mod.EXPORT_MANIFEST_NAME, mod.EXPORT_CONFIG_ENTRY, mod.EXPORT_SYNC_ENTRY))
check("EX-A2 the manifest states which package format it is written in",
      mod.EXPORT_FORMAT_VERSION == 1, mod.EXPORT_FORMAT_VERSION)
check("EX-A3 exactly these three keys are the sync-chain information a config-only export must drop",
      set(mod.SYNC_ONLY_CONFIG_KEYS) == {"sync_settings", "hosted_chains", "client_chains"},
      sorted(mod.SYNC_ONLY_CONFIG_KEYS))
check("EX-A4 the folder walk refuses to carry the folders Windows keeps in a music folder",
      {"$recycle.bin", "system volume information", "__pycache__", ".git"} == set(mod.EXPORT_SKIP_DIRS),
      sorted(mod.EXPORT_SKIP_DIRS))

# ===========================================================================
# EX-B: what may leave - build_exported_config's three cases
# ===========================================================================
LIVE = {
    "format": "flac", "bitrate": "320", "last_search": "moon over Miami",
    "folders": [r"D:\Music"], "volume": 61,
    "hosted_chains": [{"sync_code": "4821", "folder": r"D:\Hosted"}],
    "client_chains": [{"sync_code": "4821", "host_ip": "192.168.1.9"}],
    "sync_settings": {"auto_sync": True},
}

_config_only = mod.build_exported_config(LIVE, True, False, {})
check("EX-B1 a config-only export keeps the live settings",
      _config_only.get("format") == "flac" and _config_only.get("volume") == 61, _config_only)
check("EX-B2 a config-only export carries no chain code, no chain folder and no chain host",
      not any(key in _config_only for key in mod.SYNC_ONLY_CONFIG_KEYS),
      sorted(k for k in _config_only if k in mod.SYNC_ONLY_CONFIG_KEYS))
_config_only["format"] = "mp3"
check("EX-B3 the config it hands back is a copy: exporting cannot write into the running settings",
      LIVE.get("format") == "flac", LIVE.get("format"))

_PAYLOAD = {"hosted_chains": [{"sync_code": "4821", "folder": r"D:\Hosted"}],
            "client_chains": [], "sync_settings": {"auto_sync": False}}
_chains_only = mod.build_exported_config(LIVE, False, True, _PAYLOAD)
check("EX-B4 a chains-only export starts from a fresh default config, not from the live one",
      _chains_only.get("format") == mod.default_export_config().get("format")
      and _chains_only.get("last_search") == ""
      and _chains_only.get("volume") == 100, _chains_only)
check("EX-B5 a chains-only export still carries the chains it was built for",
      _chains_only.get("hosted_chains") == _PAYLOAD["hosted_chains"]
      and _chains_only.get("sync_settings") == {"auto_sync": False}, _chains_only)

_both = mod.build_exported_config(LIVE, True, True, _PAYLOAD)
check("EX-B6 exporting both keeps the live settings and the chains",
      _both.get("format") == "flac" and _both.get("hosted_chains") == _PAYLOAD["hosted_chains"], _both)

_empty = mod.build_exported_config(LIVE, True, True, {})
check("EX-B7 chains checked but nothing to say about them adds no chain keys",
      not any(key in _empty for key in mod.SYNC_ONLY_CONFIG_KEYS),
      sorted(k for k in _empty if k in mod.SYNC_ONLY_CONFIG_KEYS))

_default = mod.default_export_config()
check("EX-B8 a fresh config names the machine's own Downloads folder as its only folder",
      _default.get("folders") == [os.path.join(os.path.expanduser("~"), "Downloads")],
      _default.get("folders"))
_default["format"] = "wav"
check("EX-B9 a fresh config is built afresh every time, so one export cannot leave fingerprints in the next",
      mod.default_export_config().get("format") == "mp3",
      mod.default_export_config().get("format"))

# ===========================================================================
# EX-C: export.yaml - written by hand, read back by the program
# ===========================================================================
_MUSIC_ENTRIES = [
    {"name": "Album One", "archive_path": "music/Album One",
     "source_path": r"C:\Music\Album One", "subfolders": True},
    {"name": "Album Two", "archive_path": "music/Album Two",
     "source_path": r"C:\Music\Album Two", "subfolders": False},
]

_manifest_text = mod.build_export_manifest_text(True, False, True, _MUSIC_ENTRIES)
_manifest = mod.yaml_load(_manifest_text)

check("EX-C1 the manifest says what it is and warns against editing it, because it is read as fact",
      "# yt-msd export package manifest. DO NOT EDIT." in _manifest_text)
check("EX-C2 what was ticked is what the manifest claims is inside",
      _manifest.get("includes") == {"config": True, "sync_chains": False, "music": True},
      _manifest.get("includes"))
check("EX-C3 a package that carries no chains names no sync file, so a reader cannot go looking in one",
      'sync_chains: ""' in _manifest_text and _manifest["files"]["sync_chains"] == "",
      _manifest.get("files"))
_both_manifest = mod.yaml_load(mod.build_export_manifest_text(True, True, False, []))
check("EX-C4 a package that does carry them names sync/sync-chains.json",
      _both_manifest["files"]["sync_chains"] == mod.EXPORT_SYNC_ENTRY, _both_manifest.get("files"))
check("EX-C5 the manifest round-trips through the program's own YAML helper into the shapes it was written as",
      _manifest.get("format_version") == 1 and isinstance(_manifest.get("includes"), dict)
      and _manifest["files"]["manifest"] == mod.EXPORT_MANIFEST_NAME, _manifest)
check("EX-C6 it names the app version that wrote it, so an older package can be recognised as older",
      str(_manifest.get("app_version")) == str(mod.APP_VERSION), _manifest.get("app_version"))
check("EX-C7 it is stamped with when the package was made",
      isinstance(_manifest.get("created"), str) and len(_manifest["created"]) == 19
      and _manifest["created"][2] == "-" and _manifest["created"].count(":") == 2,
      _manifest.get("created"))
check("EX-C8 every music folder in the package is listed with where it came from and whether its subfolders went",
      _manifest.get("music_folders") == _MUSIC_ENTRIES, _manifest.get("music_folders"))
check("EX-C9 a package with no music writes an empty list and reads back an empty list",
      _both_manifest.get("music_folders") == [], _both_manifest.get("music_folders"))

# ===========================================================================
# EX-D: the name a folder takes inside the archive
# ===========================================================================
check("EX-D1 characters a path cannot hold become underscores rather than being dropped",
      mod.sanitize_archive_name('Album: "Live"/2024') == "Album_ _Live__2024",
      mod.sanitize_archive_name('Album: "Live"/2024'))
check("EX-D2 a control character in a folder name is replaced too, not copied into the archive",
      mod.sanitize_archive_name("track\x01name") == "track_name",
      repr(mod.sanitize_archive_name("track\x01name")))
check("EX-D3 a name that sanitises away to nothing falls back rather than making an empty folder",
      mod.sanitize_archive_name("") == "Music"
      and mod.sanitize_archive_name("...") == "Music"
      and mod.sanitize_archive_name(None, "Fallback") == "Fallback",
      (mod.sanitize_archive_name(""), mod.sanitize_archive_name("...")))

_used = set()
_first = mod.unique_music_archive_name(r"D:\Music\Mixtapes", _used)
_second = mod.unique_music_archive_name(r"E:\Other\Mixtapes", _used)
_third = mod.unique_music_archive_name(r"F:\mixtapes", _used)
check("EX-D4 the first folder of a name keeps that name",
      _first == ("music/Mixtapes", "Mixtapes"), _first)
check("EX-D5 a second folder of the same name is not allowed to overwrite the first inside the archive",
      _second == ("music/Mixtapes-2", "Mixtapes-2"), _second)
check("EX-D6 uniqueness ignores case, because the archive lands on a machine where names do not",
      _third == ("music/mixtapes-3", "mixtapes-3"), _third)
check("EX-D7 a folder with an illegal name is sanitised before it is made unique",
      mod.unique_music_archive_name(r"C:\a\b:c", set()) == ("music/b_c", "b_c"),
      mod.unique_music_archive_name(r"C:\a\b:c", set()))

# ===========================================================================
# EX-E: the walk that copies a music folder into the archive
# ===========================================================================
WALK = fixture("walk")
touch(WALK, "top.mp3")
touch(WALK, "deep/inner.mp3")
touch(WALK, ".git/config")
touch(WALK, "__pycache__/cached.pyc")
touch(WALK, "$RECYCLE.BIN/R$0.mp3")
touch(WALK, "System Volume Information/index")

_deep = list(mod.iter_folder_files(str(WALK), True))
_deep_rel = sorted(os.path.normpath(rel) for _full, rel in _deep)
check("EX-E1 with subfolders the walk reaches the file two levels down",
      os.path.normpath(os.path.join("deep", "inner.mp3")) in _deep_rel, _deep_rel)
check("EX-E2 the walk leaves out the folders Windows keeps, whatever case they are spelled in",
      not any(any(skip in rel.lower() for skip in mod.EXPORT_SKIP_DIRS) for _f, rel in _deep),
      _deep_rel)
check("EX-E3 every path it yields is a real file under the folder that was walked, and relative to it",
      all(os.path.isfile(full) for full, _rel in _deep)
      and _deep_rel == sorted(os.path.normpath(os.path.relpath(full, str(WALK)))
                              for full, _rel in _deep), _deep_rel)
_flat = sorted(rel for _full, rel in mod.iter_folder_files(str(WALK), False))
check("EX-E4 without subfolders only the files sitting in the folder itself are packaged",
      _flat == ["top.mp3"], _flat)

_ZIP_PATH = str(fixture("archive") / "walk.zip")
with zipfile.ZipFile(_ZIP_PATH, "w") as _zf:
    _written = mod.zip_folder_into(_zf, str(WALK), "music/Mixtapes", True)
with zipfile.ZipFile(_ZIP_PATH, "r") as _zf:
    _names = sorted(_zf.namelist())
check("EX-E5 the folder walk reports how many files it actually wrote",
      _written == 2, _written)
check("EX-E6 the archive keeps the folder's own shape under the name it was given, with / separators",
      _names == ["music/Mixtapes/deep/inner.mp3", "music/Mixtapes/top.mp3"], _names)
check("EX-E7 a skipped folder never reaches the archive, so a package cannot carry a recycle bin",
      not any(any(skip in name.lower() for skip in mod.EXPORT_SKIP_DIRS) for name in _names), _names)

# ===========================================================================
# EX-F: a package built by these functions, read back by them
# ===========================================================================
PACKED = fixture("packed") / "Live Set"
touch(PACKED, "b.mp3")
touch(PACKED, "set/a.mp3")
touch(PACKED, ".git/config")
RESTORE = fixture("restore") / "Live Set"

PACKAGE_ZIP = str(fixture("package") / "yt-msd-export.zip")
_ENTRIES = [{"name": "Live Set", "archive_path": "music/Live Set",
             "source_path": str(RESTORE), "subfolders": True}]
with zipfile.ZipFile(PACKAGE_ZIP, "w") as _zf:
    _zf.writestr(mod.EXPORT_CONFIG_ENTRY,
                 json.dumps(mod.build_exported_config(LIVE, True, True, _PAYLOAD)))
    _zf.writestr(mod.EXPORT_SYNC_ENTRY, json.dumps(_PAYLOAD))
    _packed_files = mod.zip_folder_into(_zf, str(PACKED), "music/Live Set", True)
    _zf.writestr(mod.EXPORT_MANIFEST_NAME,
                 mod.build_export_manifest_text(True, True, True, _ENTRIES))

_read = mod.read_import_package(PACKAGE_ZIP)
check("EX-F1 a package's manifest comes back as the mapping it was written from",
      _read["manifest"].get("includes") == {"config": True, "sync_chains": True, "music": True},
      _read["manifest"].get("includes"))
check("EX-F2 the settings inside a package are the settings that were exported, chains included when asked for",
      _read["config"].get("format") == "flac" and _read["config"].get("hosted_chains")
      == _PAYLOAD["hosted_chains"], _read["config"])
check("EX-F3 the chain payload is readable on its own, so chains can be restored without the settings",
      _read["sync"] == _PAYLOAD, _read["sync"])
check("EX-F4 only the music that the folder walk accepted is in the package",
      _packed_files == 2 and _read["manifest"]["music_folders"][0]["name"] == "Live Set",
      (_packed_files, _read["manifest"].get("music_folders")))

status_lines = []
with zipfile.ZipFile(PACKAGE_ZIP, "r") as _zf:
    results = mod.extract_package_music(_zf, _read["manifest"], status_cb=status_lines.append)
check("EX-F5 restoring puts every file the manifest names back into the folder it names",
      len(results) == 1 and results[0]["files"] == 2 and results[0]["error"] == ""
      and (RESTORE / "b.mp3").is_file() and (RESTORE / "set" / "a.mp3").is_file(),
      results)
check("EX-F6 it says out loud what it restored and where to",
      status_lines and status_lines[0].startswith("Restored 2 files to ")
      and str(RESTORE) in status_lines[0], status_lines)

_ORIGINAL_ZIP = str(fixture("no_manifest") / "other.zip")
with zipfile.ZipFile(_ORIGINAL_ZIP, "w") as _zf:
    _zf.writestr("anything.txt", b"not a yt-msd package")
try:
    mod.read_import_package(_ORIGINAL_ZIP)
    _refused = None
except ValueError as exc:
    _refused = str(exc)
check("EX-F7 a .zip without an export.yaml is refused by name, not half-imported",
      _refused is not None and "export.yaml" in _refused, _refused)

_MESSY_ZIP = str(fixture("messy") / "messy.zip")
with zipfile.ZipFile(_MESSY_ZIP, "w") as _zf:
    _zf.writestr(mod.EXPORT_MANIFEST_NAME,
                 mod.build_export_manifest_text(True, True, False, []))
    _zf.writestr(mod.EXPORT_CONFIG_ENTRY, b"{ this is not json")
_messy = mod.read_import_package(_MESSY_ZIP)
check("EX-F8 unreadable contents do not stop the manifest being read: what is broken is reported as missing",
      _messy["manifest"].get("format_version") == 1 and _messy["config"] is None
      and _messy["sync"] is None, _messy)

_RENAMED_ZIP = str(fixture("renamed") / "renamed.zip")
with zipfile.ZipFile(_RENAMED_ZIP, "w") as _zf:
    _zf.writestr("settings.json", json.dumps({"format": "m4a"}))
    _zf.writestr(mod.EXPORT_MANIFEST_NAME, mod.yaml_dump({
        "format_version": 1,
        "includes": {"config": True, "sync_chains": True, "music": False},
        "files": {"manifest": mod.EXPORT_MANIFEST_NAME, "config": "settings.json",
                  "sync_chains": "chains.json"},
        "music_folders": [],
    }))
_renamed = mod.read_import_package(_RENAMED_ZIP)
check("EX-F9 the manifest is read as fact: it says where the settings are and the reader goes there",
      _renamed["config"] == {"format": "m4a"} and _renamed["sync"] is None, _renamed)





_ESCAPE = fixture("escape") / "In"
_TRAP_ZIP = str(fixture("escape") / "trap.zip")
_TRAP_MANIFEST = mod.yaml_load(mod.build_export_manifest_text(False, False, True, [
    {"name": "Escape", "archive_path": "music/Escape",
     "source_path": str(_ESCAPE), "subfolders": True}]))
with zipfile.ZipFile(_TRAP_ZIP, "w") as _zf:
    _zf.writestr("music/Escape/../../elsewhere.txt", b"must never be written")
    _zf.writestr(mod.EXPORT_MANIFEST_NAME, mod.yaml_dump(_TRAP_MANIFEST))
with zipfile.ZipFile(_TRAP_ZIP, "r") as _zf:
    _trap = mod.extract_package_music(_zf, _TRAP_MANIFEST)
check("EX-F10 a member that climbs out of the folder it was packed into is left unpacked",
      _trap and _trap[0]["files"] == 0 and not (FIXTURE_ROOT / "elsewhere.txt").exists()
      and not any(_ESCAPE.rglob("*")), (_trap, list(_ESCAPE.rglob("*"))))

_missing_manifest = mod.yaml_load(mod.build_export_manifest_text(False, False, True, [
    {"name": "Nowhere", "archive_path": "music/Nowhere",
     "source_path": str(fixture("nowhere") / "Nowhere"), "subfolders": True}]))
with zipfile.ZipFile(_TRAP_ZIP, "r") as _zf:
    _missing = mod.extract_package_music(_zf, _missing_manifest)
check("EX-F11 a manifest entry naming music the archive does not hold restores nothing and claims no error",
      _missing and _missing[0]["files"] == 0 and _missing[0]["error"] == "", _missing)

check("EX-F12 a folder whose parent still exists is restored where it came from",
      mod.music_import_destination(str(PACKED), "Live Set")
      == os.path.abspath(str(PACKED)), mod.music_import_destination(str(PACKED), "Live Set"))
_fallback = mod.music_import_destination(r"Z:\gone\Live Set", "Live Set")
check("EX-F13 a folder whose parent is gone lands in Downloads/yt-msd Import instead - the path is read here, never followed",
      _fallback == os.path.join(os.path.expanduser("~"), "Downloads", "yt-msd Import", "Live Set"),
      _fallback)
check("EX-F14 a package with no record of where a folder came from still gets it a safe name to land on",
      mod.music_import_destination("", r"a/b:bad")
      == os.path.join(os.path.expanduser("~"), "Downloads", "yt-msd Import", "a_b_bad"),
      mod.music_import_destination("", r"a/b:bad"))

# ===========================================================================
# EX-G: the window that asks for a package
# ===========================================================================
_QT_APP = QApplication.instance() or QApplication([])
_dlg = mod.ExportDialog()

check("EX-G1 the window asks about exactly the three things a package can hold",
      all(hasattr(_dlg, name) for name in ("config_cb", "chains_cb", "music_cb")))
check("EX-G2 settings and chains are offered ticked, and the music folder list is out of the way until it is asked for",
      _dlg.config_cb.isChecked() and _dlg.chains_cb.isChecked()
      and not _dlg.music_cb.isChecked() and _dlg.music_widget.isHidden())
check("EX-G3 what the window would export is what its boxes say, in the shape MainApp.start_export expects",
      _dlg.build_options() == {"include_config": True, "include_chains": True,
                               "include_music": False, "music_folders": []}, _dlg.build_options())

_dlg.music_cb.setChecked(True)
_dlg._add_music_row(str(PACKED))
_dlg._add_music_row(str(RESTORE))
_options = _dlg.build_options()
check("EX-G4 each folder added is listed with the path it was added from and whether its subfolders go",
      _options["include_music"] and [entry["path"] for entry in _options["music_folders"]]
      == [str(PACKED), str(RESTORE)]
      and all(entry["subfolders"] for entry in _options["music_folders"]), _options)
check("EX-G5 every row the list holds is also a row the window shows",
      len(_dlg.music_rows) == 2 and all(_dlg.music_rows_layout.indexOf(row["row"]) >= 0
                                        for row in _dlg.music_rows),
      [row["path"] for row in _dlg.music_rows])

_dlg._remove_row(_dlg.music_rows, str(PACKED), "path")
check("EX-G6 removing a folder takes it out of the list and out of the window, not only one of them",
      [row["path"] for row in _dlg.music_rows] == [str(RESTORE)]
      and all(_dlg.music_rows_layout.indexOf(row["row"]) >= 0 for row in _dlg.music_rows),
      [row["path"] for row in _dlg.music_rows])

for _cb in (_dlg.config_cb, _dlg.chains_cb, _dlg.music_cb):
    _cb.setChecked(False)
check("EX-G7 nothing ticked is not an export: the window says so and disables its own button",
      _dlg.build_options(require_selection=True) is None
      and _dlg.summary_lbl.text() == "Nothing selected to export."
      and not _dlg.export_btn.isEnabled(), (_dlg.build_options(True), _dlg.summary_lbl.text()))
_dlg.config_cb.setChecked(True)
check("EX-G8 ticking something back names in the summary what will actually go",
      "config" in _dlg.summary_lbl.text() and _dlg.export_btn.isEnabled()
      and "sync chains" not in _dlg.summary_lbl.text(), _dlg.summary_lbl.text())
_dlg.music_cb.setChecked(True)
_shown = not _dlg.music_widget.isHidden() and _dlg._collapsed_size is not None
_dlg.music_cb.setChecked(False)
check("EX-G9 the music section appears when it is ticked and the window remembers the size it had without it",
      _shown and _dlg.music_widget.isHidden(), (_shown, _dlg._collapsed_size))

_host_widget = QWidget()
_child_dlg = mod.ExportDialog(_host_widget)
check("EX-G10 the window keeps the app that opened it under its own name, so Qt's parent() is still Qt's",
      _child_dlg.main_app is _host_widget and callable(_child_dlg.parent),
      (_child_dlg.main_app, _child_dlg.parent))



# ===========================================================================
# EX-H: the seam - a replacement lands where these functions read it
# ===========================================================================
seam.patch("yaml_dump", lambda data, indent=0: "written by the harness\n")
_patched_manifest = mod.build_export_manifest_text(True, False, False, [])
check("EX-H1 a manifest is written with the YAML helper the program actually calls, not with a copy the harness left standing",
      "written by the harness" in _patched_manifest, _patched_manifest)
seam.restore("yaml_dump")
check("EX-H2 the helper the program owns is back afterwards",
      "format_version" in mod.build_export_manifest_text(True, False, False, []))

seam.patch("sanitize_archive_name", lambda raw, fallback="Music": "PATCHED")
_patched_destination = mod.music_import_destination("", "Original Name")
check("EX-H3 the folder a package restores is named by the sanitiser its own module calls - so when a wave moves both, the patch still reaches the caller",
      _patched_destination.endswith("PATCHED"), _patched_destination)
seam.restore("sanitize_archive_name")
check("EX-H4 and the real sanitiser is the one that names it again",
      mod.music_import_destination("", "a/b:bad").endswith("a_b_bad"),
      mod.music_import_destination("", "a/b:bad"))

_owners = seam.owners("build_exported_config")
check("EX-H5 the entry point and the module holding this function hold the same function, whichever module that is",
      bool(_owners) and all(getattr(_m, "build_exported_config") is mod.build_exported_config
                            for _m in _owners),
      [getattr(_m, "__name__", "?") for _m in _owners])
check("EX-H10 after the move, the sanitiser and the function that calls it are held by the same real module, so a patch on one reaches the other",
      "yt_msd.export" in seam.owned_by("sanitize_archive_name")
      and "yt_msd.export" in seam.owned_by("music_import_destination"),
      (seam.owned_by("sanitize_archive_name"), seam.owned_by("music_import_destination")))


try:
    seam.patch("build_export_package_that_is_not_in_the_program", lambda: None)
    _refused_unowned = False
except seam.SeamError:
    _refused_unowned = True
check("EX-H6 a name nothing in the program owns is refused out loud instead of quietly doing nothing",
      _refused_unowned)

_self_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
_stray_writes = [f"line {node.lineno}" for node in ast.walk(_self_tree)
                 if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))
                 and any(isinstance(target, ast.Attribute)
                         and isinstance(target.value, ast.Name)
                         and target.value.id == "mod"
                         for target in ([node.target] if not isinstance(node, ast.Assign)
                                        else node.targets))]
check("EX-H7 this file writes nothing into the entry point by hand - every replacement goes through the seam",
      _stray_writes == [], _stray_writes)

for _leftover in ("yaml_dump", "sanitize_archive_name"):
    if seam.is_patched(_leftover):
        seam.restore(_leftover)
check("EX-H8 nothing this suite patched is left patched for the next suite to run against",
      not seam.is_patched("yaml_dump") and not seam.is_patched("sanitize_archive_name"))

shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
check("EX-H9 every folder this suite wrote is gone again", not FIXTURE_ROOT.exists())

print(f"{CHECKS - len(FAILS)} / {CHECKS} checks passed")
if FAILS:
    print("FAILED: " + "; ".join(FAILS))
    raise SystemExit(1)
