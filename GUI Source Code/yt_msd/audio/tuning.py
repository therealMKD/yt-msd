# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.audio.tuning).
#
# WHY THE FOUR SETTINGS ARE AN OBJECT AND NOT FOUR MODULE GLOBALS
# ---------------------------------------------------------------------------------------
# The loudness numbers below are genuinely fixed. Four of them never were: the silence-pad
# length, whether silence trimming runs, the worker count and the custom loudnorm override
# are settings a user changes, and before this file existed they lived as module globals in
# yt-msd-gui.pyw that eight different places rewrote with `global` - the renamer CLI, four
# SettingsDialog handlers, MainApp.__init__, MainApp.reset_to_defaults and
# _apply_imported_config - while the normalizer read them. That only works while the writer
# and the reader share a module. Moving the normalizer into a package module and leaving the
# writers in the entry point would have given every `global` a copy of the name to update
# and every reader a copy to read: a setting that silently stops doing anything, with no
# error and no failed check. These four are already duplicated a second time as
# self.silence_trim / self.silence_pad_dur / self.use_custom_norm_cmd / self.custom_norm_cmd
# on MainApp, so this object replaces a duplication that was already there instead of adding
# one. Read TUNING.<name>; write TUNING.<name> or TUNING.from_settings(...). Never import
# one of these values into another module, because that binds the value, not the setting.
# ---------------------------------------------------------------------------------------

import os

_available_threads = os.cpu_count() or 4
TARGET_LUFS = "-16"
TRUE_PEAK = "-1.5"
LOUDNESS_RANGE = "11"
BITRATE = "320k"
# Built-in silence trimming values. Used verbatim for both the front pass and the
# reversed back pass - a loudnorm override never changes them.
SILENCE_THRESHOLD = "-60dB"
SILENCE_DURATION = "0.5"
SILENCE_KEEP = "0.5"

# Factory values for the four settings a user can change. They are named DEFAULT_ on purpose:
# the live values are the attributes of TUNING below, and nothing but this file should ever
# see these names.
DEFAULT_MAX_WORKERS = max(1, _available_threads // 2)
DEFAULT_SILENCE_PAD_DUR = 2.0
DEFAULT_SILENCE_TRIM = True  # Trim leading/trailing silence; independent of the loudnorm override
DEFAULT_CUSTOM_NORM_CMD = ""  # Optional override of ONLY the loudnorm part of the ffmpeg -af chain


class Tuning:
    """The four normalization settings the ffmpeg chain is built from, in one place."""

    def __init__(self):
        self.max_workers = DEFAULT_MAX_WORKERS
        self.silence_pad_dur = DEFAULT_SILENCE_PAD_DUR
        self.silence_trim = DEFAULT_SILENCE_TRIM
        self.custom_norm_cmd = DEFAULT_CUSTOM_NORM_CMD

    def reset(self):
        """Back to factory values. Called by MainApp.reset_to_defaults so the renamer this
        window launches cannot keep running with pre-reset values."""
        self.max_workers = DEFAULT_MAX_WORKERS
        self.silence_pad_dur = DEFAULT_SILENCE_PAD_DUR
        self.silence_trim = DEFAULT_SILENCE_TRIM
        self.custom_norm_cmd = DEFAULT_CUSTOM_NORM_CMD

    def from_settings(self, silence_trim, silence_pad_dur, use_custom_norm_cmd, custom_norm_cmd):
        """Take the settings MainApp holds. This is the one place that decides when a custom
        override counts - the entry point used to repeat that decision in three copies."""
        self.silence_trim = bool(silence_trim)
        try:
            self.silence_pad_dur = float(silence_pad_dur)
        except (TypeError, ValueError):
            self.silence_pad_dur = DEFAULT_SILENCE_PAD_DUR
        override = (custom_norm_cmd or "").strip()
        self.custom_norm_cmd = override if (use_custom_norm_cmd and override) else ""


# The one instance the program uses. Every read and every write goes through this object.
TUNING = Tuning()
