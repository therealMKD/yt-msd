# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.constants).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.

# Internal version number - the numeric part of the latest GitHub release tag.
# (RELEASE-3.4 is tagged as "RELEASE-3.4" and read here as "3.4":
# _extract_version_number() reduces both sides to their numbers before comparing
# them, so a tag is still recognised as this version or as a newer one. The same
# numbers are what build_gui_exe.py puts in the installer and in the version
# resource of the exe, so the app, the setup program and the file's own
# Properties dialog all report one version.)
APP_VERSION = "3.4"


# GitHub repository whose releases page is polled for newer versions.
UPDATE_REPO = "therealMKD/yt-msd"


# Which file of a release this copy of yt-msd downloads depends on how it is being
# run: the packaged exe is updated with its setup program, a copy started from the
# source is updated with the new source file written over the one being run.
INSTALLER_ASSET = "yt-msd-setup.exe"   # what the packaged exe looks for on a release

SOURCE_ASSET = "yt-msd-gui.pyw"        # what a copy started from the source looks for


# How a downloaded update gets applied, reported to UpdateReadyDialog and used by
# _launch_swap_helper:
UPDATE_MODE_INSTALLER = "installer"  # run the downloaded setup program; this file is left alone

UPDATE_MODE_REPLACE = "replace"      # the download was written over the file being run

UPDATE_MODE_SWAP = "swap"            # keep both files, delete this one, launch the new one


# The captions the play button carries, and the one place they are set (_update_play_button).
# Play and Pause are the codes that button has always used; Replay is the state the button
# takes when the media on the player has run to its end and nothing was started after it - a
# media libVLC can no longer seek, scrub or resume, so the only thing a press can mean is
# "this track again, from the top". U+E72C rather than the published MDL2 chart's own "Replay"
# (U+E76A) for the same reason the stop-after button avoids a private-use codepoint (see the
# comment where that button is built): U+E76A has no glyph in this machine's copy of the font
# and Qt would draw an empty box. U+E72C was drawn at the size the button uses and looked at
# to confirm it reads as "start this again".
PLAY_GLYPH = "\uE768"

PAUSE_GLYPH = "\uE769"

REPLAY_GLYPH = "\uE72C"


# "Stop after current", cycled one state per click: off -> once -> always -> off.
STOP_AFTER_OFF = 0     # playback advances to the next track when one ends, as it always did

STOP_AFTER_ONCE = 1    # stop when the current track ends, then the state returns to off

STOP_AFTER_ALWAYS = 2  # stop after every track until the button is clicked again

STOP_AFTER_STATE_NAMES = {STOP_AFTER_OFF: "off", STOP_AFTER_ONCE: "once", STOP_AFTER_ALWAYS: "always"}

STOP_AFTER_LABELS = {STOP_AFTER_OFF: "Off", STOP_AFTER_ONCE: "Once", STOP_AFTER_ALWAYS: "Always"}

STOP_AFTER_TOOLTIPS = {
    STOP_AFTER_OFF: "Stop After Current: Off - playback advances to the next track.\n"
                    "Click once: stop after this track.",
    STOP_AFTER_ONCE: "Stop After Current: Once - this track is the last one, then the button returns to Off.\n"
                     "Click again: keep stopping after every track.",
    STOP_AFTER_ALWAYS: "Stop After Current: Always - every track stops when it ends.\n"
                       "Click once: turn it off.",
}


# The formats the Format dropdown offers, and therefore the formats a download can
# be saved as. The rule for this list is strict: a format is only allowed if the
# tagger can write artist/title into it and read them back, because the player gets
# everything it displays out of those two tags. Three formats used to be on this
# list and are off it on purpose, each verified against mutagen:
#   .aac  - a raw ADTS bitstream with no tag container of any kind.
#   .wav  - RIFF/PCM. mutagen opens it but gives it no tag API at all, so the
#           tagger has nowhere to put an artist or a title.
#   .flac - taggable, but only through Vorbis comments, which is a different tag
#           system from the ID3/MP4 path this tagger uses.
# All three are still in AUDIO_EXTENSIONS below, so a file someone already downloaded
# in one of them stays visible and playable - it can just no longer be produced. The
# two that are left are the two the whole pipeline actually supports: MP3 (ID3v2) and
# M4A (MP4 atoms). M4A is the same AAC codec, so no codec was ever lost, only the
# containers that could not carry a tag.
DOWNLOAD_FORMATS = ("mp3", "m4a")

DEFAULT_DOWNLOAD_FORMAT = "mp3"


# The same list as file suffixes, for the passes that walk a folder. Derived from
# DOWNLOAD_FORMATS so that a format cannot be offered in the dropdown without also
# being handled by the rename/tag/normalize/silence-trim passes, which is how aac,
# flac and wav ended up downloadable-but-never-taggable in the first place.
TAGGABLE_EXTENSIONS = {f".{fmt}" for fmt in DOWNLOAD_FORMATS}


# Audio extensions the local file browser and the sync scan accept. This is wider
# than DOWNLOAD_FORMATS on purpose: it also covers files that are already sitting in
# someone's library, including .aac files downloaded by older versions of the app,
# which should stay visible and playable even though they can no longer be produced.
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.ogg', '.opus', '.aac', '.wma', '.mka', '.aiff', '.alac', '.ape', '.wv'}


# The containers mutagen can read artist/title out of, measured against mutagen 1.48.1.
# Everything else on AUDIO_EXTENSIONS is outside this set for a reason: .aac is a raw
# ADTS bitstream with no tag container, .wav and .aiff open fine but mutagen gives them
# no tag API, and .mka and .ape are formats mutagen will not open at all. Those keep
# going to ffprobe for their tags, exactly as they did before.
MUTAGEN_TAGGABLE_EXTENSIONS = {'.mp3', '.m4a', '.alac', '.flac', '.ogg', '.opus', '.wma', '.wv'}
