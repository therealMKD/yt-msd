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

### The emulator boots in gesture navigation, and that is why the buttons are missing

`ytmsd_mvp` is a `pixel_6`, and a pixel_6 boots in **gesture navigation** (`navigation_mode` 2, the
`com.android.internal.systemui.navbar.gestural` runtime overlay enabled): there is no Home / Back / Overview
bar on the screen at all, and Back is a swipe from the left edge - which is not a thing a mouse does naturally,
and is why the first thing said about the emulator was "the buttons don't work". They work; there are no
buttons. Three ways to have them back, in the order of usefulness:

  - **Three-button navigation**, from adb, and it survives a reboot:
    `adb shell cmd overlay enable com.android.internal.systemui.navbar.threebutton`,
    `adb shell cmd overlay disable com.android.internal.systemui.navbar.gestural`, which lands
    `navigation_mode` at 0 and puts the bar on the screen.
  - **The emulator's own toolbar** (the vertical strip at the right of the device window) has Back, Home,
    Overview, rotate, volume and power - those send the key events, and the PC keyboard's `Esc` is Back when
    the window has focus, with the rest of the shortcuts listed under **Extended controls → Settings →
    Enable keyboard shortcuts**.
  - **Key events from the command line**, which is what a check would use: `adb shell input keyevent 4` is
    Back, `3` is Home, `187` is Overview. Proved on this machine by watching `dumpsys activity activities`:
    with the app in front, `3` puts `com.google.android.apps.nexuslauncher/.NexusLauncherActivity` in focus and
    `4` puts it back from the app - Home and Back, answered.

This is a device fact, not a project fact, and it is written down for the same reason as the `sdkmanager`
semicolon: the next person to boot `ytmsd_mvp` will ask the same question.

## 28 November 2026 - the phone plays, out loud, and says what it is doing

Scan, pair, take, play ran end to end on the emulator against the real host on port 63350 with code 6767. The
file that landed in `/data/data/dev.ytmsd.phone/files/yt-msd/` is byte-identical to `C:/Users/mason/Music/`
(`db492fd4…549ec1`, 7,878,986 bytes both sides), and the sound came out of the phone.

What the window now says, read off screenshots:

  - `Playing.` / `Paused. You pressed Pause.` / `The player is stopped.` / `The file has finished.`, each from
    the player's own callbacks. The Pause half needed `onPlayWhenReadyChanged`, because Media3 is
    `STATE_READY` on both sides of a Pause and `onPlaybackStateChanged` has nothing to say about it.
  - `Volume 3/15` beside a slider that is the phone's `STREAM_MUSIC` dial - the same dial the hardware keys, a
    headset and the system's own slider move. Tapping the app's slider at 20% moved the phone's
    `streamVolume` from 4 to 2; tapping its left end put the phone at 0 with `Muted: true`.
  - When Play finds the phone muted, it raises it to a quarter of the dial and says why on the same line:
    `Playing. (the phone's volume was at 0, so it is at 3)`. The note rides the state line, because the
    player's own `Playing.` arrives a moment later and would otherwise erase the only words that explain a
    quiet phone.
  - A notification shade pulled down over playing music does not end the music: `state:started` with
    `USAGE_MEDIA` / `CONTENT_TYPE_MUSIC` before, during and after, and no player-stop message.

The audio server was the referee for all of it - `dumpsys audio` for the stream and the player list,
`dumpsys media_session` for the session - because `uiautomator dump` refuses to work while the video view's
progress bar animates, and the row of buttons sits in a different place in the window when the video view is
there to move it.

## 28 November 2026 - a phone that stopped to read a screen had been losing its host

Take answered "the host would not send (G)i-dle - HWAA.mp3", and the next press said `Taking …` and meant it for
the rest of the session. It is the host that ends a session nobody is using: `host.py` reads the next command
with `recv_json_msg(sock, timeout=30.0)` and `break`s out when nothing arrives, so the connection closes. A PC
never sits that long; a phone lists 458 tracks, a person reads them, and 30 seconds is gone before anybody picks
a row. The phone cannot see the connection close. So the first press asked a host that had already gone, got
nothing back, and reported it as a refusal; the second press wrote into a socket nobody is reading, the write
threw, and nothing in the take was listening for a thrown write - a take runs on a worker whose exceptions go
into a `Future` nobody collects, which is a window that says `Taking …` and never stops.

