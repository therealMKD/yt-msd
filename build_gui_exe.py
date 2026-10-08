# Open Source Software under the Apache License, Version 2.0
#
# Build the compiled Windows program for the yt-msd GUI, and the installer that
# ships it.
#
# This is the second half of the pipeline started by build_gui_cython.py:
#
#   GUI Source Code/yt-msd-gui.pyw            the master source, unchanged
#   GUI Source Code/yt_msd_gui.pyx            the same text as a Cython module
#   build_dir_cython/yt_msd_gui.c             Cython's C output
#   build_dir_cython/yt_msd_gui.pyd           that C, compiled with MSVC
#   build_dir_cython/yt_msd_gui_launcher.py   entry point for both jobs (generated)
#   GUI Source Code/yt-msd-gui/               the GUI and the renamer, in one folder
#     yt-msd-gui.exe + _internal\               (PyInstaller's one-folder build)
#   GUI Source Code/yt-msd-setup.exe          that folder packed as one installer
#
# One exe, two jobs. The GUI is windowed and must not drag a console window
# along with it, while the MP3 renamer IS a console program (banner, colours,
# input() prompts). So the exe decides at startup what it is: with no flag it
# opens the Qt window; with --renamer (or -r) it allocates a console window for
# itself and runs the renamer CLI in it. The GUI reaches that half by starting a
# second copy of itself - see run_mp3_renamer in the .pyw - and so can you, from
# a terminal or from a shortcut that adds the flag.
#
# The exe carries every runtime dependency except yt-dlp, which stays a separate
# install: the compiled GUI itself, PySide6, mutagen, Pillow, watchdog,
# python-vlc, libvlc.dll + libvlccore.dll + the VLC plugin folder,
# ffmpeg.exe + ffprobe.exe, and icon-256x256.ico (the title bar / taskbar / tray icon -
# the same file PyInstaller also embeds as the exe's own icon).
#
# Why a folder and an installer instead of one big exe: a one-file exe unpacks its
# ~550 MB into a temporary "_MEI" folder before the window appears (about 4 seconds
# here) and deletes that folder after the window closes, which keeps a hidden
# launcher process alive for another 4 seconds after the GUI is gone. A one-folder
# exe runs from the files that already sit beside it: window in about a second,
# process gone in about a tenth of a second. The one-folder build is a folder, so
# the last step packs it into a single installer - still one file to download, and
# double-clicking that is all an end user has to do.
#
# Commands
#   python build_gui_exe.py pyd       .pyx -> .c -> build_dir_cython/yt_msd_gui.pyd
#   python build_gui_exe.py launcher  write the launcher and the PyInstaller .spec
#   python build_gui_exe.py exe       build the one-folder app into GUI Source Code/
#   python build_gui_exe.py installer pack that folder into GUI Source Code/yt-msd-setup.exe
#   python build_gui_exe.py all       pyd + launchers + exe + installer
#
# Why a launcher exists: PyInstaller reads imports out of Python source, and a
# compiled .pyd has none it can see. So the launcher restates the .pyw's own
# import lines (copied from the source, so nothing is left out of the bundle)
# and then runs the .pyw's "if __name__ == \"__main__\":" block inside the
# compiled module - which is exactly what happens when the .pyw is run directly.
# Keeping the entry block in a launcher instead of using "cython --embed" also
# keeps sys.modules[__name__] working, which the python-vlc import-error text
# reads.

import ast
import glob
import os
import re
import shutil
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import build_gui_cython as cython_tools  # noqa: E402  (same folder, same constants)

