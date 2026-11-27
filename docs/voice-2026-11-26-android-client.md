# This file is AI slop, just like all the code in this project. I didn't write this
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

## 27 November 2026 - the phone's protocol runs its own checks, on this desktop

Status: **Building.** `android/` is a Gradle build with two modules, and the protocol module's checks are
green here - no phone, no emulator, no PC hosting a chain.

  - **`:protocol` is plain Kotlin/JVM.** `Protocol.kt` mirrors `yt_msd/sync/protocol.py`, `Wire.kt` and
    `WireClient.kt` mirror `sync/wire.py` and `sync/transfer.py` - the four-byte big-endian length and the
    UTF-8 JSON frame, the file body that rides after a `SENDING` answer, the timeouts, the `Keepalive`. It
    needs no Android, which is the whole point: the checks below run on the JVM this machine already has.
  - **The acceptance check is the recording, not a story about it.** `PhoneSessionTest` runs the Kotlin client
    against `ScriptedHost`, which answers out of
    `GUI Test Suite/fixtures/protocol/phone_session.json` on a loopback socket, and compares what the phone
    spoke and heard with the recording, frame for frame: `AUTH`, `GET_INDEX`, three `PULL_FILE`s,
    `GET_CONFIG`, two `PING`s, and the bodies that arrived, hashed against the checksums the host announced.
  - **The names cannot drift in silence.** `ProtocolNamesTest` reads
    `GUI Source Code/yt_msd/sync/protocol.py` off disk and fails when a `CMD_*`, `STATUS_*` or `TYPE_*` name
    in the Python module is missing from the Kotlin list, when the counts differ, when the version, the key
    it travels under, the app's own name, the sync-code length or the checksum length disagree, and when the
    version rules answer differently than the host's rules answer. The rule the suite keeps alive - *a client
    naming no version is an old client and is answered as one* - is checked in the Kotlin copy too, and so is
    the trap under it: a host naming no version is **not** a host naming version 1, and
    `answeredProtocolVersion` returns nothing at all for it.
  - **`FixtureContractTest` says out loud when the contract is missing**: no fixture, empty fixture, a fixture
    recorded from another protocol version, a chain that is not a sync code, a first frame that is not an
    `AUTH`, a `SENDING` answer with a body recorded that no answer promised.
  - **`LiveHostTest` runs the same session against a host that is not a recording** -
    `gradlew :protocol:test --tests dev.ytmsd.protocol.LiveHostTest -Pytmsd.host=192.168.1.20
    -Pytmsd.port=63350 -Pytmsd.chain=7301`. Name no host and both its checks skip themselves, which is what
    keeps a plain `gradlew :protocol:test` runnable with no host running.
  - **Two things the recording taught, learned the hard way.** The recording traces a body for the two files
    the desktop probe hashes (`PW17`) and not for the re-pull (`PW18`), so `ScriptedHost` answers every
    `SENDING` with the file - the way the real host does - and the acceptance check compares frames exactly
    and bodies as the recording being inside the trace. And a JVM prints `1.7E9` where Python prints
    `1700000000.0`, so frames are compared as Python compares dicts: numbers by value, key order
    irrelevant, and **a string never equal to a number**.

**Toolchain on this machine, 27 Nov 2026.** JDK is the Adoptium 21 that `JAVA_HOME` names
(`jdk-21.0.12.101-hotspot` - a script that invented a JDK path from a version number is how `avdmanager`
failed first). Gradle 8.14.8 in `%USERPROFILE%\.devtools`, with the wrapper now in `android/`. Android SDK in
`%LOCALAPPDATA%\Android\Sdk`: `cmdline-tools/latest` 23.0.0, `platform-tools` 37.0.3, `platforms/android-35`,
`build-tools/35.0.0`, `emulator` 37.3.10, `system-images/android-35/google_apis/x86_64`, and the AVD
`ytmsd_mvp` (pixel_6). `emulator -accel-check` reports **WHPX is installed and usable**, so the emulator is
not a software-mode run. `sdkmanager.bat` is a batch file and `cmd` splits `platforms;android-35` into two
arguments - the package name has to reach it wrapped in quotes, which is what made the first installs
report "Package platforms not found" with exit 0.