Two things are true now:

  - **The phone keeps its connection warm.** A `PING` every 10 seconds from the moment a list lands on screen -
    the keepalive the protocol already prescribes, which the desktop client has always run - and the pings put
    away before a file is asked for, because a `PING` in the middle of a transfer is bytes the host reads as its
    next frame. Measured on the emulator: paired at 12:43:48, nothing pressed for a minute, `ss` still showing
    `ESTAB [::ffff:10.0.2.16]:33850 [::ffff:10.0.2.2]:63350`, Take at 12:44:46 and
    `pull (G)i-dle - HWAA.mp3: ok=true` at 12:44:49.
  - **A take that stops says so.** A frame that is nothing at all, a write the socket refuses, a read that finds
    the connection aborted, all mean a host that is gone and end with "the host closed this connection - pair
    with it again", and a take is never allowed to sit on `Taking …` with nobody reporting on it. A read that
    merely timed out is *not* a lost host - a slow drive hashing a whole library is a host that is there and
    slow - so that one case keeps the connection, as the desktop client's own `_recv` has always done.

Two checks keep it honest, both against the scripted host that answers out of the recorded session: one leaves a
paired phone parked for two intervals and reads the `PING`s the host answered; one hangs up on a paired phone
and presses Take twice, and both presses have to name the lost connection and neither may sit on `Taking …`.

And two things about automating this window, both learned the slow way:

  - **A press is swallowed while the keyboard is animating in.** Type the code, send `keyevent 111`, and give
    the window two seconds before the next press means anything; a press that lands during the insets animation
    looks exactly like a button that does nothing (the log line for it is
    `force finish cuj, time out: J<IME_INSETS_SHOW_ANIMATION>`).
  - **The volume slider sits about 56 pixels under the button row once the video view has appeared**, and its
    touch area is generous: presses aimed at the row at y 1900 moved the phone's volume from 13 to 11 and then
    to 3 while the buttons were the target. Take the coordinates of the node being pressed from the window, and
    read the phone's volume from `dumpsys audio` rather than assuming it did not move.

## 28 November 2026 - the phone remembers the hosts it has synced with, gets the desktop's player bar, and is 30 percent louder

Four asks, all of them about the sync side and none about searching YouTube: a host that is forgotten when the
app closes is not a host; a phone with no player bar is a phone you can only ever play one file on; every track
should be louder than the file on the phone before the phone's dial has anything to say about it; and the phone
should be able to name a host by hand.

### A host this phone has synced with is a host it knows

`SavedHosts` writes six facts into the app's own preferences on a pair the host accepted: the address, the
port, the `sync_code` that pair used, the chain name the host called itself, the protocol version it answered
with, and when it was last seen. Nothing is guessed and nothing is derived - every one of those is something
the host said. The next start of the app lists them **before any scanning**, marked `saved`, with the chain and
the code on the row, and pressing one pairs with the stored code. The desktop's rule is the one being matched:
a chain you have synced with is a chain you have, and it is not something a machine re-learns every time it
boots.

Three things about it are decisions, not consequences:

  - **A record is written by a successful pair only.** A pair that was refused, and an address typed in by
    hand, are not hosts the phone has synced with, and remembering them would make the list a list of guesses.
  - **`Clear` does not forget a host.** It ends this session and puts the saved hosts back on the screen. A
    button called Clear that emptied the phone's memory of every PC it has ever paired with is a button that
    destroys the thing this exists to do. `Forget host` is the one that removes a record, and it takes the
    connection with it.
  - **The app does not pair by itself at start-up.** The host is *on the screen*, and one press pairs with it.
    A phone that opens and immediately starts dialling every address it has ever seen is a phone making
    connections a person did not ask for, on a network it may not be on any more.

### The player bar is the desktop's controls, in the order a phone wants them

