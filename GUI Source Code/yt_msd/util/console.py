# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.util.console).
import threading


# ============================================================
# INTEGRATED MP3 RENAMER, TAGGER & LOUDNESS NORMALIZER
# (Ported from mp3renamer5000.py — interactive CLI mode & algorithms)
# ============================================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[90m'


_print_lock = threading.Lock()


def _safe_print(msg):
    with _print_lock:
        print(msg)
