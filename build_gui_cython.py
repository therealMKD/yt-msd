# Open Source Software under the Apache License, Version 2.0
#
# Build tooling for the Cython path of the yt-msd GUI.
#
# Nothing in this script changes how yt-msd behaves - it only moves source text around:
#
#   GUI Source Code/yt-msd-gui.pyw    the source you run today; it stays the master copy
#   GUI Source Code/yt_msd_gui.pyx    the Cython source: the .pyw text with a directive header on top
#   build_dir_cython/yt_msd_gui.c     the C source Cython writes from the .pyx (gitignored)
#
# The .pyx is named "yt_msd_gui.pyx" because Cython rejects "yt-msd-gui" - a hyphen is not a
# legal module name, and Cython will not take a .pyw as input.
#
# Commands
#   python build_gui_cython.py sync         write / refresh the .pyx from the .pyw
#   python build_gui_cython.py verify       prove the .pyx body is still identical to the .pyw
#   python build_gui_cython.py c            transpile the .pyx -> build_dir_cython/yt_msd_gui.c
#   python build_gui_cython.py c --embed    same, plus a main() so cl.exe can link an .exe from it
#   python build_gui_cython.py check        transpile into a temp folder and report Cython's
#                                           errors/warnings without leaving anything in the repo
#
# Not done here (later steps): compile the .c with MSVC into a .pyd extension (setuptools) or
# into an .exe (cl.exe), then package it. MSVC and the Windows SDK are auto-detected by
# setuptools from a plain PowerShell prompt - see requirements-build.txt for the verified
# toolchain (Cython 3.3.0, MSVC 14.44 / 14.50, Python 3.14).
#
# Verified on this machine while setting this up:
#   - the 9900-line source transpiles with no errors and no warnings;
#   - "cython --embed" + cl.exe gives a program whose __name__ is "__main__", so the
#     "if __name__ == \"__main__\":" block at the end of the source runs exactly as it does now;
#   - the one thing to watch at that stage: in an --embed build, sys.modules["__main__"] is the
#     interpreter's own module object rather than this module's globals, so the single place that
#     reads sys.modules[__name__] (the python-vlc import-error text) would fall back to its
#     default wording. Building a .pyd plus a small launcher keeps that lookup working.

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(ROOT, "GUI Source Code", "yt-msd-gui.pyw")
PYX = os.path.join(ROOT, "GUI Source Code", "yt_msd_gui.pyx")
BUILD_DIR = os.path.join(ROOT, "build_dir_cython")
MODULE_NAME = "yt_msd_gui"

# "verify" cuts on this line: everything after it must stay byte-identical to the .pyw, which
# is what keeps the compiled build behaviourally identical to the script.
END_MARKER = "# ---- END OF CYTHON HEADER - the unchanged yt-msd-gui.pyw source follows ----"

HEADER = """# Open Source Software under the Apache License, Version 2.0
# PySide6 version of yt-msd - Cython source for the compiled GUI build
#
# Everything after the END OF CYTHON HEADER line below is the text of
# "GUI Source Code/yt-msd-gui.pyw" copied byte-for-byte, so the compiled program behaves
# exactly like the script. Edit the .pyw, then run:
#     python build_gui_cython.py sync      (rewrites this file from the .pyw)
#     python build_gui_cython.py verify    (checks the two are still identical)
#
# The directives are all set to keep Python semantics unchanged:
#   language_level=3         Python 3 rules for division, print, str/bytes, comparisons.
#   annotation_typing=False  "def f(x: int) -> Optional[str]" hints stay documentation, so no
#                            argument or return value is type-checked or converted at call time.
#   infer_types=False        no variable is given a C int/float type, so large integers, None
#                            handling and error messages stay exactly Python's own.
#   binding=True             closures and nested functions capture names the way Python does.
# cython: language_level=3
# cython: annotation_typing=False
# cython: infer_types=False
# cython: binding=True
#
""" + END_MARKER + "\n"


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def pyx_body(data):
    # Return the part of a .pyx that follows the header marker, or None if there is no marker.
    for nl in (b"\r\n", b"\n"):
        marker = END_MARKER.encode("utf-8") + nl
        idx = data.find(marker)
        if idx >= 0:
            return data[idx + len(marker):]
    return None