`Shuffle` outside left, `Prev` / `Play-Pause` / `Restart` / `Next` across the middle, and one button cycling
`Stop after current` through `Off`, `Once`, `Always` outside right - one click per state, `Off -> Once -> Always
-> Off`. The play button says what pressing it would do, the desktop's rule for the same button: `Play` starts a
stopped track, `Pause` holds a playing one, `Replay` takes a finished one from the top. The stop-after button is
the desktop's own square with the desktop's own labels, in the desktop's own colours - grey, `#FF8C00` for
"this track is the last one", `#E31E24` for "every track stops when it ends" - and the sentences it says are the
ones `set_stop_after_current` and `_finish_stop_after_current` say:

  - `Stop after current: off - playback will advance to the next track.`
  - `Stop after current: once - this track is the last one.`
  - `Stop after current: always - every track stops when it ends.`
  - `Stopped after the current track.` / `Stopped after the current track - Stop after current is still on.`

The rules themselves are in `PlayQueue`, plain Kotlin with no player and no Android in it, so they are checked
as rules: shuffle takes a random one of the tracks not played yet and, when it has played everything, starts a
fresh order that does not repeat the track just heard; `Prev` walks back out of the order the shuffle made, and
off shuffle walks the host's list; a "once" is spent by the track it stopped, and an "always" is not spent by
anything. The bar's presses are thin readers of that.
Two things the desktop does not have to think about: the **captions are words**, because the desktop's glyphs
are Segoe MDL2 Assets codepoints (`U+E768`, `U+E769`, `U+E72C`, `U+E892`, `U+E893`, `U+E8B1`) that exist in that
Windows font and in no Android font - on a phone they draw empty boxes - so the bar uses the words the desktop's
own tray menu uses, and every button carries the desktop's tooltip as its `tooltipText`; and **advancing to a
track that is not on the phone is said, not swallowed** - `X is not on the phone yet - Take it first.` is the end
of what a phone can play by itself, and a session that stops there in silence is a session that looks broken.
The list's row moves with the bar: Prev/Next/auto-advance check the row they land on, because the bar's Next is
the same fact as the list's Play - which track the phone is standing on.

### Every track is 30 percent louder than the file, before the dial applies

`GainAudioProcessor` scales decoded samples - 16-bit, 24-bit packed, 32-bit and float - by `1.30`, clamping at
full scale, and it runs inside the player's audio sink: between the decoder and the phone's audio track. The
phone's dial, its ducking under a notification, its headset switch, and its volume curve all apply to a signal
that is already 30 percent louder, which is what "before the volume applies at all" means in a media player, and
the only place a player is allowed to make a track louder than the phone's dial. `BoostedRenderersFactory` is
where it is installed - `DefaultRenderersFactory` builds the sink, and the sink is where a processor chain lives.

It is a processor of this app's own because Media3 1.5.1 has no volume scaling: `SonicAudioProcessor` in the
version this app compiles against has `setSpeed` and `setPitch` and nothing else - `setVolumeScalingEnabled` and
`setVolume` arrive in Media3 1.6 - and the version catalog pins 1.5.1 for the reasons written in the version
catalog. `javap` on the artifact in the Gradle cache is what said so, which is the way to find out what a media
library you are compiling against has, rather than what a later one has.

What it costs, said plainly: replacing the factory's audio sink takes the audio-offload path with it, which is
the same trade every app that scales its own audio makes; and a track recorded hot clips at the top of the
range, because that is what a gain does - a clamped sample is distortion at the peaks, and a wrapped one is a
buzz. The desktop has run its volume dial to 150 percent for years for the same reason the phone needed 13 of 15
to hear a track normally: the loudness is wanted above the dial, not below it.

### A host can be typed in

The code box has a neighbour now: an address, a port (default 63350), and `Add`. A scan asks the networks the
phone is standing on within its budget, and the networks where that fails are not exotic - a VPN, a guest wifi,
a hotspot, a subnet wider than the scan. Press the row that lands on the list, type the code, pair. The host is
remembered like any other, so the typing is a one-time thing.
### What is checked, on this machine