**VS Code is the development seat.** `.vscode/settings.json` points the Java and Gradle integrations
(`redhat.java`, `vscjava.vscode-gradle`, both already installed) at that JDK, that Gradle and that SDK, and
`.vscode/tasks.json` carries `yt-msd: Desktop Python Gate`, `yt-msd: Phone Wire Checks`,
`yt-msd: Record Phone Fixture`, `yt-msd: Android Protocol Tests`, `yt-msd: Android Protocol Tests (live host)`,
`yt-msd: Android Window Checks`, `yt-msd: Build Android Debug`, `yt-msd: Gradle Sync`,
`yt-msd: Toolchain Check`, and the two that need a device: Start AVD and Logcat.
`build_dir_cython/android_desktop_suite.ps1` runs the same things by name (`-Task wire`, `-Task gate`,
`-Task protocol`, `-Task app`, `-Task apptest`, `-Task record`, `-Task all`), and exits non-zero if any of
them failed. No Kotlin language-server extension was installed: the extension ids tried
(`fwkKotlin.kotlin`, `mathiassoeholm.kotlin-vscode`, `vscjava.vscode-android-debug`) are not on the
marketplace from this machine - `code --install-extension` reports each as not found - so Kotlin is compiled
and checked by Gradle, from the tasks, rather than analysed by an editor plugin.

**What the emulator does not change.** Nothing above needs it. The emulator and `adb` are what the *device*
tests will need - the scan across a real network, MediaStore, a real Media3 decoder, battery rules - and none
of that is what the protocol checks prove.

## 27 November 2026 - the window builds, and Compose is out of the stack

Status: **Building.** `:app:assembleDebug` produces an APK on this machine and `:app:testDebugUnitTest` is
green in it - the phone's own window pairing with a scripted host, pulling a file and hashing it to what the
host promised, with no phone and no emulator.

**Compose is out, and the reason is the toolchain, not taste.** The 26 November note above named
"Kotlin + Jetpack Compose + Media3" as the stack. It is now Kotlin + Android views + Media3, and the reason
has to be written down because it cost a day and will cost the next person the same day if it is not:

  - **`Activity.setContent { }` is a `COMPOSABLE_EXPECTED` on the 2026 compilers.** The Kotlin-owned Compose
    compiler - 2.1.x, 2.2.x, 2.4.21 - enforces composability at the call site of an inline composable lambda,
    which is the way every Compose window starts: the ordinary `onCreate` and its `setContent { }`. The marker
    that makes that call legal, `@ComposableInferredTarget` in `androidx.activity:activity-compose:1.13.0`, is
    written against the **AndroidX-owned** Compose compiler (`androidx.compose.compiler:compiler:1.5.x`), and
    Kotlin 2.4.21's Gradle plugin has no knob that names a compiler plugin to load; AGP 9.1's built-in Kotlin
    (2.2.10) is the same compiler under the same rule. The diagnostic points at the application code and is a
    property of the toolchain - which is why the attempts to fix it (importing `Composable`, marking the
    activity's own lambda, `ComposeView`, `ui-tooling-preview`, a non-inline content lambda, naming
    `compose.components.internal.*`) each failed: none of them changes what the loaded compiler enforces.
  - **`androidx.compose.runtime:runtime` resolves as a component metadata module on the newest line** - the
    plain jar under `var1/` is a stub - so a checker that looks for the marker class in the jar a dependency
    resolved to finds nothing, and the failure it reports names the source file, not the dependency.
  - **What is pinned now is what compiled this app**: AGP 8.13.0, Gradle 8.14.8, Kotlin 2.0.21,
    kotlinx-serialization 1.7.3 (1.9.0 carries metadata a 2.0.21 compiler refuses to read), coroutines 1.9.0,
    Media3 1.5.1, Robolectric 4.15.1 (the release carrying an API 36 image), compileSdk/targetSdk 36. The
    wrapper names the Gradle, so the build says what it was built with; VS Code's Gradle integration points at
    the same 8.14.8.
  - With that in place the window is **Android views** - `ComponentActivity`, a `LinearLayout` built in code,
    two `ListView`s with array adapters, a `PlayerView` from Media3 - and no Compose artifact is in the build at
    all, which is also why the window check runs under Robolectric in one place. If Compose comes back it comes
    back with this paragraph read first, and with a named compiler it can be pointed at.

**What is green, on 27 November, on this machine.**

  - `:protocol:test` - 16 checks, 0 failed, 2 skipped (the live-host checks skip themselves when no host is
    named). `gradlew.bat :protocol:test` from `android/`.
  - `:app:assembleDebug` - `app/build/outputs/apk/debug/app-debug.apk`.
  - `:app:testDebugUnitTest` - 1 check, 0 failed. It is the M1 acceptance check: `SyncViewModelTest` pairs with
    `ScriptedHost` over a loopback socket and compares every frame the phone spoke with
    `GUI Test Suite/fixtures/protocol/phone_session.json`, then asserts the pulled file is whole in the app's
    own library folder, byte for byte, hashing to the checksum the host announced.
  - The 39 phone-wire checks and the 1454-check desktop gate - `build_dir_cython/android_desktop_suite.ps1
    -Task all`, which runs the wire checks, the gate, the Kotlin protocol checks, the window build and the
    window checks, and exits non-zero if any of them failed.

