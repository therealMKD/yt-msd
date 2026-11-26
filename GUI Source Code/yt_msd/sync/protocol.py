# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.sync.protocol).
"""The words both ends of a sync chain speak, and the version of them this machine speaks.

`docs/sync-protocol.md` is the specification - the frames, the order they are allowed in, the timeouts
and the sizes. This module is the same facts in code: every command name and every status a host answers
with, the discovery frame types, and the version rules. It exists because a second kind of machine is
about to speak this protocol - a phone - and a phone cannot read a Python module's control flow, only a
list of names it has to agree with.

It is deliberately small and it is deliberately Qt-free. `yt_msd.sync.host` and `yt_msd.sync.client` are
the two ends as this program runs them today; `yt_msd.sync.wire` is this list put to work as a client
that needs nothing but the standard library. A new endpoint is written against those two, and the
`PW` checks in `GUI Test Suite/probe_phone_wire.py` are what keeps the three of them agreeing.

Nothing here is read off a wire, and nothing here decides what a chain does: it names things and answers
questions about versions. The behaviour stays where it has always been.
"""
from typing import Any, Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# The version
#
# One number, said at the door. Every build since 3.0 has spoken exactly one dialect of this protocol
# and has named none, so a client that names no version is a 3.0-and-later client, and a host that
# names no version in its answer is a 3.0-and-later host. That is the whole of the backwards
# compatibility rule, and it is deliberately the only one: a protocol that has to be negotiated
# per-command is a protocol nobody tests.
#
# The number goes up when a machine that speaks the older words would be WRONG about a newer answer -
# a frame meaning something new under an old name, or a new frame in the middle of an exchange an old
# client expects to end. Adding a command nobody asks for is not that, and does not move this number.
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = 1

# The versions this machine answers. A tuple and not a range, because the honest answer is a list of
# the dialects somebody wrote, and a machine that agreed to answer "anything from 1 upward" would be
# promising to answer versions that do not exist yet.
SUPPORTED_PROTOCOL_VERSIONS: Tuple[int, ...] = (1,)

# The key a version is carried under, on the request and on the answer.
PROTOCOL_VERSION_KEY = "protocol_version"


# ---------------------------------------------------------------------------
# Commands a client sends
# ---------------------------------------------------------------------------

CMD_HELLO = "HELLO"                        # "are you a yt-msd, and what do you host?" - no chain, no code
CMD_AUTH = "AUTH"                          # "this is the chain I belong to" - the door every real exchange goes through
CMD_GET_INDEX = "GET_INDEX"                # "give me your file list"
CMD_PULL_FILE = "PULL_FILE"                # "send me that file"
CMD_PING = "PING"                          # "keep this connection warm while I ask somebody a question"
CMD_GET_CONFIG = "GET_CONFIG"              # "send me your settings file"
CMD_RESTORE_REQUEST = "RESTORE_REQUEST"    # "put a code on your screen; I have the copy you lost"
CMD_RESTORE_CONFIRM = "RESTORE_CONFIRM"    # "the code on your screen is this one"
CMD_RESTORE_CANCEL = "RESTORE_CANCEL"      # "never mind - take the code off your screen"
CMD_PUSH_REQUEST = "PUSH_REQUEST"          # "I made files here that you do not have"
CMD_PUSH_START = "PUSH_START"              # "I read your push code out" - or "this address was let through already"
CMD_PUSH_CANCEL = "PUSH_CANCEL"            # "take the push code off your screen"
CMD_PUSH_INDEX = "PUSH_INDEX"              # "here is my list; tell me which ones you want"
CMD_PUSH_FILE = "PUSH_FILE"                # "the next bytes on this socket are this file"
CMD_PUSH_DONE = "PUSH_DONE"                # "that is the last of them"