PYW = cython_tools.PYW
PYX = cython_tools.PYX
BUILD_DIR = cython_tools.BUILD_DIR
MODULE_NAME = cython_tools.MODULE_NAME
EXE_NAME = "yt-msd-gui"
LAUNCHER = os.path.join(BUILD_DIR, "%s_launcher.py" % MODULE_NAME)
SPEC_PATH = os.path.join(BUILD_DIR, "%s.spec" % EXE_NAME)
# The version resource PyInstaller writes into the exe. Without one the exe
# reports 0.0.0.0, so the file's own Properties dialog - and any Windows crash
# report about it - says nothing about which version it is.
VERSION_FILE = os.path.join(BUILD_DIR, "%s_version_info.txt" % EXE_NAME)
ICON = os.path.join(ROOT, "GUI Source Code", "icon-256x256.ico")
# The build output is written next to the GUI source, which is where it is kept and
# run from (the exe, its _internal folder and the setup .exe are all git-ignored).
DIST_DIR = os.path.join(ROOT, "GUI Source Code")
# A one-folder build is an exe plus the "_internal" folder PyInstaller fills, and
# the exe only runs while that folder sits beside it. So the app lives in a folder
# of its own, and the installer step is what turns that folder into one file.
APP_DIR = os.path.join(DIST_DIR, EXE_NAME)
EXE_PATH = os.path.join(APP_DIR, "%s.exe" % EXE_NAME)
# The one-file exe this script used to build, kept out of the way of the new layout.
LEGACY_EXE_PATH = os.path.join(DIST_DIR, "%s.exe" % EXE_NAME)
SETUP_NAME = "yt-msd-setup"
SETUP_PATH = os.path.join(DIST_DIR, "%s.exe" % SETUP_NAME)
ISS_PATH = os.path.join(BUILD_DIR, "%s.iss" % EXE_NAME)
C_PATH = os.path.join(BUILD_DIR, "%s.c" % MODULE_NAME)


def find_pyd():
    """The compiled extension, whatever suffix setuptools gave it.

    setuptools names it after the running interpreter, e.g.
    yt_msd_gui.cp314-win_amd64.pyd. That is the name Python and PyInstaller
    look for, so it is left as it is.
    """
    found = glob.glob(os.path.join(BUILD_DIR, "%s*.pyd" % MODULE_NAME))
    return max(found, key=os.path.getmtime) if found else None


def pyd_is_current():
    """True when a compiled module exists and is not older than either source.

    The check used to be only "does a .pyd exist", which let a compiled module
    from last week be packaged into today's exe without a word: the exe ran the
    older program while the .pyw said something else, and nothing failed. Both
    sources are compared because the .pyx is the one that is compiled, but it is
    only ever a copy of the .pyw - a .pyw edited without the sync step is the
    same mistake wearing a different hat.
    """
    pyd = find_pyd()
    if not pyd:
        print("no compiled module yet - building it first")
        return False
    built = os.path.getmtime(pyd)
    for src in (PYX, PYW):
        if os.path.exists(src) and os.path.getmtime(src) > built:
            print("%s is newer than the compiled module - rebuilding it first"
                  % os.path.basename(src))
            return False
    return True


