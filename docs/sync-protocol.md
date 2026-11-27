# AI generated document
# yt-msd sync protocol, version 1

The wire language of a sync chain: the frames, the order they are allowed in, the timeouts, the sizes, and
the words both ends say. It is written for somebody building an endpoint that is not this program - a phone
first - and it is the specification the code is checked against, not a description written after the code
and never read by it.

Where the code is:

| File | What it is |
| --- | --- |
| `GUI Source Code/yt_msd/sync/host.py` | the host: the server, every answer, the codes, the writing rules |
| `GUI Source Code/yt_msd/sync/client.py` | the desktop client: the same frames, with the GUI's decisions around them |
| `GUI Source Code/yt_msd/sync/wire.py` | a client written from this document: no Qt, no window, nothing a phone cannot have |
| `GUI Source Code/yt_msd/sync/protocol.py` | every command name, every status, every discovery type, and the version rules |
| `GUI Source Code/yt_msd/sync/lan.py` | the ports, timeouts, sizes and the code alphabet |
| `GUI Source Code/yt_msd/sync/transfer.py` | the framing, the file streaming, the hashing |
| `GUI Source Code/GUI Test Suite/probe_phone_wire.py` | the checks: a whole phone session against a real host |
| `GUI Source Code/GUI Test Suite/fixtures/protocol/phone_session.json` | the recorded session a new endpoint is compared with |

## 1. The version

`PROTOCOL_VERSION = 1`. It is named once, on the `AUTH` frame, and echoed by the host in its answer.

  - A client that names no version speaks version 1. Every build from 3.0 to 3.5 speaks version 1 and names
    nothing, because the number did not exist yet. A host answers them exactly as it always has.
  - A host that names no version in its answer is a version-1 host.
  - A machine asked to speak a version its host does not have is refused at the door, before it is told
    anything about a chain, and told which versions the two machines have.
  - The version is one number and there is no negotiation. A protocol negotiated per-command is a protocol
    nobody tests.

The number goes up when a machine speaking the older words would be *wrong* about a newer answer: a frame
that means something new under an old name, or a new frame inside an exchange an older client expects to
end. Adding a command that nobody asks for is not that, and does not move it.

## 2. Framing

Every message is one JSON object, UTF-8, sent as:

```
4 bytes  - the length of the JSON, big-endian unsigned 32-bit (struct '!I')
N bytes  - the JSON itself
```

Nothing is newline-delimited and nothing is chunked: both ends read exactly `length` bytes and parse one
object, and a short read is a dead connection.

File bytes are **not** framed. A transfer is announced by a message and the raw bytes then follow on the
same socket, in 1 MiB blocks, for exactly the announced size.

Both ends use TCP. A host listens on the first free port in **63350..63370** and reports that port in its
answers. UDP is used for discovery only, on **63350**.

## 3. Timeouts and sizes

| Name | Value | What it is |
| --- | --- | --- |
| `SYNC_PORT_START` / `SYNC_PORT_END` | 63350 / 63370 | the TCP range a host binds, lowest free first |
| `UDP_BEACON_PORT` | 63350 | discovery traffic |
| `SYNC_SOCKET_TIMEOUT` | 12.0 s | an ordinary read at the door |
| host's command read | 30.0 s | how long a host waits for the next command - a client that stops to ask a person something must ping inside this |
| `SYNC_CONFIRM_PING_INTERVAL` | 10.0 s | how often a client pings while it has stopped to ask |
| index read | 25.0 s | a client's read of `GET_INDEX`: the host is hashing a folder, not dead |
| `SYNC_RESTORE_HANDSHAKE_TIMEOUT` | 300.0 s | a rebuild's reads - both ends are hashing a library |
| `SYNC_RESTORE_CODE_TIMEOUT` | 180.0 s | how long a code stays good |
| `RESTORE_CODE_LENGTH` and alphabet | 4, `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` | codes are read off a screen, so no I, O, 0 or 1 |
| `MAX_CONFIG_PAYLOAD_BYTES` | 2,000,000 | the largest settings file a host will put on the wire |
| `SYNC_CHUNK_SIZE` | 1,048,576 | file blocks |
| `SCAN_CONNECT_TIMEOUT` / `SCAN_READ_TIMEOUT` | 0.35 s / 1.5 s | one handshake of a LAN search |
| `SCAN_MAX_CONCURRENCY` / `SCAN_BUDGET_SECONDS` | 128 / 14.0 s | one search pass |
| `SCAN_MAX_NETWORKS` / `SCAN_MAX_TARGETS` | 4 / 1024 | how wide a search may be |
| `DEFAULT_PUSH_FILE_LIMIT` | 5 | files a hosted chain takes per push, newest first |
| `SHA256_HEX_LENGTH` | 64 | a checksum as text |
| `SYNC_CODE_LENGTH` | 4 digits | a chain's code, as text, e.g. `"7301"` |

