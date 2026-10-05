#!/usr/bin/env python3
"""Build (and optionally install) the yt-msd MusicBee plugin.

The plugin is a thin shim: it puts "Tools > yt-msd" inside MusicBee so the yt-msd
program can be opened from there, and when yt-msd is closed it hands any file
MusicBee does not already know about to MusicBee's library, so new downloads and
renamed files show up without a manual import.

No .NET SDK is needed. The plugin is compiled with a C# compiler that is already on
this machine - Roslyn from Visual Studio / Build Tools if present, otherwise the
.NET Framework's own csc.exe. The plugin targets .NET Framework 4.x, which is what
MusicBee itself runs on.

    python "MusicBee Plugin/build_mb_plugin.py"              compile into MusicBee Plugin\release\
    python "MusicBee Plugin/build_mb_plugin.py" --install    compile and copy into MusicBee's plugin folder
    python "MusicBee Plugin/build_mb_plugin.py" --clean      delete the release folder and stop
    python "MusicBee Plugin/build_mb_plugin.py" --exe PATH   which yt-msd program the menu entry opens
    python "MusicBee Plugin/build_mb_plugin.py" --dir PATH   folder the plugin may search for it in (repeat this)
    python "MusicBee Plugin/build_mb_plugin.py" --folder PATH  folder to rescan (repeat this)

The compiled plugin is committed in MusicBee Plugin\\release\\, so installing on another
machine is just copying mb_YtMsd.dll into MusicBee's plugin folder. The mb_YtMsd.ini
committed there is a commented template with no paths in it - the plugin works without
an ini at all, finding the yt-msd the installer put there and rescanning MusicBee's own
folders. --install writes an ini with the real paths of the machine it is run on. This
script is only needed to rebuild after the C# sources change.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BUILD_DIR = os.path.join(HERE, "release")
DLL_NAME = "mb_YtMsd.dll"
CONFIG_NAME = "mb_YtMsd.ini"
SOURCES = ["MusicBeeInterface.cs", "Plugin.cs", "Rescan.cs", "Config.cs"]
REFERENCES = ["System.Windows.Forms.dll", "System.Drawing.dll"]

FRAMEWORK_DIRS = [
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319",
    r"C:\Windows\Microsoft.NET\Framework\v4.0.30319",
]

MUSICBEE_APPDATA_PLUGINS = os.path.join(
    os.environ.get("APPDATA", ""), "MusicBee", "Plugins")
MUSICBEE_PROGRAMS_PLUGINS = os.path.join(
    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "MusicBee", "Plugins")


def find_csc():
    """Return the first C# compiler found, preferring Roslyn over the legacy one."""
    candidates = []
    for pattern in (
        r"C:\Program Files*\Microsoft Visual Studio\*\*\MSBuild\Current\Bin\Roslyn\csc.exe",
        r"C:\Program Files*\Microsoft Visual Studio\*\*\MSBuild\Current\Bin\csc.exe",
    ):
        candidates.extend(sorted(glob.glob(pattern), reverse=True))
    for framework in FRAMEWORK_DIRS:
        candidates.append(os.path.join(framework, "csc.exe"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def default_exe():
    """The yt-msd program the menu entry should open.

    yt-msd is built as a folder now (an exe plus its _internal folder) and shipped
    as a single installer, so the two places it is normally found are this repo's
    GUI Source Code\\yt-msd-gui\\ and the folder yt-msd-setup.exe installs into.
    """
    candidates = [
        os.path.join(REPO, "GUI Source Code", "yt-msd-gui", "yt-msd-gui.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "yt-msd", "yt-msd-gui.exe"),
        os.path.join(REPO, "GUI Source Code", "yt-msd-gui.exe"),  # an older one-file build
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    found = [exe for exe in glob.glob(os.path.join(REPO, "GUI Source Code", "*", "*.exe"))
             if "setup" not in os.path.basename(exe).lower()]
    if found:
        return max(found, key=os.path.getmtime)
    found = glob.glob(os.path.join(REPO, "GUI Version", "*.exe"))
    if found:
        return max(found, key=os.path.getmtime)
    return candidates[0]


def default_search_dirs():
    """Folders the plugin may search for the program when exe= names nothing.

    The plugin looks in each dir= folder and one level below it, so naming the
    folder above the program survives the layout underneath it changing - a one-file
    build becoming a folder build, for instance.
    """
    dirs = []
    for candidate in (
        os.path.join(REPO, "GUI Source Code"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "yt-msd"),
    ):
        if candidate and os.path.isdir(candidate) and candidate not in dirs:
            dirs.append(candidate)
    return dirs


def default_folders():
    """Folders the plugin will walk after yt-msd closes."""
    folders = []
    music = os.path.join(os.environ.get("USERPROFILE", ""), "Music")
    if os.path.isdir(music):
        folders.append(music)
    return folders


def compile_plugin(csc):
    os.makedirs(BUILD_DIR, exist_ok=True)
    out = os.path.join(BUILD_DIR, DLL_NAME)
    if os.path.isfile(out):
        try:
            os.remove(out)
        except OSError as exc:
            raise SystemExit(
                "cannot replace " + out + " - it is being held open by another program "
                "(MusicBee will hold the plugin while it is running). Close it and try again: " + str(exc))

    cmd = [csc, "/nologo", "/target:library", "/platform:anycpu", "/optimize+",
           "/nowarn:1591", "/out:" + out]
    for framework in FRAMEWORK_DIRS:
        if os.path.isdir(framework):
            cmd.append("/lib:" + framework)
    for reference in REFERENCES:
        cmd.append("/r:" + reference)
    for source in SOURCES:
        path = os.path.join(HERE, source)
        if not os.path.isfile(path):
            raise SystemExit("missing source file: " + path)
        cmd.append(path)

    print("compiling with: " + csc)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr.strip():
            print(result.stderr.rstrip())
        raise SystemExit("compile failed")
    if not os.path.isfile(out):
        raise SystemExit("compiler produced no " + DLL_NAME)

    print("built: " + out + " (%d KB)" % (os.path.getsize(out) // 1024))
    return out


HEADER = [
    "# yt-msd MusicBee plugin settings.",
    "# exe    = the yt-msd program the Tools > yt-msd menu entry opens",
    "# dir    = a folder to search for it in (repeat as needed)",
    "# folder = a folder to scan for new files after yt-msd closes (repeat as needed)",
    "# maxfiles = safety limit on how many files one scan will look at",
    "# interval = seconds between scans while yt-msd is open (0 = only after it closes)",
]

# The ini committed in MusicBee Plugin\release\: every setting explained, no paths.
# It is the file that gets copied to other machines, and a path from this one is a
# dead path on the next, so it stays commented out. --install writes an ini with the
# real paths of the machine it is run on instead.
TEMPLATE = HEADER + [
    "#",
    "# Nothing here is required. With no uncommented lines the plugin looks for",
    "# yt-msd in the folder yt-msd-setup.exe installs into",
    "# (%LOCALAPPDATA%\\Programs\\yt-msd) and rescans MusicBee's own download folder",
    "# and your Music folder.",
    "#",
    "# Uncomment to point at a yt-msd that lives somewhere else - a source checkout",
    "# run from the .pyw, a copy on another drive:",
    "#",
    "# exe=C:\\Users\\you\\yt-msd\\GUI Source Code\\yt-msd-gui\\yt-msd-gui.exe",
    "# dir=C:\\Users\\you\\yt-msd\\GUI Source Code",
    "#",
    "# A dir= is searched before the installed folder. A search looks inside the",
    "# folder and one level below it for yt-msd-gui.exe or yt-msd.exe first, then",
    "# for yt-msd-gui.pyw or yt-msd.pyw.",
    "#",
    "# folder=C:\\Users\\you\\Music",
    "# maxfiles=3000",
    "# interval=30",
]


def write_lines(lines, path):
    with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write("\n".join(lines) + "\n")
    print("wrote: " + path)
    return path


def write_template():
    """Write the path-free settings template into MusicBee Plugin\\release\\."""
    return write_lines(TEMPLATE, os.path.join(BUILD_DIR, CONFIG_NAME))


def config_lines(exe, search_dirs, folders, max_files, interval):
    """Settings for the machine being built on, with its real paths in them."""
    lines = list(HEADER)
    if exe:
        lines.append("exe=" + exe)
    for search_dir in search_dirs:
        lines.append("dir=" + search_dir)
    for folder in folders:
        lines.append("folder=" + folder)
    lines.append("maxfiles=%d" % max_files)
    lines.append("interval=%d" % interval)
    return lines


def install(plugin_dir, ini_lines):
    """Put the plugin, and a settings file for this machine, into a MusicBee folder."""
    os.makedirs(plugin_dir, exist_ok=True)
    source = os.path.join(BUILD_DIR, DLL_NAME)
    if not os.path.isfile(source):
        raise SystemExit("not built yet: " + DLL_NAME + " (run this script without --install first)")
    shutil.copy2(source, os.path.join(plugin_dir, DLL_NAME))
    print("installed: " + os.path.join(plugin_dir, DLL_NAME))

    target = os.path.join(plugin_dir, CONFIG_NAME)
    if os.path.isfile(target):
        print("kept the settings already in " + target)
        print("      delete that file and run --install again to replace them")
    else:
        write_lines(ini_lines, target)


def main():
    parser = argparse.ArgumentParser(description="Build the yt-msd MusicBee plugin.")
    parser.add_argument("--install", action="store_true",
                        help="copy the plugin into MusicBee's plugin folder")
    parser.add_argument("--plugin-dir", default=MUSICBEE_APPDATA_PLUGINS,
                        help="where --install copies the plugin (default: %s)" % MUSICBEE_APPDATA_PLUGINS)
    parser.add_argument("--exe", default=None, help="yt-msd program the menu entry opens")
    parser.add_argument("--dir", action="append", default=None,
                        help="folder the plugin may search for yt-msd in (repeatable)")
    parser.add_argument("--folder", action="append", default=None,
                        help="folder to rescan after yt-msd closes (repeatable)")
    parser.add_argument("--maxfiles", type=int, default=3000, help="scan safety limit")
    parser.add_argument("--interval", type=int, default=30,
                        help="seconds between library scans while yt-msd is open (0 = only after it closes)")
    parser.add_argument("--clean", action="store_true", help="delete the release folder and stop")
    args = parser.parse_args()

    if args.clean:
        if os.path.isdir(BUILD_DIR):
            try:
                shutil.rmtree(BUILD_DIR)
                print("removed: " + BUILD_DIR)
            except OSError as exc:
                print("could not fully remove " + BUILD_DIR + ": " + str(exc))
                return 1
        return 0

    csc = find_csc()
    if not csc:
        print("No C# compiler found. Install Visual Studio Build Tools (.NET desktop")
        print("workload) or a .NET SDK, then run this script again.")
        return 1

    compile_plugin(csc)
    write_template()

    if args.install:
        exe = args.exe or default_exe()
        search_dirs = list(args.dir) if args.dir else default_search_dirs()
        if exe and os.path.isfile(exe):
            parent = os.path.dirname(exe)
            if parent and parent not in search_dirs:
                search_dirs.insert(0, parent)
        else:
            print("note: no yt-msd program at " + str(exe) + " - the settings written")
            print("      below name folders to search instead, so it still works.")
            exe = None

        try:
            install(args.plugin_dir,
                    config_lines(exe, search_dirs,
                                 args.folder or default_folders(),
                                 args.maxfiles,
                                 args.interval))
        except (PermissionError, OSError) as exc:
            print("Cannot write to " + args.plugin_dir + " (" + str(exc) + ")")
            print("Run this from an elevated prompt, or in MusicBee use")
            print("Options > Plugins > Add and pick " + os.path.join(BUILD_DIR, DLL_NAME))
            return 1

    print()
    print("Next steps:")
    print("  1. start MusicBee, open Options > Plugins")
    print("  2. enable the 'yt-msd' plugin, restart MusicBee")
    print("  3. Tools > yt-msd opens yt-msd; the library refreshes while it is open")
    if not args.install:
        print("     Copy " + os.path.join(BUILD_DIR, DLL_NAME) + " into a plugin folder first.")
        print("     The mb_YtMsd.ini written into " + BUILD_DIR + " is a template with no")
        print("     paths in it - the plugin needs no settings file at all, and --install")
        print("     writes one with this machine's real paths.")
    print("Plugin folders MusicBee accepts: " + MUSICBEE_APPDATA_PLUGINS)
    print("                          or also: " + MUSICBEE_PROGRAMS_PLUGINS + " (needs admin)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
