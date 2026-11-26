# Voice note - 26 November 2026 - "make the phone part of this"

Status: **Exploring.** M0 (the protocol seam and its checks) has landed in this repo. No Android code
exists. Nothing here is a promise about shipping an app.

## What was asked

yt-msd runs on Windows. The library lives on a PC, and the thing people actually listen to is in their
pocket. The question was how a phone gets at that library, and how much of yt-msd a phone should be.

## The decision, and the reason it is the right one

**The phone is a client of the sync protocol that already exists. It is not a new backend, not a server,
and not a second yt-msd.**

Everything a phone needs for offline playback is already on the wire, trusted by nothing beyond a
four-digit code, and running on six builds of Windows software people already have installed:

  - discovery - a TCP `HELLO` scan across the networks the phone is on, and a UDP beacon;
  - `AUTH` - say which chain, learn what the host calls it;
  - `GET_INDEX` - the host's library with size, date, sha256 and tags;
  - `PULL_FILE` - one file, streamed, verified by the checksum the host announced;
  - `GET_CONFIG` - the host's settings;
  - `PING` - keep a connection warm while a person reads a code off a screen;
  - `RESTORE_*` and `PUSH_*` - rebuild a host, offer a handful of new files.

So the work is not inventing a protocol. It is writing the protocol down, giving it a version number it
never had, making a Qt-free client that speaks it, and checking the whole phone conversation against a real
host - all of which is possible with no phone in the room, and which is what this round did.

## What is true today because of it

  - `docs/sync-protocol.md` is the specification: frames, order, timeouts, sizes, every refusal in the words
    the host uses, the rules a client must keep, and what the protocol deliberately does not do.
  - `yt_msd/sync/protocol.py` is the version and the names. `PROTOCOL_VERSION = 1`, every command, every
    status, every discovery type. A phone reads a list of names, not a control flow.
  - `yt_msd/sync/host.py` names its version at the door and in the `HELLO` answer, and refuses a version it
    does not speak. `yt_msd/sync/client.py` names the desktop's version on its `AUTH` and records what the
    host answers. **A client that names no version is answered exactly as it always was** - that is
    `SY-G16`, and it is the check that keeps 3.0-to-3.5 clients alive.
  - `yt_msd/sync/wire.py` is a client with no Qt in it at all - no `PySide6`, no window, no signal. It is the
    Kotlin port's reference: connect, authenticate, index, pull, config, ping, keepalive, restore, push.
  - `GUI Test Suite/probe_phone_wire.py` (`PW1`-`PW39`) drives that client against a real `SyncHostServer`
    over a real socket: the discovery a phone runs, the whole offline-playback session, the refusals at the
    door, a keepalive during a code read, a whole Restore Host exchange, a coded push and a code-free one.
    39 checks.
  - `GUI Test Suite/fixtures/protocol/phone_session.json` is the recording of one session - 18 frames, byte
    for byte, compared on every run. That file is the contract the app is written against. It is tracked by
    an exception to the repo's `*.json` rule: it is not scratch, and changing it changes the protocol.
  - The gate is **1454 checks** (was 1412): `probe_sync.py` gained `SY-G15`-`SY-G17` for the version (257
    checks), and `probe_phone_wire.py` is a tenth gate suite (39).

## The rules that came out of reading the code, and that the app must not break

  1. **Nothing over the wire deletes.** There is no frame for it and a phone must not invent one. Removals
     are asked for by the person standing at the machine they happen on.
  2. **A sync code is the whole of the trust.** There is no TLS and no certificate. A phone app must not
     present a chain as a secure channel, and a hosted folder must contain nothing a person has not chosen to
     share with the network.
  3. **The code that authorises a rebuild or a push never travels on the wire.** It appears on the host's
     screen and a human reads it out. A phone's job there is a good four-character keypad - uppercase, no
     autocorrect, the 30-letter alphabet with I/O/0/1 taken out - and a keepalive that keeps the host
     interested while somebody is typing.
  4. **Discovery must not depend on the beacon.** Directed broadcasts are dropped by most access points; the
     TCP scan is what works, and a phone needs a manual address-and-code entry for the networks where even
     that fails. "No hosts found" is not good enough when the real reason is a guest network.
  5. **Files land verified.** Write to `.tmp_sync`, hash while writing, compare with the announced sha256,
     rename only on a match, restore the file's own date.
  6. **A push does not overwrite a host's own copy of a name it holds.** The host keeps what it has.