def run(cmd, cwd=None):
    """Run a build command and echo its output."""
    print("  $ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines():
        if line.strip():
            print("  " + line)
    return proc.returncode


def source_text():
    with open(PYW, encoding="utf-8") as fh:
        return fh.read()


def collect_import_lines():
    """Every import statement in the .pyw, copied verbatim and de-duplicated.

    These are what the launcher re-imports so PyInstaller bundles everything the
    compiled module needs. Only real module names are emitted: 'from x import y'
    is kept in its original form, so a class or constant imported from a module
    stays a class or constant imported from that module.
    """
    tree = ast.parse(source_text())
    lines = []
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                line = "import " + alias.name + (" as " + alias.asname if alias.asname else "")
                if line not in seen:
                    seen.add(line)
                    lines.append(line)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "__future__":
                continue
            names = ", ".join(a.name + (" as " + a.asname if a.asname else "") for a in node.names)
            line = "from %s import %s" % (node.module, names)
            if line not in seen:
                seen.add(line)
                lines.append(line)
    return lines


def collect_entry_block():
    """The body of the .pyw's 'if __name__ == \"__main__\":' block, dedented."""
    src = source_text()
    tree = ast.parse(src)
    for node in tree.body:
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"):
            lines = src.splitlines(True)
            body = "".join(lines[node.body[0].lineno - 1: node.body[-1].end_lineno])
            body = textwrap.dedent(body)
            if "'''" in body or body.rstrip().endswith("\\"):
                raise SystemExit("the entry block cannot be embedded in the launcher as-is")
            return body
    raise SystemExit("no 'if __name__ == \"__main__\":' block found in %s" % PYW)


SETUP_SRC = '''# Generated by build_gui_exe.py - do not edit by hand.
from setuptools import Extension, setup

setup(
    name="yt-msd-gui-compiled",
    ext_modules=[Extension("%s", ["%s.c"])],
    script_args=["build_ext", "--inplace"],
)
''' % (MODULE_NAME, MODULE_NAME)


def cmd_pyd():
    """Cython .pyx -> C -> MSVC -> build_dir_cython/yt_msd_gui.pyd"""
    if cython_tools.cmd_verify() != 0 and cython_tools.cmd_sync() != 0:
        return 1
    os.makedirs(BUILD_DIR, exist_ok=True)
    if (not os.path.exists(C_PATH)
            or os.path.getmtime(C_PATH) < os.path.getmtime(PYX)):
        if cython_tools.run_cython(C_PATH, False):
            return 1
    setup_py = os.path.join(BUILD_DIR, "_setup_ext.py")
    with open(setup_py, "w", encoding="utf-8") as fh:
        fh.write(SETUP_SRC)
    print("compiling %s with MSVC (a 9900-line module takes a minute or two)..."
          % os.path.basename(C_PATH))
    if run([sys.executable, setup_py], cwd=BUILD_DIR):
        print("  MSVC not found? Start a 'Developer PowerShell for VS' prompt and re-run.")
        return 1
    pyd = find_pyd()
    if not pyd:
        print("  expected a %s*.pyd in %s but none was produced" % (MODULE_NAME, BUILD_DIR))
        return 1
    print("  -> %s (%d bytes)" % (pyd, os.path.getsize(pyd)))
    return 0


LAUNCHER_HEAD = '''# Open Source Software under the Apache License, Version 2.0
#
# Generated by build_gui_exe.py - do not edit by hand.
#
# Entry point for the compiled GUI and, when called with --renamer, for the
# renamer CLI. PyInstaller cannot see the imports inside a compiled .pyd, so they
# are restated here (copied from yt-msd-gui.pyw) and nothing is left out of the
# bundle. The .pyw's entry block (the body of its "if __name__ == \"__main__\":")
# is then run inside the compiled module, which is what the .pyw does when it is
# run directly.
import os
import sys

if getattr(sys, "frozen", False):
    # ffmpeg.exe, ffprobe.exe, libvlc.dll, libvlccore.dll and the VLC plugins sit
    # in sys._MEIPASS, which for a one-folder build is the "_internal" folder beside
    # this exe. Putting that folder on PATH is how the plain "ffmpeg"/"ffprobe"
    # calls, yt-dlp's --ffmpeg-location and python-vlc's libvlc.dll lookup find them.
    _app_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    os.environ["PATH"] = _app_dir + os.pathsep + os.environ.get("PATH", "")

# Dependencies of the compiled module. The try/except mirrors the .pyw, which
# imports python-vlc the same way and reports a missing VLC itself.
try:
'''


LAUNCHER_TAIL = '''except Exception:  # the compiled module reports missing optional dependencies
    pass

import ctypes
import io
import msvcrt

import {module}


def run_renamer():
    """Give this windowed copy a console, then run the renamer CLI in it."""
    kernel32 = ctypes.windll.kernel32
    # GetStdHandle returns a pointer, not a C int, so say what it really returns:
    # None for a handle the process was not given, otherwise the handle as a
    # number (INVALID_HANDLE_VALUE comes back as a row of ones).
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    missing = (None, 0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFE, 0xFFFFFFFFFFFFFFFF)

    if kernel32.GetStdHandle(-11) in missing:
        # Nothing was handed to this copy - it was started by double-click, or by
        # the GUI, which is a windowed program too (CREATE_NEW_CONSOLE only works
        # for a program that is a console program to begin with). AllocConsole
        # gives this copy a console window of its own. Started from a terminal,
        # the handles are already there and the renamer prints in that terminal.
        kernel32.AllocConsole()
    # The banner draws with box-drawing characters and a tick mark, and a console
    # works in bytes, so both directions have to be told UTF-8.
    kernel32.SetConsoleOutputCP(65001)
    kernel32.SetConsoleCP(65001)
    kernel32.SetConsoleTitleW("MP3 Renamer")
    for index, fd, name, flags in ((-10, 0, "stdin", os.O_RDONLY),
                                   (-11, 1, "stdout", os.O_WRONLY),
                                   (-12, 2, "stderr", os.O_WRONLY)):
        handle = kernel32.GetStdHandle(index)
        if handle in missing:
            continue
        try:
            # A handle the process was given is not the same as a descriptor the
            # C runtime opened, and a windowed program opens none of the three.
            # Put the handle where its descriptor belongs before opening it.
            try:
                os.fstat(fd)
            except OSError:
                os.dup2(msvcrt.open_osfhandle(handle, flags), fd)
            stream = io.open(fd, "r" if flags == os.O_RDONLY else "w",
                             closefd=False, encoding="utf-8", errors="replace")
            if flags != os.O_RDONLY:
                stream.reconfigure(line_buffering=True)  # print as it happens
        except OSError:
            continue
        setattr(sys, name, stream)

    # "--renamer" and "-r" are accepted and dropped so one command line works for
    # either job. Everything else - the folder, --norm, --auto, --silence-pad,
    # --norm-threads, --eq, --custom-norm-cmd - is read by the CLI's own argparse,
    # which is the same code the .pyw runs for "yt-msd-gui.pyw --renamer".
    sys.argv = [a for a in sys.argv if a not in ("--renamer", "-r")]
    {module}.run_integrated_renamer_cli()

ENTRY_BLOCK = r\'\'\'
{entry}\'\'\'
# One exe, two jobs: the flag decides which job this copy of the program does.
# The .pyw's own entry block also understands --renamer, but only this path sets
# up a console first, which is what the renamer's printing and prompting need.
if any(arg in ("--renamer", "-r") for arg in sys.argv[1:]):
    run_renamer()
else:
    exec(compile(ENTRY_BLOCK, {pyw!r}, "exec"), {module}.__dict__)
'''


def write_launcher():
    imports = collect_import_lines()
    entry = collect_entry_block()
    body = "".join("    " + line + "\n" for line in imports)
    os.makedirs(BUILD_DIR, exist_ok=True)
    # The launcher restates the .pyw's own import lines, because that is what
    # puts every dependency into a bundle built around a compiled .pyd.
    tail = LAUNCHER_TAIL.format(module=MODULE_NAME, entry=entry,
                                pyw=os.path.basename(PYW))
    with open(LAUNCHER, "w", encoding="utf-8") as fh:
        fh.write(LAUNCHER_HEAD + body + tail)
    print("  -> %s (%d import lines)" % (LAUNCHER, len(imports)))
    return 0


def cmd_launcher():
    """Write the launcher and the .spec, without compiling or packaging."""
    if write_launcher():
        return 1
    return write_spec()


def ffmpeg_pair():
    """Find a real ffmpeg.exe + ffprobe.exe pair to bundle.

    Looks in PATH first, then in the usual winget/chocolatey install folders, and
    picks the smallest pair that is actually FFmpeg so the exe stays as small as
    it can. Set YTMSD_FFMPEG_DIR to force a particular folder.

    Two things are rejected:
      - chocolatey's bin folder, which holds shim .exe files that only work
        inside chocolatey and would be dead weight in the bundle;
      - a pair whose two files are byte-identical, which is how a shim pair
        looks (real ffmpeg.exe and ffprobe.exe are different programs).
    """
    dirs = []
    override = os.environ.get("YTMSD_FFMPEG_DIR")
    if override:
        dirs.append(override)
    for name in ("ffmpeg", "ffprobe"):
        found = shutil.which(name)
        if found:
            dirs.append(os.path.dirname(os.path.realpath(found)))
    for pattern in (
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\bin"),
        r"C:\ProgramData\chocolatey\lib\ffmpeg*\tools\**\bin",
        r"C:\ffmpeg\bin",
    ):
        dirs.extend(glob.glob(pattern, recursive=True))
    pairs = []
    for directory in dict.fromkeys(dirs):
        if not directory:
            continue
        if os.sep + "chocolatey" + os.sep + "bin" in directory.lower() + os.sep:
            continue  # chocolatey shims, not FFmpeg
        pair = (os.path.join(directory, "ffmpeg.exe"), os.path.join(directory, "ffprobe.exe"))
        if not all(os.path.isfile(p) for p in pair):
            continue
        if os.path.getsize(pair[0]) == os.path.getsize(pair[1]):
            continue  # identical files: a shim pair
        pairs.append(pair)
    pairs.sort(key=lambda p: sum(os.path.getsize(x) for x in p))
    for pair in pairs:
        if runs_as_ffmpeg(pair[0], "ffmpeg version") and runs_as_ffmpeg(pair[1], "ffprobe version"):
            return pair
    return None


def runs_as_ffmpeg(exe, expected):
    """True if <exe> -version prints the version line we expect."""
    try:
        proc = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and (proc.stdout or "").lower().startswith(expected.lower())


def vlc_dir():
    """The VLC install folder, found the same way python-vlc finds it."""
    import winreg
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"Software\VideoLAN\VLC") as key:
                install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
        except OSError:
            continue
        if install_dir and os.path.isfile(os.path.join(install_dir, "libvlc.dll")):
            return install_dir
    for candidate in (r"C:\Program Files\VideoLAN\VLC", r"C:\Program Files (x86)\VideoLAN\VLC"):
        if os.path.isfile(os.path.join(candidate, "libvlc.dll")):
            return candidate
    return None