A sync code is a **string** on the wire. A number that has lost its leading zero is a different chain.

## 4. Discovery

Discovery is the only traffic a host answers without authentication, and it says as little as it can.

**UDP, on 63350.** A host broadcasts every 4 seconds:

```json
{"type": "BEACON",
 "sync_codes": ["7301"],
 "chains": [{"sync_code": "7301", "name": "Kitchen", "visible": true}],
 "tcp_port": 63350,
 "host_ip": "192.168.1.20"}
```

A client may send, to the same port:

```json
{"type": "PROBE", "sync_code": "7301"}
{"type": "PROBE_ALL"}
{"type": "CHAIN_UPDATED", "sync_code": "7301"}
{"type": "CHAIN_SYNC_REQUEST", "sync_codes": ["7301", "7302"]}
```

`CHAIN_UPDATED` means "the folder behind this code has changed". `CHAIN_SYNC_REQUEST` is what a host
broadcasts about 20 seconds after it comes up (`HOST_UP_SYNC_REQUEST_DELAY_MS`): "I am listening now, the
clients of these chains should run their normal sync". A machine that follows none of the named codes
ignores it.

**Directed broadcasts are dropped by most access points, so discovery must not rely on the beacon.** The
path that works on real networks is TCP, and it is what the desktop search does:

**TCP `HELLO`.** A search connects to each address of its own /24s on each port of the range, **in port
order** - 63350 across the whole network first, then 63351, and so on, because almost every host is on the
first free port and asking that one first is what puts an answer on a screen in the first second:

```json
{"cmd": "HELLO"}
{"cmd": "HELLO", "sync_code": "7302"}
```

A host answers once and closes:

```json
{"status": "OK", "app": "yt-msd", "host_name": "DESKTOP-7Q1", "port": 63350, "protocol_version": 1,
 "chains": [{"sync_code": "7301", "name": "Kitchen", "visible": true}]}
```

  - A **visible** chain is named freely, code and name. A **private** chain is named to no untargeted
    search: it answers only a search that already put its code on the request - the code that machine would
    need to sync it anyway.
  - The hosted folder's path is **never** in a discovery answer. A search is a stranger.
  - An address with no yt-msd behind it answers nothing. A refused port, a port that says nothing, and a
    port that answers something that is not JSON are all the same thing: no answer.
  - A `HELLO` carries no protocol-version requirement. A scan is a stranger introducing itself, not a
    client asking for something.

A phone needs a **manual fallback** for what discovery cannot solve: an address and a code typed in by hand.
Android does not grant multicast to ordinary apps on most access points, so a phone's discovery is a TCP
scan plus a keypad, and it should remember the address a host last answered from - a host that changed
address is found again by its code.

## 5. A session

One connection is one exchange. It opens with `AUTH` and it ends when the socket closes.

### `AUTH` - the door

```json
{"cmd": "AUTH", "sync_code": "7301", "client_ip": "192.168.1.77", "protocol_version": 1}
{"status": "OK", "chain_name": "Kitchen", "files_count": 412, "protocol_version": 1}
```

`client_ip` is what the client calls itself, for the host's activity log and its card. It is **not** what the
host trusts: the address a push is trusted from is the peer address of the socket, never the address a client
chooses to name in a message. `chain_name` is what the host calls this chain, and a client that joined by
code alone has no way of learning it except from this answer.