CLIENT_COMMANDS = frozenset({
    CMD_HELLO, CMD_AUTH, CMD_GET_INDEX, CMD_PULL_FILE, CMD_PING, CMD_GET_CONFIG,
    CMD_RESTORE_REQUEST, CMD_RESTORE_CONFIRM, CMD_RESTORE_CANCEL,
    CMD_PUSH_REQUEST, CMD_PUSH_START, CMD_PUSH_CANCEL, CMD_PUSH_INDEX, CMD_PUSH_FILE, CMD_PUSH_DONE,
})


# ---------------------------------------------------------------------------
# Statuses a host answers with
#
# The answers are read by name at both ends and in the windows above them, so they are named here as
# well: a phone that has to type "SENDING" out of a document is a phone that will type it wrong, and a
# PC that changes a word in one place is a PC that breaks a machine it cannot see.
# ---------------------------------------------------------------------------

STATUS_OK = "OK"
STATUS_ERROR = "ERROR"
STATUS_SENDING = "SENDING"                 # PULL_FILE: the bytes follow this answer on the same socket
STATUS_PONG = "PONG"
STATUS_CONFIG = "CONFIG"
STATUS_CANCELLED = "CANCELLED"
STATUS_WAITING_FOR_CODE = "WAITING_FOR_CODE"
STATUS_CODE_ACCEPTED = "CODE_ACCEPTED"
STATUS_RESTORING = "RESTORING"
STATUS_RECEIVING = "RECEIVING"             # PUSH_FILE: send the bytes now
STATUS_SYNCED = "SYNCED"
STATUS_WAITING_FOR_PUSH_CODE = "WAITING_FOR_PUSH_CODE"
STATUS_PUSH_ALLOWED = "PUSH_ALLOWED"       # a trusted address gets to push with no code at all
STATUS_PUSH_ACCEPTED = "PUSH_ACCEPTED"
STATUS_PUSHING = "PUSHING"
STATUS_RESTORE_CLOSED = "RESTORE_CLOSED"   # the offer a PING was waiting on has gone away
STATUS_PUSH_CLOSED = "PUSH_CLOSED"

HOST_STATUSES = frozenset({
    STATUS_OK, STATUS_ERROR, STATUS_SENDING, STATUS_PONG, STATUS_CONFIG, STATUS_CANCELLED,
    STATUS_WAITING_FOR_CODE, STATUS_CODE_ACCEPTED, STATUS_RESTORING, STATUS_RECEIVING,
    STATUS_SYNCED, STATUS_WAITING_FOR_PUSH_CODE, STATUS_PUSH_ALLOWED, STATUS_PUSH_ACCEPTED,
    STATUS_PUSHING, STATUS_RESTORE_CLOSED, STATUS_PUSH_CLOSED,
})


# ---------------------------------------------------------------------------
# The discovery frames, which are UDP and carry a "type" and not a "cmd"
# ---------------------------------------------------------------------------

TYPE_BEACON = "BEACON"                      # a host announcing the chains it is willing to name
TYPE_PROBE = "PROBE"                        # "who hosts this code?"
TYPE_PROBE_ALL = "PROBE_ALL"                # "who hosts anything, and what is it?"
TYPE_PROBE_REPLY = "PROBE_REPLY"
TYPE_CHAIN_UPDATED = "CHAIN_UPDATED"        # "the folder you follow has changed"
TYPE_CHAIN_SYNC_REQUEST = "CHAIN_SYNC_REQUEST"  # "a host you follow is up; run your normal sync"

DISCOVERY_TYPES = frozenset({
    TYPE_BEACON, TYPE_PROBE, TYPE_PROBE_ALL, TYPE_PROBE_REPLY, TYPE_CHAIN_UPDATED,
    TYPE_CHAIN_SYNC_REQUEST,
})


# ---------------------------------------------------------------------------
# Shapes both ends rely on
# ---------------------------------------------------------------------------

# What one row of a file index looks like. `artist` and `title` travel on the index a host sends, and on
# the index a restoring client sends, because a rebuild is a whole library and a library that arrives with
# its tags is a library that need not be opened again to be named. A push measures files the host has
# never seen and offers the four facts a file is checked against, and nothing else.
INDEX_ENTRY_KEYS = ("name", "size", "mtime", "sha256", "artist", "title")
PUSH_INDEX_ENTRY_KEYS = ("name", "size", "mtime", "sha256")

