# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.util.text).
#
# Extracted from yt-msd-gui.pyw during the 3.5 modularisation. The wording of everything
# moved here is unchanged; only the imports needed to reach the rest of the program were
# added.
import os
import re
from typing import Tuple


def _is_romanized(text):
    return re.search(
        r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\u0400-\u04ff\u0370-\u03ff\u0600-\u06ff]',
        text
    ) is None


def clean_youtube_title(filename):
    title = filename
    title = re.sub(r'[\u2010-\u2015—–‐‑‒―]+', '-', title)
    title = re.sub(r'-+', '-', title)
    title = re.sub(r'[｜│┃ǀ]+', '|', title)
    title = title.replace('：', ':')
    title = title.replace('’', "'").replace('‘', "'").replace('`', "'").replace('´', "'")
    title = title.replace('“', '"').replace('”', '"')

    MASK_HYPHEN = "\x00HYPHEN\x00"
    MASK_PIPE   = "\x00PIPE\x00"
    MASK_COLON  = "\x00COLON\x00"

    def mask_separators_in_brackets(text):
        result, depth, i = [], 0, 0
        while i < len(text):
            ch = text[i]
            if ch in '([{':
                depth += 1; result.append(ch); i += 1
            elif ch in ')]}':
                depth -= 1; result.append(ch); i += 1
            elif depth > 0:
                if text[i:i+3] == ' - ':
                    result.append(MASK_HYPHEN); i += 3
                elif text[i] == '|':
                    result.append(MASK_PIPE); i += 1
                elif text[i] == ':':
                    result.append(MASK_COLON); i += 1
                else:
                    result.append(ch); i += 1
            else:
                result.append(ch); i += 1
        return ''.join(result)

    title = mask_separators_in_brackets(title)
    title = re.sub(r'\s*:\s*', ' - ', title)

    if "|" in title:
        if "-" not in title:
            title = title.replace("|", " - ")
        else:
            title = title.split("|")[0].rstrip()

    title = re.sub(r'\s+-\s+', ' - ', title)

    parts = title.split(" - ")
    if len(parts) > 2:
        title = " - ".join(parts[:2])

    title = title.replace(MASK_HYPHEN, ' - ').replace(MASK_PIPE, '|').replace(MASK_COLON, ':')

    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part, title_part = parts[0].strip(), parts[1].strip()
        if not _is_romanized(title_part):
            m = re.search(r'[\(\[\{]([^\)\}\]]+)[\)\]\}]', title_part)
            if m:
                inside = m.group(1).strip()
                if not _is_romanized(inside):
                    title_part = inside
        title = f"{artist_part} - {title_part}"
    else:
        if not _is_romanized(title):
            m = re.search(r'[\(\[\{]([^\)\}\]]+)[\)\]\}]', title)
            if m:
                inside = m.group(1).strip()
                if not _is_romanized(inside):
                    title = inside

    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = re.split(r'\s*&\s*|\s+[xX]\s+', parts[0].strip())[0].strip()
        title = f"{artist_part} - {parts[1].strip()}"

    def process_brackets(match):
        inside = match.group(2)
        if not _is_romanized(inside):
            return inside
        return ""

    bracket_pair_pattern = r'(\(|\[|\{)([^\(\)\[\]\{\}]*)(\)|\]|\})'
    old_title = ""
    while old_title != title:
        old_title = title
        title = re.sub(bracket_pair_pattern, process_brackets, title)

    title = re.sub(r'[\(\)\{\}\[\]]', '', title)
    title = re.sub(r'\b(hd|version|original|official|4k|uhd|upgraded|upscaled|remastered|lyrics)\b', '', title, flags=re.IGNORECASE)
    # Strip "feat/ft/featuring" credits only from the title side so an artist
    # whose name begins with those letters (e.g. "FT Island") is not destroyed.
    if " - " in title:
        _feat_re = re.compile(r'\s*\b(ft|feat|featuring)\b\.?.*$', re.IGNORECASE)
        _artist_part, _title_part = title.split(" - ", 1)
        title = f"{_artist_part.strip()} - {_feat_re.split(_title_part)[0].strip()}"
    else:
        title = re.compile(r'\s*\b(ft|feat|featuring)\b\.?.*$', re.IGNORECASE).split(title)[0]
    title = re.sub(r'#\S+', '', title)

    # Quote handling:
    # 1. Double quotes are never part of a contraction, so every double-quote character is
    #    removed outright: ASCII " plus the unicode variants - curly U+201C/U+201D, low
    #    double U+201E, reversed-9 high U+201F, guillemets U+00AB/U+00BB and the double
    #    prime U+2033. No pairing and no adjacency rules are applied. This is what stops Bad
    #    Lip Reading style titles (which wrap words in quotes) from leaving floating double
    #    quotes behind in the filename.
    title = re.sub(r'["\u201c\u201d\u201e\u201f\u00ab\u00bb\u2033]', '', title)

    # 2. Mask interior word contractions (e.g. Don't, won't, it's, rock'n'roll)
    MASK = "\x00APOS\x00"
    title = re.sub(r"([a-zA-Z0-9])'([a-zA-Z0-9])", rf"\1{MASK}\2", title)

    # 2b. Quoted-title pattern with no explicit artist separator.
    #     When no " - " was detected anywhere but there is a balanced single-quote pair
    #     (opening quote preceded by whitespace), treat it as "<artist> '<title>' <junk>":
    #     everything before the quotes becomes the artist, the quoted text becomes the title,
    #     the quotes are dropped and everything after the closing quote is stripped.
    #     Common for Kpop uploads, e.g. "A2O Lite 'NEON' Official Video" -> "A2O Lite - NEON".
    if " - " not in title:
        m = re.match(r"^(.*?)\s+'([^']+)'.*$", title)
        if m:
            quoted_artist = m.group(1).strip()
            quoted_title  = m.group(2).strip()
            if quoted_artist and quoted_title:
                title = f"{quoted_artist} - {quoted_title}"

    # 3. Remove balanced single-quote pairs ('x')
    old = None
    while old != title:
        old = title
        title = re.sub(r"'([^']*)'", r'\1', title)

    # 4. Remove any UNATTACHED single quotes (not touching any letters/numbers on either side)
    title = re.sub(r"(?<![a-zA-Z0-9])'(?![a-zA-Z0-9])", "", title)

    # 5. Restore masked interior contractions (e.g. Don't stays as Don't)
    title = title.replace(MASK, "'")

    try:
        title = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27bf]', '', title, flags=re.UNICODE)
    except re.error:
        pass

    title = re.sub(r'\s+', ' ', title).strip()

    if " - " in title:
        parts = title.split(" - ", 1)
        artist_part = parts[0].strip()
        title_part = parts[1].strip()
        if "," in artist_part:
            artist_part = artist_part.split(",")[0].strip()
        title = f"{artist_part} - {title_part}"
    else:
        title = re.sub(r'\s*-\s*$', '', title)
        title = re.sub(r'^\s*-\s*', '', title)
        title = title.strip()

    invalid_chars = r'[\\/:*?<>|]'
    title = re.sub(invalid_chars, '_', title)
    title = re.sub(r'\s+', ' ', title).strip()

    return title