Anything that is not `AUTH`, sent first, is refused: `{"status": "ERROR", "reason": "Expected AUTH command"}`.
A host that refuses answers **once** and closes; a client must read one answer and stop.

### `GET_INDEX` - what the host holds

```json
{"cmd": "GET_INDEX"}
{"status": "OK", "files": [{"name": "one.mp3", "size": 7341123, "mtime": 1700000000.0,
                            "sha256": "…64 hex…", "artist": "Bach", "title": "Partita 2"}]}
```

Answering this means hashing the whole hosted folder, so read it with 25 seconds and not 12. While a host is
being rebuilt from another machine it refuses this - `This host is being rebuilt from another PC; try again
in a moment` - because a list of a folder half-written is a list of a folder that does not exist, and a
Mirror chain that compares against it deletes real files.

The rule every client has always judged a file by: re-fetch when it is missing, or its size differs, or the
host's copy is newer and the hashes differ. A hash match is a match.

### `PULL_FILE` - take one file

```json
{"cmd": "PULL_FILE", "filename": "one.mp3"}
{"status": "SENDING", "filename": "one.mp3", "filesize": 7341123, "sha256": "…64 hex…"}
<7341123 raw bytes, on the same socket, immediately after that message>
```

The size and checksum in **the answer**, not in the index, are what the transfer is judged by: the host read
its disk after it listed it. The receiver writes to `<name>.tmp_sync`, hashes while writing, compares against
the promised `sha256`, and only then renames. A half file left at the final name is a library that lies, so a
failed transfer leaves the previous copy untouched.

A host will not send a file that is not an audio file: `File not found or not an audio file`.

### `GET_CONFIG` - the host's settings

```json
{"cmd": "GET_CONFIG", "sync_code": "7301", "client_ip": "192.168.1.77"}
{"status": "CONFIG", "config": { …the host's whole settings object… }}
```

It moves no audio. It is refused before it is answered by anything the client was not allowed to authenticate
for. The payload is a message and not a stream, because it has to arrive whole before either end can read it,
and a host refuses one over 2,000,000 bytes.

Which of the settings that arrive describe the machine that received them is decided by the receiver alone.
The host sends what it has and says nothing about where it should land.

### `PING` - keep the connection warm

```json
{"cmd": "PING"}
{"status": "PONG"}
```

A client that has stopped to ask a person something - a phone waiting for a code to be read out - pings every
10 seconds, inside the host's 30-second command read. Two answers are not `PONG` and they mean the offer this
client was waiting on no longer exists: `RESTORE_CLOSED`, `PUSH_CLOSED`. A client that ignores them sits on a
dead exchange and reports a wire failure that is not one.

Nothing else may be sent while a keepalive is running: a `PING` in the middle of a file transfer is bytes the
host reads as its next frame.

## 6. Rebuilding a host (`RESTORE_*`)

This is the exchange where a host agrees that the machine on the other end has the better copy of
everything, and writes it. It is the only place in the protocol where a host writes into its own folder, so
it is the narrowest thing on the wire - and it is the exchange a phone is worst at, because what authorises
it never travels on the wire.

```json
{"cmd": "RESTORE_REQUEST", "sync_code": "7301", "client_ip": "192.168.1.77"}
{"status": "WAITING_FOR_CODE", "chain_name": "Kitchen", "expires_in": 180}
```

**The code is never sent on the socket.** It appears on the host's own screen and nowhere else, and the only
way a client learns it is a person reading it out. `expires_in` is how long the offer lives
(`SYNC_RESTORE_CODE_TIMEOUT`, 180 s). A client starts its keepalive here and stops it before it sends the
code.

```json
{"cmd": "RESTORE_CONFIRM", "sync_code": "7301", "code": "K7P2"}
{"status": "CODE_ACCEPTED", "chain_name": "Kitchen"}
```

A wrong code is an answer and not a hint: it closes the offer (`That is not the code on the host screen`) and
the client keeps its own copy of everything. `{"cmd": "RESTORE_CANCEL", "sync_code": "7301"}` closes the offer
from the client side and is answered `{"status": "CANCELLED"}`.

Then the rebuild itself, on the same connection, with 300-second reads because both ends are hashing
libraries:

```json
{"cmd": "PUSH_INDEX", "sync_code": "7301", "files": [{"name": "one.mp3", "size": 7341123,
                                                      "mtime": 1700000000.0, "sha256": "…64 hex…",
                                                      "artist": "Bach", "title": "Partita 2"}]}
{"status": "RESTORING", "files": ["one.mp3", "two.mp3"], "already_there": 391}
{"cmd": "PUSH_FILE", "filename": "one.mp3", "filesize": 7341123, "sha256": "…64 hex…", "mtime": 1700000000.0}
{"status": "RECEIVING", "filename": "one.mp3"}
<7341123 raw bytes, on the same socket>
{"status": "OK", "filename": "one.mp3"}
{"cmd": "PUSH_DONE", "sync_code": "7301"}
{"status": "SYNCED", "received": 2, "missing": []}
```

  - The host answers with **the part of the client's list it still needs**. Only files on that list are
    accepted, and a file that arrives that is not on it is refused: `This host did not ask for that file`.
  - Names are read as names and not as paths - nothing with a separator in it, nothing that climbs out of
    the folder, nothing whose suffix is not an audio type (`.mp3 .flac .wav .m4a .ogg .opus .aac .wma .mka
    .aiff .alac .ape .wv`): `Not a name this folder can hold`.
  - A file that arrives half-written, or that hashes to something other than the promise, is refused:
    `That file did not arrive whole`.
  - `mtime` is the date the track was **made**, and the host restores it. A copy that looks newer than every
    other copy is the thing that makes a chain decide it has to be re-fetched, and a rebuild is not a reason
    for that.
  - **Nothing is deleted by a restore.** Not on the host, and the client deletes nothing on the word of the
    host - it is the client's own machine, with its own buttons, that ever removes a file.
  - A rebuild ends its connection when it is finished: a host is not a host until its folder is whole again.

## 7. Pushing files (`PUSH_*`)

The one thing a client can do to somebody else's library, so the host decides every part of it: whether this
address needs a code, how many files it may bring, and which of them it will take. Only a Mirror chain is
allowed to push - an Additive chain keeps what it holds, so it has nothing to lose and no reason to ask.

```json
{"cmd": "PUSH_REQUEST", "sync_code": "7301", "client_ip": "192.168.1.77"}
{"status": "PUSH_ALLOWED", "code_required": false, "chain_name": "Kitchen", "limit": 5}
{"status": "WAITING_FOR_PUSH_CODE", "chain_name": "Kitchen", "limit": 5, "expires_in": 180}
```

`PUSH_ALLOWED` means the **peer address of this socket** has already been given leave on the host's own
screen, so no code is needed. The rest of the answers are refusals, and one of them is worth reading before
measuring anything: `This chain does not accept pushed files` is a chain with its limit at 0.

```json
{"cmd": "PUSH_START", "sync_code": "7301", "code": "T9Q4"}
{"status": "PUSH_ACCEPTED", "code_required": true, "chain_name": "Kitchen", "limit": 5}
{"cmd": "PUSH_INDEX", "sync_code": "7301", "files": [{"name": "new song.mp3", "size": 5123456,
                                                      "mtime": 1760000000.0, "sha256": "…64 hex…"}]}
{"status": "PUSHING", "files": ["new song.mp3"], "refused": 2, "already_there": 1, "limit": 5}
<the same PUSH_FILE / RECEIVING / bytes / OK exchange as a rebuild>
{"cmd": "PUSH_DONE", "sync_code": "7301"}
{"status": "SYNCED", "received": 1, "refused": 2, "already_there": 1, "missing": []}
```

  - Only the files this push is about are measured. A client that hashed 400 files to be offered five is a
    client doing work nobody asked it for.
  - `files` in the answer is what this host will take: newest first, up to the limit.
  - A name the host already holds **stays the host's**, however different the two copies are - it is counted
    in `refused` and left exactly where it is. A file that is genuinely identical is not a push and is
    counted in `already_there`.
  - A push does **not** close the connection. The client that pushed has just changed what this folder holds
    and will want its index again, so the host answers a push and carries on serving.
  - `{"cmd": "PUSH_CANCEL", "sync_code": "7301"}` closes an offer the client will not be using.

