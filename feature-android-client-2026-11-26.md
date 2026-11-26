# Android client - 26 November 2026

Status: **Exploring** - M0 (the protocol seam, the Qt-free wire client and the checks) has landed in this
repo. No Android code exists, nothing has run on a phone, and no release promises an app.

Voice note: `docs/voice-2026-11-26-android-client.md`. Specification: `docs/sync-protocol.md`.

## The problem

The library lives on a Windows PC and the listening happens on a phone. Today a phone gets at the music by
being a USB stick: sync a chain to a drive, plug the drive into something, or copy files by hand. What
people want is the PC's library, on the phone, without a cable, and without a second copy of the program
running somewhere.

## The decision

**The phone is a client of the sync protocol that already exists.** It pairs with a PC by sync code, reads
the host's index, pulls files, plays them offline, and can push the handful of files it made. It is not a
server, not a backend, not a second yt-msd, and it holds no library the PC does not know about.

Why that is the decision rather than a shortcut: the protocol already carries discovery, authentication, the
index with hashes, a verified file stream, the host's settings, a keepalive, a host rebuild and a bounded
push. It has run on six builds. A phone that speaks it needs no new PC-side service to play music offline,
and the PC keeps the rules it already keeps - a hosted folder is read-only to a client, codes are read off a
screen by a human, a host's own copy of a name stays its own, and nothing over the wire deletes.

The stack is **Kotlin + Jetpack Compose + Media3/ExoPlayer**: the protocol is a socket, a 4-byte length and
JSON, which Android does natively, and the playback stack is native. BeeWare/Briefcase is a spike (it would
run `wire.py` on a phone and prove the framing on real networks in a week, and it is not where players,
notifications, storage and distribution live). Flutter means a socket library bolted on and a second playback
bridge.

## M0 - done here, with no phone

| Deliverable | What it fixes |
| --- | --- |
| `docs/sync-protocol.md` | the frames, the order, the timeouts, the sizes, every refusal in the host's own words, the rules a client keeps, what the protocol deliberately does not do, and how to change it |
| `yt_msd/sync/protocol.py` | `PROTOCOL_VERSION = 1`, `SUPPORTED_PROTOCOL_VERSIONS`, every command name, every host status, every discovery type, index entry shapes, and the version read/accept/refuse helpers |
| `yt_msd/sync/host.py` | names its version in the `HELLO` answer and the `AUTH` answer; refuses a version it does not speak at the door |
| `yt_msd/sync/client.py` | names the desktop version on `AUTH`, records `host_protocol_version` on the chain |
| `yt_msd/sync/wire.py` | a Qt-free client written from the spec: `probe_host`, `scan_for_hosts`, `library_index`, `Keepalive`, `WireClient` (connect / authenticate / index / pull / fetch_config / ping / restore / push) |
| `GUI Test Suite/probe_phone_wire.py` | `PW1`-`PW39`: a whole phone session against a real `SyncHostServer` over a real loopback socket |
| `GUI Test Suite/fixtures/protocol/phone_session.json` | the recorded session - 18 frames, compared byte for byte on every run; the contract an app is measured against |
| `.gitignore` | one negation, so that fixture is tracked while every other generated `.json` stays ignored |

Back-compat is a check and not an assurance: `SY-G16` asserts that a client naming no version gets the answer
it has always got, and all 254 pre-existing sync checks pass unchanged.

## Milestones

**M1 - the phone plays the PC's library offline** (the app's first release)

Kotlin: scan with `HELLO`, pair by code, `AUTH`, `GET_INDEX`, list, `PULL_FILE` with the host's announced
size and sha256, store, play with Media3. Manual address-and-code entry beside the scan. A pull resumes by
comparing the `.tmp_sync` it already has.

Acceptance: the app's frames match `fixtures/protocol/phone_session.json` frame for frame; a host running
3.5 answers it; a host running 3.4 answers it; a refused code reads as a refusal on screen, not as a hang.

**M2 - live YouTube playback on the phone.** A PC-side command that resolves a stream URL for the phone using
the PC's existing yt-dlp settings - which already ask for `youtube:player_client=android` and the Android
user agent. The phone plays the URL; the signed query never enters a log, the rule `TR11`-`TR13` already
hold on the desktop. Acceptance: the URL never appears in `--trace` output; a phone on a guest network fails
as "the PC could not reach YouTube", not as "no hosts found".

**M3 - search and suggest from the phone**, answered by the PC, with the PC's own filters.

