# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.util.timefmt).

# The pane is handed the height the finished folder is going to occupy as soon as its listing is
# known, and it keeps that height until the fill is done. A row that has already been drawn is
# therefore never moved while the rest of the folder is being built: the folder appears at the
# size it is going to be, its scrollbar is right from the first frame, and every chunk after the
# first lands in room that is already reserved instead of stretching the list under the user and
# forcing everything already on screen to be laid out and painted over again. Chunked filling
# without it is what makes a big folder look like it is inflating rather than arriving.


def _format_audio_duration(seconds):
    """The duration text a local row shows: H:MM:SS at an hour or more, M:SS under it."""
    try:
        d = float(seconds)
    except (TypeError, ValueError):
        return ""
    if d <= 0:
        return ""
    if d >= 3600:
        return f"{int(d // 3600)}:{int((d % 3600) // 60):02d}:{int(d % 60):02d}"
    return f"{int(d // 60)}:{int(d % 60):02d}"