## 8. The refusals, in the words the host uses them

A phone must read these as the answers they are. Every one of them is a sentence a person can be shown.

| Where | `reason` |
| --- | --- |
| first frame was not `AUTH` | `Expected AUTH command` |
| code this host does not have | `Sync code 9999 not found on host` |
| protocol this host does not speak | `This host speaks sync protocol version 1; it cannot answer version 99. Update yt-msd on this machine.` |
| hosted folder is gone | `Hosted folder path does not exist on disk` |
| index asked during a rebuild | `This host is being rebuilt from another PC; try again in a moment` |
| file that is not audio | `File not found or not an audio file` |
| command the host does not know | `Unknown command: WAT` |
| offer gone (the answer to a PING) | `That restore offer is no longer open on the host` / `That push offer is no longer open on the host` |
| code typed wrong | `That is not the code on the host screen` |
| confirm with no offer open | `No restore offer is open on this connection` / `No push offer is open on this connection` |
| a second offer on one connection | `This connection already has a restore offer open` / `This connection already has a push offer open` |
| rebuild already running | `This host is already being rebuilt from another PC` |
| another client pushing | `Another client is already pushing into this chain` |
| chain takes no pushes | `This chain does not accept pushed files` |
| name the folder cannot hold | `Not a name this folder can hold` |
| file not on the host's own list | `This host did not ask for that file` / `This host did not agree to take that file` |
| no size, no checksum | `No size given for that file` / `No checksum to check that file against` |
| bytes did not hash | `That file did not arrive whole` |
| index never arrived | `The restore index never arrived` / `The push index never arrived` |
| settings: nothing stored | `This host has no settings written yet` |
| settings: unreadable | `This host did not answer with a settings object` |
| settings: too big | `This host's settings are too large to send over a sync chain` |

A refusal at the door is answered **once**, and then the host closes. A client that keeps reading, or keeps
sending, is a client that reports a wire fault where the answer was a refusal.

## 9. Rules a client is expected to keep

These are not host-side enforcement. They are what every yt-msd client has always done, and a new endpoint
that does not do them is a client that breaks libraries.

  1. **Never delete a file on the host's word.** A client deletes only its own files, only on its own
     machine, only after a person at that machine agreed. A phone that wants files gone removes them from its
     own storage, and the host finds out on the next index.
  2. **Verify before you name.** Write to `<name>.tmp_sync`, hash while writing, compare with the promised
     `sha256`, rename only on a match.
  3. **Restore the date the file was made**, the `mtime` that came with it. A file that looks newer than
     every other copy makes a chain re-fetch it.
  4. **Measure only what you are about to send.**
  5. **Never invent a chain's name.** It comes from the `AUTH` answer.
  6. **Treat a code as a four-character string** from the host's alphabet, upper-cased, spaces and dashes
     taken out. It is not a number, and it is not a sync code - the alphabet has no I, O, 0 or 1 precisely
     so a rebuild code can never look like a chain's four digits.
  7. **Never send a path.** A `filename` is a bare file name.
  8. **Read one answer per command.** There are no request ids and no out-of-order replies. A client that
     reads an answer it was not expecting then answers its next request with somebody else's reply.
  9. **Keep a keepalive to one exchange.** Start it when a code is being read, stop it before the code is
     sent, and never let it overlap a file transfer.
  10. **A host's address changes; its code does not.** Re-find by code, and remember where it answered.

## 10. What this protocol does not do

Not omissions to fix silently - the reasons they are not here:

  - **No deletes over the wire.** Removals are asked for by the person standing at the machine they happen
    on, so there is no frame for it and a phone must not invent one.
  - **No authentication beyond the code.** A sync code is a shared secret of four digits and everything a
    chain does is done on a local network by machines that already share it. There is no TLS and no
    certificate. A phone client must not pretend a chain is a secure channel, and nothing belongs on a hosted
    folder that a person has not chosen to share with the network.
  - **No streaming.** A host serves files, not streams. Playing a YouTube link on a phone means the phone
    asking yt-dlp on the PC for a stream URL and playing that URL - a command this protocol does not have
    yet, and milestone M2 of `feature-android-client-2026-11-26.md`.
  - **No search over the wire.** For the same reason: search is a PC service, not a chain service.

