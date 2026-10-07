"""Checks for the download-queue skipping fix.

Pulls the new helper functions straight out of GUI Source Code/yt-msd-gui.pyw
with ast, so what is tested is the text that actually ships, and then feeds
them the yt-dlp output lines that used to be misread.
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PYW = os.path.join(ROOT, "GUI Source Code", "yt-msd-gui.pyw")

WANTED = {
    "_YTDLP_FINAL_PATH_PATTERNS", "_YTDLP_STAGED_PATH_PATTERNS",
    "_PERMANENT_DOWNLOAD_ERROR_MARKERS", "DOWNLOAD_ITEM_ATTEMPTS",
    "_clean_reported_path", "_match_reported_path", "_title_match_key",
    "_title_matches_filename", "_is_permanent_download_error",
}

with open(PYW, "r", encoding="utf-8") as fh:
    tree = ast.parse(fh.read())

picked = []
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in WANTED:
        picked.append(node)
    elif isinstance(node, ast.Assign):
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if names and all(n in WANTED for n in names):
            picked.append(node)

missing = WANTED - {getattr(n, "name", None) or "" for n in picked}
for node in picked:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                missing.discard(t.id)
if missing:
    raise SystemExit("could not find in the source: %s" % ", ".join(sorted(missing)))

ns = {"re": re, "os": os}
exec(compile(ast.Module(body=picked, type_ignores=[]), PYW, "exec"), ns)

match_reported = ns["_match_reported_path"]
title_matches = ns["_title_matches_filename"]
is_permanent = ns["_is_permanent_download_error"]

failures = []
checked = 0


def check(label, got, want):
    global checked
    checked += 1
    if got != want:
        failures.append("%s\n     got:  %r\n     want: %r" % (label, got, want))


P = r"C:\Music\Artist - Song [abc123]"

# The path lines yt-dlp really prints, in the shapes both old and new versions use.
check("ExtractAudio Destination",
      match_reported("[ExtractAudio] Destination: %s.m4a" % P),
      ("final", "%s.m4a" % P))
check("ExtractAudio not converting (quoted, old form)",
      match_reported('[ExtractAudio] Not converting audio "%s.m4a"; audio is already in m4a' % P),
      ("final", "%s.m4a" % P))
check("Not converting audio (bare, current form)",
      match_reported('Not converting audio "%s.m4a"; already is in target format m4a' % P),
      ("final", "%s.m4a" % P))
check("Not converting audio (no quotes at all)",
      match_reported("Not converting audio %s.m4a; already is in target format m4a" % P),
      ("final", "%s.m4a" % P))
check("already downloaded (quoted)",
      match_reported('[download] "%s.m4a" has already been downloaded' % P),
      ("final", "%s.m4a" % P))
check("already downloaded (unquoted)",
      match_reported("[download] %s.m4a has already been downloaded" % P),
      ("final", "%s.m4a" % P))
check("Merger",
      match_reported('[Merger] Merging formats into "%s.webm"' % P),
      ("final", "%s.webm" % P))
check("download Destination",
      match_reported("[download] Destination: %s.webm" % P),
      ("staged", "%s.webm" % P))

# Progress lines and errors must still not be mistaken for paths.
check("progress line",
      match_reported("[download]  45.3% of   3.20MiB at  1.12MiB/s ETA 00:02"),
      (None, ""))
check("error line",
      match_reported("ERROR: unable to download video data: HTTP Error 403: Forbidden"),
      (None, ""))
check("warning line",
      match_reported("WARNING: falling back to another format"),
      (None, ""))

# Titles are matched against the filename yt-dlp would have written.
check("colon in title",
      title_matches("Artist - Song (Official Video): HD", "Artist - Song (Official Video)_ HD.m4a"),
      True)
check("slash in title", title_matches("AC/DC - Thunder", "AC_DC - Thunder.mp3"), True)
check("quote in title", title_matches('Beyoncé - "Single Ladies"', "Beyoncé - _Single Ladies_.m4a"), True)
check("truncated title",
      title_matches("A" * 60 + " - Very Long Song Title That Goes On",
                    ("A" * 60 + " - Very Long Song Title") + ".mp3"),
      True)
check("different song", title_matches("Artist - Song", "Someone Else - Other.mp3"), False)
check("empty title", title_matches("", "whatever.mp3"), False)

# Retrying only makes sense for the failures a request can fix.
check("permanent: unavailable", is_permanent("ERROR: Video unavailable"), True)
check("permanent: private", is_permanent("ERROR: Private video. Sign in if you've been given a login"), True)
check("transient: 403", is_permanent("ERROR: unable to download video data: HTTP Error 403: Forbidden"), False)
check("transient: throttled", is_permanent("ERROR: Sign in to confirm you're not a bot"), False)
check("transient: connection reset", is_permanent("ERROR: The read operation timed out"), False)

if failures:
    print("FAILED %d of %d check(s):" % (len(failures), checked))
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("All %d checks passed." % checked)