`:app:testDebugUnitTest` - five test classes, on this desktop's JVM, with the real Android framework classes:

  - **`SavedHostsTest`** (6): a record written in one start is read back in the next, with the code, the chain,
    the port and the version intact; the same address is updated and not doubled, newest first; the store is
    capped at ten hosts, newest kept; a forgotten host stays forgotten through a restart; a store somebody has
    written junk into is an empty list and not a crash, and is usable again afterwards; and the row a saved host
    prints names the address, the chain, the code and the fact that it is saved.
  - **`SyncViewModelTest`** (5): the three checks the idle-close fix brought, plus two new ones. The pair, the
    close, and a **new view model on the same phone**: the saved host on the list with no scan run, marked
    `saved`, paired from the record against a host standing on the address the record named, a file taken from
    it, every frame compared with the recording the Python host made - and then the host forgotten, with the
    next start showing nothing. The hand-typed host: on the list, paired by typing the code, an empty address
    and a 70000 port said as what they are, and a dead address that says it is dead.
  - **`PlayQueueTest`** (13): shuffle plays five distinct tracks in five plays, and plays no track straight
    after playing it across 41 plays; `Prev` retraces the shuffle order and stops at the front; off-shuffle
    `Next` walks the host's order and stops at the end; the cycle walks `Off -> Once -> Always -> Off` one click
    at a time; a "once" is spent by the track it stopped and an "always" is not; and the words the phone says
    are the words the desktop says, tooltip for tooltip.
  - **`PhonePlayerTest`** (4): the three the first play session brought, plus the boost - `1.30` on the player,
    the factory that carries it actually the one the player was built with, and the sample arithmetic itself:
    16-bit samples scaled and clipped at full scale, 32-bit scaled, an encoding this code does not read handed
    through untouched, and a format that comes out exactly as it went in.

Three things about Media3's audio-processor API look like bugs in this app and are not, all three found the
slow way. **`AudioProcessor.configure()` parks the format in the *pending* pair; `flush()` is what makes it the
format the processor reads while it works** - a player calls flush before it feeds a processor any bytes, and a
check that skips the flush hands the processor `NOT_SET`, and it passes audio through untouched, which is the
right behaviour for a processor that has not been told what it is being fed. **`getOutput()` is a hand-over,
not a peek** - Media3's implementation returns the filled buffer and puts an empty one back in its slot, so a
check takes the output once and reads it from there. And
`DefaultRenderersFactory.buildAudioRenderers` is Java with a `java.util.ArrayList` parameter, which this Kotlin
accepts an override of only with the Java list type named in it - writing `List` compiles as "overrides
nothing", which is the good outcome, because a factory that is silently never called is a player that is
quietly not boosted at all.

### What is not true yet

Nothing in this section has been run on an emulator or a real phone yet. The bar, the remembered hosts and the
boost are checked on this machine, and the emulator has to say what 1.30 does to a real track on a real dial -
starting at the level this all started at, 13 of 15, and going down from there, reading the phone's own stream
with `dumpsys audio` rather than trusting the app's slider.

Clipping is a real risk on a track that is already recorded hot. If it bites, the number to argue with is
`BoostedAudio.GAIN`, and it is in one place on purpose.

`Stop after current` lives in the session. The desktop also persists it across starts; the phone persists the
hosts, not the square. That is an open question, not an oversight.

The phone still has no foreground service, so a pull and playback still stop with the app: a session that is
advancing through tracks stops advancing when the window is backgrounded, and `onStop` pauses the player. A
pull that is interrupted by the app being killed is a pull that starts again. That is the next thing, and the
play bar makes it worth doing - a bar that advances through a list is a bar that wants to keep working when the
phone is in a pocket.








## Run on the emulator - 28 Nov 2026, and what it did and did not say

This section replaces the note above it that said nothing had been run on an emulator.