def cmd_sync():
    pyw = read_bytes(PYW)
    wanted = HEADER.encode("utf-8") + pyw
    current = read_bytes(PYX) if os.path.exists(PYX) else None
    if current == wanted:
        print("already in sync: %s" % os.path.basename(PYX))
        return 0
    with open(PYX, "wb") as fh:
        fh.write(wanted)
    print("wrote %s from %s (%d bytes, %d source lines)"
          % (os.path.basename(PYX), os.path.basename(PYW), len(wanted), pyw.count(b"\n")))
    return 0


def cmd_verify():
    pyw = read_bytes(PYW)
    if not os.path.exists(PYX):
        print("MISSING: %s (run: python build_gui_cython.py sync)" % os.path.basename(PYX))
        return 1
    body = pyx_body(read_bytes(PYX))
    if body is None:
        print("BAD HEADER: %s has no header marker; regenerate it with 'sync'." % os.path.basename(PYX))
        return 1
    if body == pyw:
        print("OK: the .pyx body is byte-identical to the .pyw (%d bytes)." % len(pyw))
        return 0
    print("OUT OF SYNC: the .pyw and the .pyx body differ.")
    print("  .pyw is %d bytes, the .pyx body is %d bytes" % (len(pyw), len(body)))
    print("Run: python build_gui_cython.py sync")
    return 1


def run_cython(out_c, embed):
    args = [sys.executable, "-m", "cython", "-o", out_c, PYX]
    if embed:
        args.append("--embed")
    proc = subprocess.run(args, capture_output=True, text=True)
    for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines():
        if line.strip():
            print("  cython: %s" % line)
    if proc.returncode != 0 or not os.path.exists(out_c):
        print("  cython failed")
        return 1
    print("  -> %s (%d bytes)" % (out_c, os.path.getsize(out_c)))
    return 0


def ensure_synced():
    if cmd_verify() == 0:
        return 0
    print("refreshing the .pyx from the .pyw first...")
    return cmd_sync()


def cmd_c(embed=False):
    if ensure_synced():
        return 1
    os.makedirs(BUILD_DIR, exist_ok=True)
    print("transpiling %s -> build_dir_cython\\%s.c%s"
          % (os.path.basename(PYX), MODULE_NAME, " (with a main())" if embed else ""))
    return run_cython(os.path.join(BUILD_DIR, "%s.c" % MODULE_NAME), embed)


def cmd_check():
    import shutil
    import tempfile
    if ensure_synced():
        return 1
    tmp = tempfile.mkdtemp(prefix="ytmsd_cython_check_")
    print("transpiling into a temp folder (nothing is written into the repo):")
    try:
        return run_cython(os.path.join(tmp, "%s.c" % MODULE_NAME), False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


USAGE = """usage: python build_gui_cython.py <command>

  sync     write / refresh GUI Source Code/yt_msd_gui.pyx from GUI Source Code/yt-msd-gui.pyw
  verify   check that the .pyx body is byte-identical to the .pyw
  c        transpile the .pyx to build_dir_cython/yt_msd_gui.c   (add --embed for a main())
  check    transpile into a temp folder and report Cython errors/warnings, repo left untouched
"""


def main(argv):
    args = [a for a in argv[1:]]
    embed = "--embed" in args
    args = [a for a in args if a != "--embed"]
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if args[0] == "sync":
        return cmd_sync()
    if args[0] == "verify":
        return cmd_verify()
    if args[0] == "c":
        return cmd_c(embed)
    if args[0] == "check":
        return cmd_check()
    print("unknown command: %s\n" % args[0])
    print(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))


