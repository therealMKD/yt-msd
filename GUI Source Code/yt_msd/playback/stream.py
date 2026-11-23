# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.playback.stream).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.

# Keeping one track playing. A YouTube stream URL is a signed link with a lifetime rather
# than a file: partway through a long track - or after a track has been paused for an hour -
# it stops answering, and libVLC reports that as nothing useful. The media on the player
# either falls to vlc.State.Error or goes on claiming Playing with a position that has
# stopped moving, and in both cases scrubbing does nothing and Play does nothing, so the only
# way back was to pick the track again. The rule every re-resolution is measured against first
# is the opposite one: a stream that is measurably answering is left alone, which
# _stream_is_playing_now() is the question of (see _stream_needs_renew). STREAM_STALL_SECONDS is
# how long a reported position may stand still while the player claims Playing before the stream
# counts as dead; a dead stream the listener never asked to stop is re-resolved by itself,
# keeping its position, up to STREAM_REFETCH_LIMIT times per track. STREAM_RESUME_GRACE is how
# long a track the listener had stopped gets once it is playing again - a paused stream has to
# reconnect before it reports a moving position, so the first still position after a resume is not
# the evidence a still position is in a track that has been running the whole time. Neither clock
# runs at all while the listener has the track stopped (see _watch_stream_liveness), which is what
# used to reload a paused track for nothing: pause one for longer than STREAM_STALL_SECONDS and the
# first tick after Play convicted it on the position it had left behind before the pause.
# STREAM_URL_MAX_AGE is the backstop: a loaded URL
# that old is re-resolved the moment the user scrubs or presses Play, unless the player is
# measurably advancing on it - a stream that is working is left alone however old its URL is,
# and so is a stream that was only ever loaded and left sitting, which is the track the session
# restore preloads at start up. Age alone reloads a stream that has actually been heard and has
# then gone idle; reloading anything else is a restart rather than a recovery, and the two are
# told apart by _stream_listened.
# STREAM_END_SLACK_MS is how far short of its own reported length a media may "end" before
# that ending is read as a stream that gave up rather than a track that finished.
STREAM_STALL_SECONDS = 8

STREAM_RESUME_GRACE = 20          # seconds a track the listener had stopped gets, once playing again, before a still position counts as a stall

STREAM_URL_MAX_AGE = 30 * 60      # seconds the URL on the player may be before a scrub or Play re-resolves it

STREAM_REFETCH_LIMIT = 3          # self-healing re-resolutions per track before the player says so and waits

STREAM_RENEW_COOLDOWN = 10        # seconds between two re-resolutions of the same track

STREAM_END_SLACK_MS = 15000       # a stream that ended this far short of its length did not finish

STREAM_SEEK_RESTORE_TIMEOUT = 12  # seconds a scrub or a restored position stays queued for fresh media