# The checksum both ends promise each other, as it appears in a frame: 64 hex characters. A host that is
# told a file is coming and is handed fewer characters than that has nothing to check it against, and
# says so instead of reading bytes it cannot verify.
SHA256_HEX_LENGTH = 64

# A sync code is four digits, chosen for being readable off a screen, and travels as text and not as a
# number - `Sync code 8888 not found on host` names it as text at both ends.
SYNC_CODE_LENGTH = 4

# The app's own name, as a host introduces itself to a stranger. A scan of a network finds this word or
# nothing at all: it is the one thing that lets a search tell a sync host from a machine that merely has
# a port open.
APP_NAME = "yt-msd"


def requested_protocol_version(message: Optional[Dict[str, Any]]) -> int:
    """The protocol version the machine on the other end says it speaks.

    Read the way every other number a chain carries is read - with a fallback, because a frame from a
    machine this program has never talked to is a frame that can hold anything. A missing key, a boolean,
    text that is not a number and a number that is not a version all answer `PROTOCOL_VERSION`, which is
    what every build since 3.0 speaks: a client that names no version is not announcing that it speaks no
    protocol, it is announcing that it is old, and old is the case this has to keep working.
    """
    raw = (message or {}).get(PROTOCOL_VERSION_KEY)
    if raw is None or isinstance(raw, bool):
        return PROTOCOL_VERSION
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return PROTOCOL_VERSION
    return value if value > 0 else PROTOCOL_VERSION


def protocol_version_accepted(requested) -> bool:
    """Will this machine answer a client that asked for `requested`?"""
    try:
        return int(requested) in SUPPORTED_PROTOCOL_VERSIONS
    except (TypeError, ValueError):
        return False


def version_refusal(requested) -> str:
    """What to tell a machine this program will not speak with.

    Two sentences, because the two cases end differently. A machine asking for a newer protocol than this
    one has is running a newer yt-msd, and the fix is an update on this machine; a machine asking for an
    older one is running an older yt-msd than this one, and the fix is an update on that one. Saying which
    case it is saves the person standing between two screens from guessing.
    """
    try:
        wanted = int(requested)
    except (TypeError, ValueError):
        wanted = PROTOCOL_VERSION
    if wanted > PROTOCOL_VERSION:
        return (f"This host speaks sync protocol version {PROTOCOL_VERSION}; it cannot answer version "
                f"{wanted}. Update yt-msd on this machine.")
    return (f"This host speaks sync protocol version {PROTOCOL_VERSION}; it no longer answers version "
            f"{wanted}. Update yt-msd on the machine that asked.")


def version_answer(message: Optional[Dict[str, Any]]) -> Optional[str]:
    """Nothing at all if this machine should answer, or the sentence telling it not to.

    The one question a host asks at its door: read the version out of the frame, and answer with a
    refusal only when there is one to give.
    """
    requested = requested_protocol_version(message)
    if protocol_version_accepted(requested):
        return None
    return version_refusal(requested)


def with_protocol_version(message: Dict[str, Any]) -> Dict[str, Any]:
    """This frame, with this machine's protocol version named on it.

    Copies rather than writing into the caller's dict, because these frames are built by the code above:
    a sync that added a key to the dict it was handed would be a sync that changed its caller's copy of a
    chain for the exchange after this one.
    """
    framed = dict(message)
    framed[PROTOCOL_VERSION_KEY] = PROTOCOL_VERSION
    return framed


def answered_protocol_version(message: Optional[Dict[str, Any]]) -> Optional[int]:
    """The version a host named in its answer, or nothing at all if it named none.

    Deliberately not the same read as `requested_protocol_version`: on an answer, "no version named" is
    information - it says the host is a 3.0-to-3.5 build - and a machine that read it as version 1 would
    be reading the absence of a fact as the fact itself.
    """
    raw = (message or {}).get(PROTOCOL_VERSION_KEY)
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None




