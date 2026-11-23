# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ui.render).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.

# The rows of a folder are filled in chunks, and every chunk hands the event loop back a
# chance to lay the new rows out and paint them. The first chunk is deliberately about
# what fits in the pane, because those are the rows the user switched folders to look at:
# a folder of thirty files is filled by that chunk alone, and a folder of a thousand is
# on screen and readable while the rest of it is still arriving.
LOCAL_RENDER_FIRST_CHUNK_ROWS = 32


# How tall a row is assumed to be until the pane has measured its own, which is what
# decides how many rows a screenful is.
LOCAL_RENDER_ROW_HEIGHT_GUESS = 24.0


# After the first chunk the size is worked out from what a row actually costs this machine -
# building it, laying it out and painting it - so that a chunk is as big as it can be and still
# keep the GUI thread away for no more than about a frame. A fast machine fills a thousand files
# in a few larger chunks, a slow one in many smaller ones, and neither stops answering the user.
LOCAL_RENDER_CHUNK_MIN_ROWS = 32

LOCAL_RENDER_CHUNK_MAX_ROWS = 1024

LOCAL_RENDER_CHUNK_BUDGET_S = 0.020
