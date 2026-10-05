# Open Source Software under the Apache License, Version 2.0
#
# Build the compiled Windows executable for the yt-msd GUI.
#
# This is the second half of the pipeline started by build_gui_cython.py:
#
#   GUI Source Code/yt-msd-gui.pyw            the master source, unchanged
#   GUI Source Code/yt_msd_gui.pyx            the same text as a Cython module
#   build_dir_cython/yt_msd_gui.c             Cython's C output
#   build_dir_cython/yt_msd_gui.pyd           that C, compiled with MSVC
#   build_dir_cython/yt_msd_gui_launcher.py   the entry point (generated, see below)
#   dist/yt-msd-gui.exe                       the packaged program
#
# The exe carries every runtime dependency except yt-dlp, which stays a separate
# install: the compiled GUI itself, PySide6, mutagen, Pillow, watchdog,
# python-vlc, libvlc.dll + libvlccore.dll + the VLC plugin folder, and
# ffmpeg.exe + ffprobe.exe.
#
# Commands
#   python build_gui_exe.py pyd       .pyx -> .c -> build_dir_cython/yt_msd_gui.pyd
#   python build_gui_exe.py launcher  write the launcher and the PyInstaller .spec
#   python build_gui_exe.py exe       build dist/yt-msd-gui.exe
#   python build_gui_exe.py all       pyd + launcher + exe
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
ICON = os.path.join(ROOT, "GUI Source Code", "icon.ico")
DIST_DIR = os.path.join(ROOT, "dist")
EXE_PATH = os.path.join(DIST_DIR, "%s.exe" % EXE_NAME)
C_PATH = os.path.join(BUILD_DIR, "%s.c" % MODULE_NAME)


def find_pyd():
    """The compiled extension, whatever suffix setuptools gave it.

    setuptools names it after the running interpreter, e.g.
    yt_msd_gui.cp314-win_amd64.pyd. That is the name Python and PyInstaller
    look for, so it is left as it is.
    """
    found = glob.glob(os.path.join(BUILD_DIR, "%s*.pyd" % MODULE_NAME))
    return max(found, key=os.path.getmtime) if found else None


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
# Entry point for the compiled GUI. PyInstaller cannot see the imports inside a
# compiled .pyd, so they are restated here (copied from yt-msd-gui.pyw) and
# nothing is left out of the bundle. The .pyw's entry block (the body of its
# "if __name__ == \"__main__\":") is then run inside the compiled module, which
# is what the .pyw does when it is run directly.
import os
import sys

if getattr(sys, "frozen", False):
    # ffmpeg.exe, ffprobe.exe, libvlc.dll, libvlccore.dll and the VLC plugins
    # are unpacked into the application folder. Putting that folder on PATH is
    # how the plain "ffmpeg"/"ffprobe" calls, yt-dlp's --ffmpeg-location and
    # python-vlc's libvlc.dll lookup all find them.
    _app_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    os.environ["PATH"] = _app_dir + os.pathsep + os.environ.get("PATH", "")

# Dependencies of the compiled module. The try/except mirrors the .pyw, which
# imports python-vlc the same way and reports a missing VLC itself.
try:
'''


LAUNCHER_TAIL = '''except Exception:  # the compiled module reports missing optional dependencies
    pass

import {module}

ENTRY_BLOCK = r\'\'\'
{entry}\'\'\'
exec(compile(ENTRY_BLOCK, {pyw!r}, "exec"), {module}.__dict__)
'''


def write_launcher():
    imports = collect_import_lines()
    entry = collect_entry_block()
    body = "".join("    " + line + "\n" for line in imports)
    tail = LAUNCHER_TAIL.format(module=MODULE_NAME, entry=entry, pyw=os.path.basename(PYW))
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(LAUNCHER, "w", encoding="utf-8") as fh:
        fh.write(LAUNCHER_HEAD + body + tail)
    print("  -> %s (%d import lines)" % (LAUNCHER, len(imports)))
    return 0


def cmd_launcher():
    return write_launcher()


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
# Onefile + windowed (the .pyw has no console), with icon.ico, and everything
# the GUI needs at run time except yt-dlp.

block_cipher = None

a = Analysis(
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

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name={name!r},
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon!r},
)
'''


def write_spec():
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
    plugins = os.path.join(vlc, "plugins")
    datas = [(plugins, "plugins")] if os.path.isdir(plugins) else []
    if not datas:
        print("  note: no VLC plugin folder at %s - playback would fail" % plugins)
    spec = SPEC_TEMPLATE.format(
        launcher=LAUNCHER,
        pathex=BUILD_DIR,
        binaries=repr(binaries),
        datas=repr(datas),
        hidden=repr([MODULE_NAME]),
        name=EXE_NAME,
        icon=ICON,
    )
    with open(SPEC_PATH, "w", encoding="utf-8") as fh:
        fh.write(spec)
    print("  -> %s" % SPEC_PATH)
    print("  bundling:")
    for path, _ in binaries:
        print("    %s (%.1f MB)" % (path, os.path.getsize(path) / 1048576.0))
    if datas:
        count = sum(len(files) for _, _, files in os.walk(plugins))
        size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(plugins) for f in fs)
        print("    %s (%d files, %.1f MB)" % (plugins, count, size / 1048576.0))
    return 0


def cmd_exe():
    if not find_pyd():
        print("no compiled module yet - building it first")
        if cmd_pyd():
            return 1
    if write_launcher():
        return 1
    if write_spec():
        return 1
    print("packaging with PyInstaller (PySide6 + FFmpeg + VLC: a few minutes)...")
    # No --specpath: PyInstaller takes the spec location from the .spec file itself.
    if run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", DIST_DIR,
            "--workpath", os.path.join(BUILD_DIR, "pyinstaller"),
            SPEC_PATH]):
        return 1
    if not os.path.exists(EXE_PATH):
        print("  expected %s but it was not produced" % EXE_PATH)
        return 1
    print("  -> %s (%.1f MB)" % (EXE_PATH, os.path.getsize(EXE_PATH) / 1048576.0))
    return 0


USAGE = """usage: python build_gui_exe.py <command>

  pyd       build build_dir_cython/yt_msd_gui.pyd from GUI Source Code/yt_msd_gui.pyx
  launcher  write build_dir_cython/yt_msd_gui_launcher.py and the PyInstaller .spec
  exe       build dist/yt-msd-gui.exe (onefile, windowed, icon.ico)
  all       pyd + launcher + exe

Environment: YTMSD_FFMPEG_DIR overrides the automatic FFmpeg lookup.
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
    if args[0] == "all":
        for step in (cmd_pyd, cmd_exe):
            if step():
                return 1
        return 0
    print("unknown command: %s\n" % args[0])
    print(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