**M4 - the phone as a remote control** of a running PC: queue, next, pause. Every destructive action stays on
the PC's own screen; nothing in M4 deletes, and nothing in M4 is a button on a phone.

## Test seams

  - **The fixture is the acceptance test.** `probe_phone_wire.py --record` writes
    `fixtures/protocol/phone_session.json`; every run compares against it. A phone client passes when the
    frames it sends and the frames it reads are that file. Kotlin does not get to invent its own ordering.
  - **`probe_phone_wire.py` is the regression gate for protocol changes.** A new command, a new answer, a
    reordered exchange - it fails first, on this machine, before a phone is involved.
  - **`probe_sync.py` is the gate on the desktop's side.** `SY-G15`-`SY-G17` hold the version rules;
    `SY-G16` in particular is the rule that a 3.x client that names no version is answered as it always was.
  - **On a real network, the seams are manual.** The suite runs on loopback. M1's real test is a phone on the
    same Wi-Fi as a PC that has run yt-msd once and answered the firewall prompt, plus a phone on a network
    that cannot see the PC at all - which is the case the app has to explain in words.

## Risks

  1. **Discovery on a phone is the weakest part**, and it is not a code problem. Multicast is not granted to
     ordinary apps on most access points; client isolation, guest networks, VPNs and a Windows profile that
     never answered the firewall prompt each kill it in a different way. Mitigation is the manual
     address-and-code entry, kept honest by an error message that names the network reason.
  2. **A sync code is not a credential.** There is no TLS in this protocol and this plan does not add any. A
     phone app that displays "connected securely" would be lying; the app says which machine it joined and
     what that machine hosts.
  3. **Storage and battery.** 400 tracks is a lot of storage taken quietly; a background pull is a phone that
     will be killed. Foreground service, explicit "download this" actions, resumable pulls, and a sync that
     stops when the app is backgrounded.
  4. **Two protocol dialects drifting apart.** The spec, `protocol.py`, `host.py`, `wire.py` and the fixture
     must agree. `PW3`-`PW5` assert that every name in `protocol.py` is a word `host.py` really says, and
     `PW37` asserts the recorded session is the session the host answers.
  5. **The desktop client is not on the wire layer.** `client.py` keeps its own socket code. A protocol change
     now has to be made in two places, which is a known cost of not refactoring a 1,190-line file that 257
     checks drive.
  6. **The Android app needs its own repo, Gradle, signing and a distribution answer** - all outside this
     repo's build tooling, and all unbudgeted.

## Out of scope for this feature

A phone that hosts a chain. A phone that deletes files on a PC. Any authentication beyond the sync code.
The desktop's volume, fade and ducking on the phone. An HTTP server, a web client, a cloud relay, a NAT
traversal: a phone on the same network as the PC is the whole scope, and everything else is a different
project.

## What M0 deliberately did not do

  - It did not move `client.py` onto `wire.py`. `wire.py` is the reference; the desktop client's socket code
    stays where 257 checks already drive it.
  - It did not replace `client.py`'s literals with `protocol.py` constants. `probe_phone_wire.py` asserts the
    constants are the words the host says (`PW3`-`PW5`), which is the anti-drift property the constants are
    for, without rewriting a heavily-probed file.
  - It did not add a command. Version 1 is the protocol 3.0 has always spoken, named.

## Rollback

`protocol.py` and `wire.py` are new files that nothing in the shipped program depends on for behaviour: the
version fields are additive keys in existing answers, and the version refusal is one guard at the door.
Removing them - revert `host.py` and `client.py`, delete the two modules, drop the `PW` suite, the fixture
and the `.gitignore` negation - leaves 3.5 exactly as it was. The spec, the Voice note and this plan are
documents and cost nothing to keep.

## Files this round touches

`GUI Source Code/yt_msd/sync/protocol.py` · `GUI Source Code/yt_msd/sync/wire.py` ·
`GUI Source Code/yt_msd/sync/host.py` · `GUI Source Code/yt_msd/sync/client.py` ·
`GUI Source Code/GUI Test Suite/probe_phone_wire.py` ·
`GUI Source Code/GUI Test Suite/probe_sync.py` ·
`GUI Source Code/GUI Test Suite/fixtures/protocol/phone_session.json` · `.gitignore` ·
`GUI Source Code/GUI Test Suite/Test Suite README.md` · `docs/sync-protocol.md` ·
`docs/voice-2026-11-26-android-client.md` · this plan.