## What a phone has to bring that the desktop never had to think about

Multicast is not granted to ordinary apps on most access points. Foreground service for transfers, on a phone
that wants to sleep. MediaStore for a library other apps can see. Storage: 400 tracks is a lot to have taken
without asking. Playback via Media3/ExoPlayer - the desktop's volume, fade and ducking are a Qt + VLC design
with no Android equivalent, so a phone starts with plain playback and does not promise the fader.

## Stack, and why

**Kotlin + Jetpack Compose + Media3/ExoPlayer.** The protocol is a socket, a 4-byte length and JSON: the
Android standard stack does it natively, the playback stack is native, and an app a person installs on a
phone has to be a real Android app to stay maintainable.

BeeWare/Briefcase is worth a spike, not a plan: it would let `wire.py` run on a phone and prove the framing on
real networks inside a week, and it is not where a player, notifications, storage and the Play Store live.
Flutter is a fine UI toolkit with a socket library bolted on and a second playback bridge to write; the Kotlin
route has fewer bridges.

## Milestones

  - **M0 - done in this repo, no phone.** Spec + version + Qt-free wire + 39 checks + golden fixture.
  - **M1 - the MVP.** Kotlin: scan, pair by code, list, pull, play offline. Acceptance: the app's frames match
    `fixtures/protocol/phone_session.json` frame for frame.
  - **M2 - live playback.** A new PC-side command that resolves a stream URL for the phone using the PC's
    existing yt-dlp settings - which already ask for the Android player client (`youtube:player_client=android`
    and the Android YouTube user agent), so the resolution that a phone needs is the resolution this program
    already does, on the machine that has yt-dlp, ffmpeg and the network. Nothing signed ever printed into a
    log, the same rule `TR11`-`TR13` hold on the desktop.
  - **M3 - search and suggest from the phone**, answered by the PC.
  - **M4 - the phone as a remote control** of a PC: queue, next, pause - every destructive action staying on
    the PC's own screen.

M2 and M3 add commands to a versioned protocol, which is what section 11 of `docs/sync-protocol.md` is for:
write the frames first, decide whether the number moves, add the checks, re-record the fixture, keep the 3.x
clients answering as they always did.

## What is not known

  - Nothing has run on a phone. No Android build exists, so nothing here has met a real access point,
    Android's battery rules, MediaStore, or a real Media3 decoder.
  - `probe_phone_wire.py` proves the exchange on loopback on this machine. It does not prove a phone can reach
    a PC through a particular router, and it will not: guest networks, client isolation, VPNs, AP isolation
    and a firewall that never prompted for yt-msd are all outside what a loopback test can see.
  - The desktop's own client (`yt_msd/sync/client.py`) has **not** been moved onto `wire.py`. It keeps its
    socket code where it has always been and `wire.py` is the reference the phone is written from. Moving the
    desktop client onto the same seam is worth doing, and is not done.
  - The Android app is a separate repo, built with Gradle, and needs a CI decision that this repo's
    PowerShell-and-Task-Scheduler build tooling does not cover.

## The next thing that needs a human

M1 in Kotlin, on a phone, on a real network - with `docs/sync-protocol.md` as the specification,
`wire.py` as the reference, and `probe_phone_wire.py`'s fixture as the acceptance test. Before that: the
Import-dialog fix that this round also shipped needs its manual pass on the installed app.