## 11. Changing this protocol

  1. Write the change here first - the frames, the answers a client will read, the order.
  2. Say whether a machine speaking the old words would be **wrong** about the new answers. If it would,
     `PROTOCOL_VERSION` goes up and `SUPPORTED_PROTOCOL_VERSIONS` gains the versions it answers; if it
     would not, the version stays.
  3. Add the command to `protocol.py`, the answers to `host.py`, the moves to `wire.py`.
  4. Add the checks to `GUI Test Suite/probe_phone_wire.py`, then re-record
     `GUI Test Suite/fixtures/protocol/phone_session.json` - `python probe_phone_wire.py --record`, read
     what it wrote, commit it. The fixture is the contract a phone is written against, so changing it is
     changing the protocol and should be looked at rather than generated.
  5. Keep every existing client working. `SY-G16` in `probe_sync.py` is the check that a client naming no
     version is answered exactly as it always was, and it is not allowed to start failing.

## 12. What a phone client has to add around this

The wire is the small part. What a phone brings to it:

  - **Permissions and networks.** `INTERNET` and `ACCESS_NETWORK_STATE` are the two it needs to speak at all.
    mDNS/multicast discovery is not granted to ordinary apps on most access points, so a phone does the TCP
    scan and keeps a manual address-and-code entry. A phone on a guest network, a VPN, a tethered network or
    a client-isolated access point cannot see a PC at all, and the app has to say that in those words
    instead of "no hosts found".
  - **Battery and lifecycle.** A scan is 14 seconds of 128 sockets; a pull is a megabyte at a time on a
    phone that is trying to sleep. Foreground service for transfers, resumable pulls (the index gives size
    and hash, so a resume is a `PULL_FILE` of a file whose `.tmp_sync` is compared), and a sync that stops
    when the app is backgrounded.
  - **Storage.** Files a phone pulls live in app storage; a library the person can see and that other apps
    can play needs MediaStore registration, and 400 tracks is a lot of storage for a phone to have taken
    without saying so.
  - **Playback.** `Media3`/`ExoPlayer` for the pulled files. The desktop's volume, fade and ducking are a
    Qt + VLC design with no Android equivalent, so a phone starts with plain playback and does not promise
    the desktop's fader.
  - **Codes.** A restore/push code is typed on a phone keypad, four characters from a 30-letter alphabet.
    Uppercase keyboard, no autocorrect, and a keypad that shows the alphabet it expects.

## 13. Machine-readable anchors

The protocol is a document, and a document drifts. These are the places where the same rules exist as code
and as checks, so that a change here has to be made in every one of them at once.

| Where | What it is | What checks it |
| --- | --- | --- |
| `GUI Source Code/yt_msd/sync/protocol.py` | `PROTOCOL_VERSION`, every command, status, discovery type, timeout, size and the key the version travels under | the host's own suite (`probe_sync.py`), and `ProtocolNamesTest` in `android/protocol` |
| `GUI Source Code/yt_msd/sync/host.py`, `client.py`, `lan.py` | the host, the desktop client, discovery | `probe_sync.py` and `probe_phone_wire.py` |
| `GUI Source Code/GUI Test Suite/probe_phone_wire.py` | the phone's whole session against a real host, frame by frame, with a `--record` mode that writes the golden fixture | the 39 checks in `probe_phone_wire.py` |
| `GUI Source Code/GUI Test Suite/fixtures/protocol/phone_session.json` | the recording: `AUTH`, `GET_INDEX`, three `PULL_FILE`s, `GET_CONFIG`, two `PING`s, and the bodies that arrived | `FixtureContractTest`, and `PhoneSessionTest` in `:protocol` |
| `android/protocol/src/main/kotlin/dev/ytmsd/protocol/` | `Protocol.kt` (names and version rules), `Json.kt`, `Wire.kt`, `WireClient.kt`, `Transfer.kt`, `Lan.kt`, `Beacon.kt`, `Discovery.kt`, `Keys.kt`, `Restore.kt` | `android/protocol/src/test/kotlin/...` |
| `android/protocol/src/testFixtures/kotlin/dev/ytmsd/protocol/testing/` | `PhoneSession.kt` (the recording, loaded), `ScriptedHost.kt` (a host that answers out of the recording on a loopback socket), `FixtureLibrary.kt` (the MP3s the recording names) | used by the checks above and by the app's own checks |
| `android/app/src/main/kotlin/dev/ytmsd/phone/SyncViewModel.kt` | the phone's side of a session as state: hosts found, the host's list, the pull into the app's own library folder, the player | `android/app/src/test/kotlin/dev/ytmsd/phone/SyncViewModelTest.kt`, under Robolectric against `ScriptedHost` |