SPEC_TEMPLATE = '''# Generated by build_gui_exe.py - do not edit by hand.
# One-folder and windowed, carrying icon-256x256.ico and everything the GUI needs at
# run time except yt-dlp.
#
# Windowed means no console window sits behind the GUI. The interactive MP3
# renamer - banner, colours, input() prompts - is this same exe called with
# --renamer: the launcher allocates a console window for that copy, so one
# program covers both jobs. See run_renamer in the launcher and run_mp3_renamer
# in the .pyw.
#
# One-folder rather than one-file: the exe starts straight from the files beside it
# instead of unpacking ~550 MB into a temporary folder first, and it has no
# temporary folder to clean up after the window closes.

block_cipher = None

gui = Analysis(
    [{launcher!r}],
    pathex=[{pathex!r}],
    binaries={binaries},
    datas={datas},
    hiddenimports={hidden},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

gui_pyz = PYZ(gui.pure)

gui_exe = EXE(
    gui_pyz,
    gui.scripts,
    [],
    exclude_binaries=True,
    name={name!r},
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon!r},
    version={version!r},
)

# Everything that is not the program itself is collected beside it, in the
# "_internal" folder the exe reads when it starts. Nothing is unpacked to a
# temporary folder, so there is nothing to delete after the window closes.
gui_coll = COLLECT(
    gui_exe,
    gui.binaries,
    gui.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name={name!r},
)
'''


