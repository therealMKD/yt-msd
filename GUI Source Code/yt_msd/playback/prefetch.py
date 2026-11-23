# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.playback.prefetch).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.

# Playback reads ahead of the player. A stream URL takes a second or two to resolve
# with yt-dlp, and that time used to land between two tracks - the player sat on an
# empty media while the successor's URL was fetched, which looked like a skip or a
# laggy start. So the successor is resolved while the current track still has this
# many seconds left, on its own thread, and the resolved URL is held ready.
# PREFETCH_URL_MAX_AGE is the guard: a YouTube stream URL that has been sitting
# longer than that has expired and is resolved again.
PREFETCH_SECONDS_BEFORE_END = 30

PREFETCH_URL_MAX_AGE = 15 * 60  # seconds a prefetched stream URL is still trusted

PREFETCH_CACHE_LIMIT = 4        # resolved stream URLs held at most