Running them, on a desktop with no phone:

```
gradlew :protocol:test                                    # the names, the recording, the session, frame for frame
gradlew :protocol:test --tests dev.ytmsd.protocol.LiveHostTest \
        -Pytmsd.host=192.168.1.20 -Pytmsd.port=63350 -Pytmsd.chain=7301
                                                          # the same session against a host that is running
python "GUI Test Suite\probe_phone_wire.py" --record      # re-record the golden fixture from a real host
powershell -File build_dir_cython\android_desktop_suite.ps1 -Task all
```

`ProtocolNamesTest` is the one that keeps the two copies of the protocol from drifting silently: it reads the
Python module off disk and fails on a name in one and not the other, on a count that differs, on a version
that differs, and on the version rules answering differently - including the rule under the version rule,
that a host naming no version is **not** a host naming version 1. `LiveHostTest` skips itself when no host is
named, so a plain `:protocol:test` never asks for a running host.

Two things the recording taught the Kotlin side, both of them real properties of the wire and not of the
test:

  - **A `SENDING` answer is followed by the file, every time.** The desktop probe hashes the two files it
    pulls in its loop (`PW17`) and re-pulls a third without hashing (`PW18`), so the recording has three
    `SENDING` answers and two recorded bodies. A client that reads a body after every answer is the client
    the Python host is talking to today, so `ScriptedHost` sends the file after every `SENDING` answer,
    recorded or not, and the acceptance check compares frames exactly and bodies as the recording being
    inside the trace.
  - **A number and a string are never the same frame.** A JVM writes `1.7E9` where Python writes
    `1700000000.0`; `JsonCompat` compares numbers by value, ignores key order, and refuses a string against
    a number - which is how Python compares the dicts it parsed.

## 14. The client as it is built (27 Nov 2026)

`:app` compiles and its window check passes on this desktop. What that means in protocol terms, and what it
does not:

  - **Everything a session does is the protocol module's, unchanged.** `SyncViewModel` opens a
    `WireClient`, calls `authenticate`, `index`, `pull` and `fetchConfig`, and never invents a frame; the
    scan runs on `Discovery.scan`, and the address it puts on its `AUTH` is the address the host sees it at -
    `Lan.localIp()` on a phone, and the address the recording was made from in a check, because two AUTH
    frames that name different addresses are two different frames.
  - **The window is Android views, not Compose.** `MainActivity` draws `SyncViewModel`'s state with framework
    widgets and Media3's `PlayerView`. Jetpack Compose was tried and taken out; the reason is a toolchain
    story and it is in `docs/voice-2026-11-26-android-client.md`. Nothing about this protocol depends on it.
  - **The toolchain is pinned where a build can read it.** `android/gradle/wrapper/gradle-wrapper.properties`
    names Gradle 8.14.8; the version catalog names AGP 8.13.0, Kotlin 2.0.21, kotlinx-serialization 1.7.3,
    Media3 1.5.1, Robolectric 4.15.1, compileSdk 36. A build that floats its own toolchain is a build that
    cannot say what compiled it.
  - **`GET_PLAY_URL` and `PUT_STATE` are not implemented, and are not faked.** The app pulls files and plays
    what it pulled. The command this protocol reserves for live resolution (section 12) has no frames recorded
    for it, no host answers it, and a client that asked for it would get `UNKNOWN_COMMAND`. Section 11's rules
    are what it has to go through first.