VERSION_FILE_TEMPLATE = '''# Generated by build_gui_exe.py - do not edit by hand.
# PyInstaller reads this as the version resource of the exe it builds.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=@QUAD@,
    prodvers=@QUAD@,
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904b0', [
        StringStruct('CompanyName', 'therealMKD'),
        StringStruct('FileDescription', 'yt-msd'),
        StringStruct('FileVersion', '@VERSION@'),
        StringStruct('InternalName', '@EXE_NAME@'),
        StringStruct('LegalCopyright', 'Apache License, Version 2.0'),
        StringStruct('OriginalFilename', '@EXE_NAME@.exe'),
        StringStruct('ProductName', 'yt-msd'),
        StringStruct('ProductVersion', '@VERSION@')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''


def write_version_file():
    """Write the version resource for the exe, from APP_VERSION in the .pyw.

    The same APP_VERSION the window shows and the installer is labelled with, so
    right-clicking yt-msd-gui.exe and choosing Properties reports the version the
    program reports, instead of 0.0.0.0.
    """
    version = app_version() or "0.0"
    numbers = (re.findall(r"\d+", version) + ["0", "0", "0", "0"])[:4]
    body = (VERSION_FILE_TEMPLATE
            .replace("@QUAD@", "(" + ", ".join(numbers) + ")")
            .replace("@VERSION@", version)
            .replace("@EXE_NAME@", EXE_NAME))
    with open(VERSION_FILE, "w", encoding="utf-8") as fh:
        fh.write(body)
    print("  -> %s (the exe will report version %s)" % (VERSION_FILE, version))
    return 0


def write_spec():
    if write_version_file():
        return 1
    ffmpeg = ffmpeg_pair()
    vlc = vlc_dir()
    if not ffmpeg:
        print("  FFmpeg was not found. Install it, or set YTMSD_FFMPEG_DIR to its folder.")
        return 1
    if not vlc:
        print("  VLC was not found. Install VLC Media Player (python-vlc needs libvlc.dll).")
        return 1
    binaries = [
        (ffmpeg[0], "."),
        (ffmpeg[1], "."),
        (os.path.join(vlc, "libvlc.dll"), "."),
        (os.path.join(vlc, "libvlccore.dll"), "."),
    ]
    # icon-256x256.ico is unpacked next to the app so the GUI can load it for the title
    # bar, the taskbar button and the tray (see app_icon() in the .pyw).
    datas = [(ICON, ".")]
    plugins = os.path.join(vlc, "plugins")
    if os.path.isdir(plugins):
        datas.append((plugins, "plugins"))
    if len(datas) < 2:
        print("  note: no VLC plugin folder at %s - playback would fail" % plugins)
    spec = SPEC_TEMPLATE.format(
        launcher=LAUNCHER,
        pathex=BUILD_DIR,
        binaries=repr(binaries),
        datas=repr(datas),
        hidden=repr([MODULE_NAME]),
        name=EXE_NAME,
        icon=ICON,
        version=VERSION_FILE,
    )
    with open(SPEC_PATH, "w", encoding="utf-8") as fh:
        fh.write(spec)
    print("  -> %s (builds the %s folder)" % (SPEC_PATH, EXE_NAME))
    print("  bundled into it:")
    for path, _ in binaries:
        print("    %s (%.1f MB)" % (path, os.path.getsize(path) / 1048576.0))
    print("    %s (%.1f KB, the title bar / taskbar / tray icon)"
          % (ICON, os.path.getsize(ICON) / 1024.0))
    if len(datas) > 1:
        count = sum(len(files) for _, _, files in os.walk(plugins))
        size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(plugins) for f in fs)
        print("    %s (%d files, %.1f MB)" % (plugins, count, size / 1048576.0))
    return 0


def cmd_exe():
    if not pyd_is_current():
        if cmd_pyd():
            return 1
    if write_launcher():
        return 1
    if write_spec():
        return 1
    print("packaging with PyInstaller (one folder carrying PySide6 + FFmpeg + VLC;")
    print("a few minutes)...")
    # No --specpath: PyInstaller takes the spec location from the .spec file itself.
    # --distpath is the folder it writes into, and a one-folder build writes a
    # folder of its own named after the program: "<distpath>/yt-msd-gui/".
    if run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", DIST_DIR,
            "--workpath", os.path.join(BUILD_DIR, "pyinstaller"),
            SPEC_PATH]):
        return 1
    if not os.path.exists(EXE_PATH):
        print("  expected %s but it was not produced" % EXE_PATH)
        return 1
    # The one-file exe this script used to build sits in the same place. It is the
    # same program, only slower to start and slower to close, so it is not kept.
    if os.path.isfile(LEGACY_EXE_PATH):
        os.remove(LEGACY_EXE_PATH)
        print("  removed the old one-file build: %s" % LEGACY_EXE_PATH)
    carry_settings()
    count, size = folder_stats(APP_DIR)
    print("  -> %s (windowed GUI, and the renamer with --renamer)" % EXE_PATH)
    print("     %s beside it: %d files, %.1f MB"
          % (os.path.join(APP_DIR, "_internal"), count, size / 1048576.0))
    return 0


def carry_settings():
    """Copy an existing gui_config.json next to the new exe.

    yt-msd keeps its settings beside whichever copy of it is running, and the
    one-folder build moved the program into a folder of its own. Without this a
    rebuild would start the app with a blank configuration. The original is left in
    place so running the .pyw directly is unaffected.
    """
    old = os.path.join(DIST_DIR, "gui_config.json")
    new = os.path.join(APP_DIR, "gui_config.json")
    if os.path.isfile(old) and not os.path.exists(new):
        shutil.copy2(old, new)
        print("  carried the settings across: %s -> %s" % (old, new))


def folder_stats(folder):
    """(file count, total bytes) for a built folder."""
    count = 0
    size = 0
    for root, _, files in os.walk(folder):
        for name in files:
            count += 1
            try:
                size += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return count, size


def find_iscc():
    """The Inno Setup compiler, wherever it is. YTMSD_ISCC points at it by hand."""
    candidates = [os.environ.get("YTMSD_ISCC"), shutil.which("iscc")]
    for pattern in (
        r"%LOCALAPPDATA%\Programs\Inno Setup *\iscc.exe",
        r"%PROGRAMFILES%\Inno Setup *\iscc.exe",
        r"%PROGRAMFILES(X86)%\Inno Setup *\iscc.exe",
    ):
        candidates.extend(sorted(glob.glob(os.path.expandvars(pattern)), reverse=True))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def app_version():
    """The version string the GUI carries, so the installer is labelled with it."""
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]*)"', source_text(), re.MULTILINE)
    return match.group(1) if match else ""


ISS_TEMPLATE = """; Generated by build_gui_exe.py - do not edit by hand.
;
; One file to download. This installer unpacks the one-folder build - yt-msd-gui.exe
; and the _internal folder beside it - into one folder, and adds a Start menu
; shortcut (and a desktop one if asked for).
;
; The default folder is per-user on purpose: yt-msd writes its gui_config.json next
; to its own exe, and %LOCALAPPDATA% is writable without an administrator. The
; folder can still be changed on the wizard's second page.
;
; gui_config.json is left out of the package on purpose - it holds whoever built the
; installer's own settings (folders, playlists, window size). A new install starts at
; the defaults, and an update over an existing install keeps the settings that install
; already has, because nothing here deletes a file the package does not carry.
;
; The _internal folder is the one thing that IS cleared first. Every build ships a
; complete one, and a file an earlier build left behind is not part of this one -
; nothing would ever remove it, so an install that is updated a few times would grow
; a little at a time with DLLs no one loads any more.

[Setup]
AppName=yt-msd
AppVersion=@APP_VERSION@
AppPublisher=therealMKD
AppPublisherURL=https://github.com/therealMKD/yt-msd
AppSupportURL=https://github.com/therealMKD/yt-msd/issues
AppUpdatesURL=https://github.com/therealMKD/yt-msd/releases
DefaultDirName={localappdata}\\Programs\\yt-msd
DefaultGroupName=yt-msd
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=@OUTPUT_DIR@
OutputBaseFilename=@OUTPUT_NAME@
SetupIconFile=@ICON@
UninstallDisplayIcon={app}\\@EXE_NAME@.exe
UninstallDisplayName=yt-msd
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
@VERSION_LINE@
[Files]
Source: "@APP_DIR@\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "gui_config.json"

[Icons]
Name: "{autoprograms}\\yt-msd"; Filename: "{app}\\@EXE_NAME@.exe"
Name: "{autodesktop}\\yt-msd"; Filename: "{app}\\@EXE_NAME@.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\\@EXE_NAME@.exe"; Description: "Start yt-msd"; Flags: nowait postinstall skipifsilent

[Code]
// [InstallDelete] would be the obvious way to do this and it is the wrong one: Inno
// processes it after [Files], so it would delete the folder this setup has only just
// copied. PrepareToInstall runs before any of the install steps, which is the only
// point at which the older files can be cleared out first. (Comments here have to
// be "//": in this section the file is read as Pascal, where a semicolon ends a
// statement instead of starting a comment.)
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  OldInternal: string;
begin
  OldInternal := ExpandConstant('{app}\\_internal');
  if DirExists(OldInternal) then begin
    if not DelTree(OldInternal, True, True, True) then
      MsgBox('Could not remove the older yt-msd files in ' + OldInternal + '. Close yt-msd if it is running, then run this setup again.', mbError, MB_OK);
  end;
  Result := '';
end;
"""


def write_iss():
    version = app_version()
    numbers = re.findall(r"\d+", version)
    iss = (ISS_TEMPLATE
           .replace("@APP_VERSION@", version or "development")
           .replace("@VERSION_LINE@",
                    ("VersionInfoVersion=%s" % ".".join(numbers[:4])) if numbers else "")
           .replace("@APP_DIR@", APP_DIR)
           .replace("@OUTPUT_DIR@", DIST_DIR)
           .replace("@OUTPUT_NAME@", SETUP_NAME)
           .replace("@EXE_NAME@", EXE_NAME)
           .replace("@ICON@", ICON))
    with open(ISS_PATH, "w", encoding="utf-8") as fh:
        fh.write(iss)
    print("  -> %s (installs %s)" % (ISS_PATH, APP_DIR))
    return 0


def cmd_installer():
    if not os.path.isfile(EXE_PATH):
        print("nothing to pack at %s - run 'python build_gui_exe.py exe' first" % EXE_PATH)
        return 1
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup (iscc.exe) was not found, so no installer was built.")
        print("  install it:  winget install --id JRSoftware.InnoSetup -e")
        print("  or point at it:  set YTMSD_ISCC=C:\\path\\to\\iscc.exe")
        print("  %s still runs as it is - it is just not one file yet." % APP_DIR)
        return 1
    if write_iss():
        return 1
    count, size = folder_stats(APP_DIR)
    print("packing %d files (%.1f MB) into one installer with LZMA at its highest"
          % (count, size / 1048576.0))
    print("setting - a minute or two...")
    if run([iscc, ISS_PATH]):
        return 1
    if not os.path.isfile(SETUP_PATH):
        print("  expected %s but it was not produced" % SETUP_PATH)
        return 1
    print("  -> %s (%.1f MB, the one file an end user downloads)"
          % (SETUP_PATH, os.path.getsize(SETUP_PATH) / 1048576.0))
    print("     it installs into %LOCALAPPDATA%\\Programs\\yt-msd and adds a Start menu shortcut.")
    return 0


USAGE = """usage: python build_gui_exe.py <command>

  pyd        build build_dir_cython/yt_msd_gui.pyd from GUI Source Code/yt_msd_gui.pyx
  launcher   write the launcher and the PyInstaller .spec
  exe        build GUI Source Code/yt-msd-gui/ (one folder: the windowed exe + _internal)
  installer  pack that folder into GUI Source Code/yt-msd-setup.exe (needs Inno Setup)
  all        pyd + launcher + exe + installer

That one exe is two programs: run it as it is and it opens the GUI window; run
it with --renamer (or -r) and it opens a console and runs the MP3 renamer CLI.
The GUI reaches its own renamer half the same way, by re-running itself.

The exe only runs with its _internal folder beside it, which is why the last step
exists: yt-msd-setup.exe is the single file an end user downloads, and running it
puts the folder somewhere on their machine and gives them a Start menu shortcut.

Environment: YTMSD_FFMPEG_DIR overrides the automatic FFmpeg lookup.
           YTMSD_ISCC points at iscc.exe when it is not in one of the usual places.
"""


def main(argv):
    args = argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if args[0] == "pyd":
        return cmd_pyd()
    if args[0] == "launcher":
        return cmd_launcher()
    if args[0] == "exe":
        return cmd_exe()
    if args[0] == "installer":
        return cmd_installer()
    if args[0] == "all":
        for step in (cmd_pyd, cmd_exe, cmd_installer):
            if step():
                return 1
        return 0
    print("unknown command: %s\n" % args[0])
    print(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