def _title_match_key(text):
    """A loose key for matching a queue title against the file it produced.

    yt-dlp rewrites every character a Windows filename cannot hold, so a title
    with a ':' or a '/' in it never matches the file it was downloaded to.
    Comparing only the letters and digits ignores those rewrites.
    """
    return re.sub(r'[^0-9a-z]+', '', (text or '').lower())



def _title_matches_filename(title, filename):
    """True when 'filename' is the file a download of 'title' would have written."""
    wanted = _title_match_key(title)
    on_disk = _title_match_key(os.path.splitext(os.path.basename(filename))[0])
    if not wanted or not on_disk:
        return False
    if wanted == on_disk:
        return True
    # yt-dlp shortens titles past its own filename limit, so a long enough
    # prefix of the right shape still counts.
    shorter, longer = (wanted, on_disk) if len(wanted) < len(on_disk) else (on_disk, wanted)
    return len(shorter) >= 12 and longer.startswith(shorter)



def _sanitize_filename(name: str) -> str:
    """Strip characters that Windows filenames cannot contain."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    return re.sub(r'\s+', ' ', cleaned).strip(' .')



def _split_artist_title(stem: str) -> Tuple[str, str]:
    """Best-effort 'Artist - Title' split, used to pre-fill the renamer when a
    file has no tags but is already named in that format."""
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


def channel_prefixed_stem(stem: str, channel: str) -> str:
    """The name the renamer would have built for 'stem' had the channel name been
    typed at its "No artist found" prompt, or '' when there is nothing to add.

    The prediction is the renamer's own - clean_youtube_title plus the same ' - '
    split auto mode accepts - so a downloaded track is judged by the rule that
    renames it rather than by a second copy of that rule that can drift from it.
    The channel half is sanitized on its own and the pair is then joined the way
    the prompt joins it: a name the user supplied is used as typed and is never
    run back through the cleaner, which is why a channel carrying a ' - ' of its
    own keeps it here too - the renamer splits such a name at its first ' - ' just
    as it splits the one the user typed.
    """
    prediction = clean_youtube_title(stem)
    artist, title = _split_artist_title(prediction)
    if artist or not title:
        # The name already carries an artist, so this is the renamer's job and not
        # this one's; or nothing survived the cleaner, and there is no title left to
        # build a pair around.
        return ""
    prefix = _sanitize_filename(channel or "")
    if not any(ch.isalnum() for ch in prefix):
        # Covers a row that names no owner at all, and one whose name was nothing but
        # characters a filename cannot hold - neither is a name worth putting on a file.
        return ""
    # A title that already opens with the channel must not be prefixed twice, but the test is
    # made word by word on the cleaned title: 'IVE Looks Can Kill' from channel IVE is already
    # named, while 'Ferry Has A Name' from @ferryhasaname is not - one is the channel followed
    # by a title, the other only looks alike once the spaces are gone.
    cleaned = prediction.strip().lower()
    if cleaned == prefix.strip().lower() or cleaned.startswith(prefix.strip().lower() + " "):
        return ""
    return f"{prefix} - {title}"