**What the Kotlin checks need to be given, and what they find for themselves.** The acceptance recording is
`GUI Source Code/GUI Test Suite/fixtures/protocol/phone_session.json`, and the chain it was recorded from is
`7301`. Each module's `build.gradle.kts` resolves that path against the repository root the `android/` build
sits inside and hands it to the tests as the `ytmsd.fixture` system property - absolute, so it does not depend
on which module's test task ran first - and `-Pytmsd.fixture=<path>` replaces it on a machine that keeps the
suite elsewhere. `-Pytmsd.chain=` names the chain (the suite passes it when `-Chain` is named; the build files
default it to `7301`, and `android/gradle.properties` carries that default). `LiveHostTest` takes
`-Pytmsd.host`, `-Pytmsd.port` and `-Pytmsd.chain`, and skips itself when no host is named, which is what keeps
a plain `:protocol:test` runnable with no host running.

```
cd android
gradlew.bat :protocol:test                              # 16 checks, 2 skipped with no host named
gradlew.bat :app:testDebugUnitTest                      # 1 check, Robolectric, the fixture as the contract
gradlew.bat :app:assembleDebug                          # app/build/outputs/apk/debug/app-debug.apk
cd ..\build_dir_cython
powershell -File android_desktop_suite.ps1 -Task all    # wire + gate + protocol + window checks + APK
powershell -File android_desktop_suite.ps1 -Task protocol -Chain 7301
powershell -File protocol_test.ps1                      # the Kotlin protocol checks alone
```


**Two traps worth naming, because they are not Kotlin's fault.**

  - **A property is a string list.** `-Pandroidx.suppressComposabilityCheckWarning=true` is read by Gradle as
    `["true"]` and Kotlin's `String.toBoolean()` on that is `false`, so a boolean Gradle property set from a
    command line can be silently off. The same trap is in the suite's own `-Pytmsd.chain=` - that is why
    `android_desktop_suite.ps1` builds its argument list as single strings.
  - **A batch file cannot rewrite itself.** `gradlew.bat wrapper` on Windows dies with *"The system cannot
    find the batch label specified - exitWithErrorLevel"* when the wrapper regenerates the very `.bat` it is
    running from. The suite now leaves an existing wrapper alone - which is the right rule anyway: the wrapper
    names its own Gradle, and a build that regenerates its own toolchain is a build that has no version.

**What the app is, in one paragraph.** `SyncViewModel` owns the socket, the list, the pull, the library folder
and the player, and exposes them as state; `MainActivity` draws that state with framework widgets. The window
is a scanning line, the hosts it found, a sync-code field, the host's list, and a `PlayerView`; the pull lands
in the app's own `filesDir/yt-msd` (the device rule - app-private storage on Android 11+, no `MANAGE_EXTERNAL_STORAGE`).
`GET_PLAY_URL`, `PUT_STATE`, scan discovery and the foreground service are the next things, in the order the
milestones name them.

### What the full run taught the suite, the same day

The first `-Task all` run (wire, gate, protocol, app, window checks) stopped on one check, and both things it
found are kept.

  - **`PW36` found a real race in the host, not in the probe.** A push that nobody read the code for is closed
    by `PUSH_CANCEL`, and `host.py` answered `CANCELLED` *before* it reported `push_cancelled` to the callback
    the host's own window reads - so a client told the offer was closed could ask the host where its code went
    and get told it was still on the screen. `PW28` found the same race on the restore side the same morning
    (`RESTORE_CLOSED` on a `PING`, with the report after it) and `PW29` had been passing the same shape on
    luck. Every place a host's screen changes and a client is told about it over the wire is now **report
    first, answer second** - a code issued, a code named wrongly, a code accepted, an offer taken away on the
    host's own screen, a cancel from either side, for a restore and for a push. The rule the probes lean on is
    that a code exists *only* in the host's own report, so a client told a code is gone must not be able to ask
    this machine's window where it is and be told it is still there; a check reading that window fails exactly
    the way a window would, on a loaded machine, when the order is the other way round.
  - **A step with no program in it cannot have an exit code.** The suite script judged every step with
    `$LASTEXITCODE -ne 0`; `$LASTEXITCODE` is session-wide and `$null` before the first program runs, and
    PowerShell says `$null -ne 0`, so the toolchain report - a step that runs no program - was recorded as
    `FAILED: toolchain (exit )`, with no number. The step now clears the code before running and reads it as a
    number, so a step fails on the program it ran and on nothing else. The same class of trap as a Gradle
    property read as a list: the tool reports a value that means nothing, and the script believes it.
  - After both, `-Task all` is green end to end: 39 wire, 1454 gate, 16 protocol (2 skipped with no live host
    named), 1 window check, and an APK.