What ran, on `ytmsd_mvp` (API 36, 48 kHz, the app's own AVD), against the desktop that is running on this
machine at `10.0.2.2:63350`:

- The app was installed from `:app:assembleDebug`, restarted after the emulator was rebooted, and the saved
  host appeared in the list on its own: `10.0.2.2:63350  Other Playlist  code 6767  protocol not named
  saved`. One tap on that row paired it - no scan, no code typed - and the 458-file list came back.
- A row that was already on the phone (`(G)i-dle - HWAA.mp3  7694 KiB  on the phone`) was selected, `PLAY`
  was tapped, and the status line read `Playing.` and stayed there.
- `dumpsys media.audio_flinger` says the mixer thread `AudioOut_D` is out of standby at 48000 Hz,
  `AUDIO_FORMAT_PCM_16_BIT`, 2 channels, while the app plays - which is the phone's own voice saying audio is
  going through it, with the boosted processor in the player's sink.
- The play bar rendered as built: `Shuffle | Prev | Play | Restart | Next | ■ Off`, with `TAKE`/`PLAY`, the
  host fields (`Host IP` and port `63350` with `Add`), `CLEAR` and `FORGET HOST`, and the phone's own volume
  read back as `Volume 10/15`.
- The first emulator run - before the buffer-aliasing fix - died on the player's first buffer with
  `IllegalArgumentException: The source buffer is this buffer`. That is fixed, and it is the reason
  `PhonePlayerTest` now hands the processor the buffer it is holding and asserts the samples come out scaled
  once, not twice.

**What did not get measured: the loudness, in decibels.** The instrument is not on this machine:

- This emulator build has no `-audio-out` option (it answers `unknown option: -audio-out`), so its output
  cannot be recorded to a WAV by the emulator itself.
- `dumpsys media_metrics` - Android's per-player loudness metrics (`shortTermLoudness`, `maximumLoudness`, in
  dBFS/LKFS) - prints nothing on this image: the metrics service is present in `dumpsys -l` and empty.
- The host has no loopback capture device to record what the emulator plays: `ffmpeg -list_devices true -f
  dshow -i dummy` lists microphones only, and no `Stereo Mix`.

So the honest statement is: the 30% is proven at the sample level, and proven to be in the path on a device,
and it has not been measured in decibels on a device. The sample-level proof is `PhonePlayerTest` - 16-bit,
24-bit, 32-bit and float samples scaled by exactly 1.30 and clamped at full scale, the identity-buffer case,
and `isActive()` answering that a gain of 1.00 is not in the path at all. `20 * log10(1.30)` is 2.30 dB, which
is what a measurement should find on the same track at the same dial position, less whatever clipping takes
back.

To measure it, the cheapest route is to enable `Stereo Mix` on this machine (Sound settings → Recording
devices → "Show disabled devices"), then capture while the app plays:

```
ffmpeg -f dshow -i audio="Stereo Mix" -t 30 -ac 2 -ar 48000 -c:a pcm_s16le build_dir_cython\tmp\boost-130.wav
```

Capture the same track at the same volume twice - once with `BoostedAudio.GAIN = 1.30f` and once with `1.00f`
- and read the two files back with `ffprobe`/`ffmpeg`'s `volumedetect` filter (`-af volumedetect`), comparing
`max_level` and `mean_volume`. Same file, same dial, same emulator boot, one rebuild between them.

## The harness in `android/harness` is written again, and it is not wired in

`Main.kt` was lost from disk with the rest of that folder on 28 Nov 2026 - the folder is untracked in git, and
nothing in the repo is tracked that calls it, so there was nothing to restore it from. `Main.kt` and
`Emulator.kt` here are written again from the work the originals did, with the provenance said in each file's
header. They are not complete: `Main.kt` has the commands, the Gradle runner, the report voice, the desktop
gate and the emulator/AVD commands, and it is not compiled, so treat every command in it as unproven.

Two facts about it that matter to anyone using it:

- `android/settings.gradle.kts` includes `:protocol` and `:app` only. `:harness` is not in the build, so
  `android/harness/build.gradle.kts` does nothing today, and a broken harness cannot break an app build.
- The runners that do exist, and are what this session used, are in the gitignored scratch folder:
  `build_dir_cython/android_desktop_suite.ps1` (toolchain, the 39 phone-wire checks, `:protocol:test`, the
  app's Robolectric checks, `:app:assembleDebug`, the desktop gate) and
  `build_dir_cython/android_build.ps1` (the app build, its unit checks, and the counts read out of Gradle's
  own XML). Those scripts are ground truth; the harness is a convenience over the same work.

Last full run of the app's gates on 28 Nov 2026: `:app:check` BUILD SUCCESSFUL - lint clean, 29 Robolectric
checks (5 player, 13 play queue, 6 saved hosts, 5 sync view-model) with 0 failures - and
`:app:assembleDebug` producing `app-debug.apk`, which is the APK measured on the emulator above.

