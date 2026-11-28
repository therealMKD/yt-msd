// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The window. Four things happen on it, in the order the protocol makes them happen: ask what hosts are
// here, pair with one, take a file, hear it. It is deliberately small - a reader of the flows in
// SyncViewModel and a button per step - because a phone screen is where a person reads a status, not
// where a protocol is decided.
//
// It is written with Android views rather than Compose, and the reason is in the version catalog: the
// Kotlin-owned Compose compiler enforces composability at the call site of `Activity.setContent { }`, and
// the artifacts that carry the marker making that legal are not reachable from the compiler this Kotlin
// plugin can name. A list, a code box, a status line and a Media3 player are the same window either way.
package dev.ytmsd.phone

import android.content.Context
import android.graphics.Color
import android.media.AudioManager
import android.os.Bundle
import android.text.InputType
import android.util.TypedValue
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.SeekBar
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.RenderersFactory
import androidx.media3.ui.PlayerView
import dev.ytmsd.protocol.Protocol
import java.io.File
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

/**
 * `ComponentActivity` for what it brings - a view-model store, a lifecycle, a saved-state registry - and a
 * window built in code from framework views, so the app needs no resource files: the manifest's framework
 * theme is the theme.
 */
class MainActivity : ComponentActivity() {

    private val model: SyncViewModel by viewModels()

    private lateinit var player: PhonePlayer
    private lateinit var volume: PhoneVolume
    private var volumeWatch: AutoCloseable? = null
    private var playedWithQuietPhone = false
    private lateinit var statusLine: TextView
    private lateinit var playerLine: TextView
    private lateinit var volumeBar: SeekBar
    private lateinit var volumeLabel: TextView
    private lateinit var codeBox: EditText
    private lateinit var hostIpBox: EditText
    private lateinit var hostPortBox: EditText
    private lateinit var hostList: ListView
    private lateinit var trackList: ListView
    private lateinit var playerView: PlayerView
    private lateinit var hostAdapter: ArrayAdapter<String>
    private lateinit var trackAdapter: ArrayAdapter<String>
    private lateinit var playButton: Button
    private lateinit var prevButton: Button
    private lateinit var nextButton: Button
    private lateinit var restartButton: Button
    private lateinit var shuffleButton: Button
    private lateinit var stopAfterButton: Button

    /** The host's list as a playing session - shuffle, prev/next and stop-after all read this. */
    private var queue = PlayQueue(emptyList())

    /** The track on the player, and the one that ran to its end and is being held for a replay. */
    private var playingTrack: Track? = null
    private var finishedTrack: Track? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        model.init(applicationContext)
        volume = PhoneVolume(this)
        setContentView(buildWindow())
        player = PhonePlayer(this)
        playerView.player = player.exo
        // The player's own reasons for stopping belong on the window's status line. Without this a pull that
        // never landed, a file that is not audio, and a decoder that refused are all the same silent nothing,
        // which is exactly what the first run on the emulator produced.
        player.reportErrors { problem -> playerLine.text = "The player stopped: $problem" }
        // A player that took audio focus and lost it is a player that is sitting there looking ready. Saying
        // which of Playing / Paused / Stopped it is is the difference between a pause and a mystery.
        player.reportState { state ->
            playerLine.text =
                if (playedWithQuietPhone) "$state  (the phone's volume was at 0, so it is at ${volume.quietComfortLevel})"
                else state
        }
        // The play bar's button says what pressing it would do right now - start a stopped track, pause a
        // playing one, start a finished one again from the beginning - which is the desktop's rule for the
        // same button, and the reason it is redrawn from the player's states rather than from our presses.
        player.reportPlayback { state -> paintPlayButton(state) }

        // A track that ran to its end is where "stop after current" and shuffle are decided, exactly as it
        // is on the desktop: this is the only place a session advances itself, and the only place a "once"
        // is spent.
        player.reportFinished { trackFinished() }

        // The bar's buttons say their states from the first frame, so a window never shows a control in a
        // state it is not in.
        paintStopAfter()
        paintShuffle()

        // The phone's volume moves under the hardware keys, a headset, and a system slider. The bar follows.
        volumeWatch = volume.follow { level ->
            volumeBar.progress = level
            volumeLabel.text = volumeWords(level)
        }
        readFlows()
    }

    override fun onStop() {
        super.onStop()
        // Nothing in this app plays in the background yet - that needs a foreground service. Pausing here is
        // the honest half of that: the file stops, the phone is left alone, and Play takes it up again.
        player.pause()
    }

    override fun onDestroy() {
        volumeWatch?.close()
        volumeWatch = null
        playerView.player = null
        player.release()
        super.onDestroy()
    }

    /**
     * The window, built in code: one column of the four steps, in the order they happen.
     *
     * The two lists are weighted children of the column, and the column is the window - **not** inside a
     * `ScrollView`. A `ListView` inside a `ScrollView` is measured with no height limit at all, so it lays out
     * one or two rows and hands the scrolling to the scroll view: that is the "two lines tall" window this app
     * first shipped with. A `ListView` given a share of the screen lays out its own rows, scrolls its own
     * list, and the window stops scrolling at all.
     */
    private fun buildWindow(): View {
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val edge = dp(12)
            setPadding(edge, edge, edge, edge)
        }

        column.addView(TextView(this).apply { text = "yt-msd"; textSize = 20f })

        statusLine = TextView(this).apply {
            text = model.status.value
            textSize = 14f
            setMinLines(2)
        }
        column.addView(statusLine)

        // The player gets its own line. A take and a play can each have something to say at the same moment,
        // and one line telling both stories is a line that says the wrong thing about the thing being watched.
        playerLine = TextView(this).apply {
            text = "Nothing playing."
            textSize = 14f
        }
        column.addView(playerLine)

        val codeRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        codeBox = EditText(this).apply {
            hint = "Sync code"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            setSingleLine()
            textSize = 18f
        }
        codeRow.addView(codeBox, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        codeRow.addView(Button(this).apply {
            text = "Scan"
            setOnClickListener {
                model.scan()
                putKeyboardAway()
            }
        })
        column.addView(codeRow)

        // The host's address, named by hand. A scan asks the networks the phone is standing on, and the
        // networks where that does not work are not rare - a VPN, a guest wifi, a hotspot, a subnet bigger
        // than the scan's budget. The desktop has always let a person name an address, and a phone that
        // cannot is a phone that cannot pair with the machine across the room.
        val hostRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        hostIpBox = EditText(this).apply {
            hint = "Host IP"
            inputType = InputType.TYPE_CLASS_TEXT
            setSingleLine()
            textSize = 16f
        }
        hostPortBox = EditText(this).apply {
            hint = "Port"
            inputType = InputType.TYPE_CLASS_NUMBER
            setSingleLine()
            textSize = 16f
            setText(Protocol.SYNC_PORT_START.toString())
        }
        hostRow.addView(hostIpBox, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hostRow.addView(hostPortBox, LinearLayout.LayoutParams(dp(72), LinearLayout.LayoutParams.WRAP_CONTENT))
        hostRow.addView(fileButton("Add") {
            model.addHost(hostIpBox.text.toString(), hostPortBox.text.toString().toIntOrNull() ?: 0)
            putKeyboardAway()
        })
        column.addView(hostRow)

        hostList = ListView(this)
        hostAdapter = readableRows(android.R.layout.simple_list_item_1)
        hostList.adapter = hostAdapter
        // A host is paired by naming the code the person typed - the code is what the host's `AUTH` answer
        // is checked against, and the chain it hosts is what its `HELLO` named. A saved host is pressed
        // without typing anything: the code it was paired with is on the phone with it, which is the entire
        // point of having written it down.
        hostList.setOnItemClickListener { _, _, position, _ ->
            val card = model.hosts.value.getOrNull(position) ?: return@setOnItemClickListener
            val remembered = model.saved.value.firstOrNull { it.ip == card.ip && it.port == card.port }
            if (remembered != null) model.pairSaved(remembered) else model.pairAndLoad(card, codeBox.text.toString())
            putKeyboardAway()
        }
        column.addView(hostList, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 2f))

        trackList = ListView(this).apply {
            choiceMode = ListView.CHOICE_MODE_SINGLE
        }
        trackAdapter = readableRows(android.R.layout.simple_list_item_activated_1)
        trackList.adapter = trackAdapter
        trackList.setOnItemClickListener { _, _, position, _ -> trackList.setItemChecked(position, true) }
        column.addView(trackList, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 4f))

        val fileRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        fileRow.addView(fileButton("Take") {
            val track = selectedTrack()
            if (track == null) statusLine.text = "Pick a file in the list first." else model.pull(track)
        })
        fileRow.addView(fileButton("Play") {
            val track = selectedTrack()
            if (track == null) playerLine.text = "Pick a file in the list first." else startTrack(track)
        })
        // Pause and Stop are not in this row any more. The bar below has them, in the order the desktop's
        // bar has them, and a phone with two ways to pause a track is a phone with one of them left stale.
        column.addView(fileRow)

        // The play bar: the desktop's controls, in the order a phone screen wants them - shuffle outside
        // left, prev / play-pause / restart / next across the middle, "stop after current" outside right.
        //
        // The captions are words, not the desktop's glyphs. The desktop's bar is drawn with Segoe MDL2
        // Assets codepoints (U+E768 play, U+E769 pause, U+E72C replay, U+E892/E893 prev/next, U+E8B1
        // shuffle), which are private-use codepoints that exist in that Windows font and in no Android
        // font - on a phone they draw empty boxes. The words are the desktop's own: they are what its tray
        // menu uses for the same commands, and each button carries the desktop's tooltip as its own.
        val playBar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        shuffleButton = barButton("Shuffle", "Shuffle Playback (Toggle)") { pressShuffle() }
        prevButton = barButton("Prev", "Previous track") { pressPrevious() }
        playButton = barButton("Play", "Play / Pause") { pressPlayPause() }
        restartButton = barButton("Restart", "Replay - play this track again from the beginning") { pressRestart() }
        nextButton = barButton("Next", "Next track") { pressNext() }
        stopAfterButton = barButton("■ Off", PlaybackWords.stopAfterTooltips.getValue(StopAfter.OFF)) {
            pressStopAfter()
        }
        playBar.addView(shuffleButton, barLayout())
        playBar.addView(prevButton, barLayout())
        playBar.addView(playButton, barLayout(1.2f))
        playBar.addView(restartButton, barLayout(1.2f))
        playBar.addView(nextButton, barLayout())
        playBar.addView(stopAfterButton, barLayout(1.1f))
        column.addView(playBar)

        // The phone's media volume, on a bar in the window. The phone has its own ways to move it - hardware
        // keys, a headset, a system slider - and this bar reads the same stream those move, so it is never a
        // second, disagreeing volume.
        val volumeRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        volumeLabel = TextView(this).apply {
            textSize = 14f
            text = volumeWords(volume.level)
        }
        volumeBar = SeekBar(this).apply {
            max = volume.maxLevel
            progress = volume.level
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(seek: SeekBar, progress: Int, fromUser: Boolean) {
                    if (fromUser) {
                        volume.setLevel(progress)
                        volumeLabel.text = volumeWords(progress)
                    }
                }

                override fun onStartTrackingTouch(seek: SeekBar) = Unit
                override fun onStopTrackingTouch(seek: SeekBar) = Unit
            })
        }
        volumeRow.addView(volumeLabel, LinearLayout.LayoutParams(dp(110), LinearLayout.LayoutParams.WRAP_CONTENT))
        volumeRow.addView(volumeBar, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        // Letting go of the host travels with the volume row, not the file row: five buttons in a row on a
        // phone screen is a row where the last one is unreadable.
        volumeRow.addView(fileButton("Clear") { model.clear() })
        volumeRow.addView(fileButton("Forget host") { model.forgetNewest() })
        column.addView(volumeRow)

        playerView = PlayerView(this).apply {
            useController = true
            visibility = View.GONE
        }
        column.addView(playerView, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(96)))

        // The window is the whole screen, and it is a `FrameLayout` saying so. A column given to the activity's
        // content frame on its own is laid out at its content height: the weighted lists then divide up only
        // what they asked for, the bottom of the screen stays empty, and the volume bar lands in the middle of
        // nothing. A frame that fills the screen is what gives the lists a screen to divide up.
        //
        // The frame is also what takes the insets - the status bar at the top and the navigation bar at the
        // bottom. Laid out without them, the window's bottom row sits *under* the navigation bar, where a tap
        // lands on the system bar and the app never hears it: that is why Take appeared to do nothing.
        val root = FrameLayout(this).apply {
            fitsSystemWindows = true
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT,
            )
            addView(column, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT,
            ))
        }
        return root
    }

    /** Framework list rows, with the text at a size a phone screen is read at. */
    private fun readableRows(layout: Int): ArrayAdapter<String> =
        object : ArrayAdapter<String>(this, layout, mutableListOf<String>()) {
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View =
                (super.getView(position, convertView, parent) as TextView).apply { textSize = 16f }
        }

    /** A button in the file row, at a size five of them fit on a phone screen at. */
    private fun fileButton(label: String, action: () -> Unit): Button =
        Button(this).apply {
            text = label
            textSize = 12f
            setOnClickListener { action() }
        }

    /** A button on the play bar. The bar's buttons are the same size and the same colour by default. */
    private fun barButton(label: String, tooltip: String, action: () -> Unit): Button =
        Button(this).apply {
            text = label
            textSize = 12f
            isAllCaps = false
            tooltipText = tooltip
            contentDescription = tooltip
            setBackgroundColor(BAR_BASE)
            setOnClickListener { action() }
        }

    /** Bar buttons share a row evenly; a bigger weight is how the play button gets the desktop's bigger box. */
    private fun barLayout(weight: Float = 1f): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight)

    /** Put a track on the player from the beginning, and stand the session on it. */
    private fun startTrack(track: Track) {
        val file = model.downloadedFile(track.name)
        // The player is not asked for a file the phone does not have. It used to be, and what came back was
        // a source error two seconds deep in Media3 and a window that said nothing.
        if (!file.exists()) {
            playerLine.text = "${track.name} is not on the phone yet - Take it first."
            return
        }
        playerView.visibility = View.VISIBLE
        queue.select(track.name)
        trackList.setItemChecked(queue.index, true)
        playingTrack = track
        finishedTrack = null
        player.play(file)
        putKeyboardAway()
        // The phone can be muted - its own audio policy ducks and mutes this stream under its own sound - and
        // a file played into a muted phone is a file played into nobody. The note is kept so the state line
        // carries it, because the player's own "Playing." arrives after it and would otherwise wipe the only
        // words explaining why the sound is quiet.
        if (volume.raiseFromMute()) {
            playedWithQuietPhone = true
            playerLine.text =
                "Playing - the phone's volume was at 0, so it is at ${volume.quietComfortLevel} now."
        }
    }

    /**
     * The play bar's middle button. It does what pressing it would do right now, which is the desktop's rule
     * for the same button: start a stopped track, pause a playing one, start a finished one from the top.
     */
    private fun pressPlayPause() {
        val finished = finishedTrack
        if (finished != null) {
            startTrack(finished)
            return
        }
        val current = playingTrack
        if (current == null) {
            val picked = selectedTrack()
            if (picked == null) {
                playerLine.text = PlaybackWords.nothingPlaying
                return
            }
            startTrack(picked)
            return
        }
        // A player let go of by "stop after current" has no media item left: pressing Play there starts the
        // track again rather than asking a stopped player to play nothing.
        if (player.exo.playbackState == Player.STATE_IDLE) {
            startTrack(current)
            return
        }
        if (player.exo.isPlaying) player.pause() else player.exo.playWhenReady = true
    }

    /** The track from the top. The desktop's Replay, on its own button because a phone screen has room. */
    private fun pressRestart() {
        val track = playingTrack
        if (track == null || finishedTrack != null) {
            val picked = track ?: selectedTrack()
            if (picked == null) {
                playerLine.text = PlaybackWords.nothingPlaying
                return
            }
            startTrack(picked)
            return
        }
        player.exo.seekTo(0L)
        player.exo.playWhenReady = true
        playerLine.text = "Restarted ${track.name} from the beginning."
    }
    private fun pressPrevious() {
        val moved = queue.previous()
        if (moved == null) {
            playerLine.text = PlaybackWords.noPrevious
            return
        }
        playAt(moved)
    }

    private fun pressNext() {
        val moved = queue.next()
        if (moved == null) {
            playerLine.text = PlaybackWords.noNext
            return
        }
        playAt(moved)
    }

    private fun playAt(position: Int) {
        val track = model.tracks.value.getOrNull(position) ?: return
        trackList.setItemChecked(position, true)
        startTrack(track)
    }

    private fun pressShuffle() {
        val on = queue.toggleShuffle()
        paintShuffle()
        playerLine.text = if (on) PlaybackWords.shuffleOn else PlaybackWords.shuffleOff
    }

    private fun pressStopAfter() {
        queue.cycleStopAfter()
        paintStopAfter()
        playerLine.text = queue.stopAfterWords()
    }

    /** The shuffle button says "on" the way the desktop's does - a colour, not a caption. */
    private fun paintShuffle() {
        shuffleButton.setBackgroundColor(if (queue.shuffled) Color.parseColor("#1E88E5") else BAR_BASE)
    }

    /**
     * The stop-after button, in its three states.
     *
     * The caption is the desktop's own square with the desktop's own label, and the colours are the
     * desktop's own - grey at off, the amber of "this track is the last one", the red of "every track stops
     * when it ends". A control whose colour is its state is a control that can be read at a glance in a
     * pocket, which is what a phone screen is for.
     */
    private fun paintStopAfter() {
        val state = queue.stopAfter
        stopAfterButton.text = "\u25A0 " + state.label
        stopAfterButton.tooltipText = PlaybackWords.stopAfterTooltips.getValue(state)
        stopAfterButton.setBackgroundColor(
            when (state) {
                StopAfter.OFF -> BAR_BASE
                StopAfter.ONCE -> Color.parseColor("#FF8C00")
                StopAfter.ALWAYS -> Color.parseColor("#E31E24")
            },
        )
    }

    /** The caption and the tooltip that say what pressing the middle button would do. */
    private fun paintPlayButton(state: Playback) {
        playButton.text = when (state) {
            Playback.PLAYING -> "Pause"
            Playback.ENDED -> "Replay"
            Playback.PAUSED, Playback.STOPPED, Playback.GETTING_READY -> "Play"
        }
        playButton.tooltipText =
            if (state == Playback.ENDED) "Replay - play this track again from the beginning" else "Play / Pause"
    }

    /**
     * A file ran to its end. This is where "stop after current" and shuffle live, and it is the same on the
     * desktop: a track ending advances to the next one, stops when the button says to, and spends a "once"
     * on the way.
     */
    private fun trackFinished() {
        val finished = playingTrack ?: return
        finishedTrack = finished
        val armed = queue.stopAfter
        if (queue.shouldStopAfterCurrent()) {
            paintStopAfter()
            playerLine.text = if (armed == StopAfter.ALWAYS) PlaybackWords.stoppedAfterAlways
            else PlaybackWords.stoppedAfterOnce
            player.stop()
            playerView.visibility = View.GONE
            return
        }
        val moved = queue.next()
        if (moved == null) {
            playerLine.text = PlaybackWords.noNext
            return
        }
        val next = model.tracks.value.getOrNull(moved) ?: return
        trackList.setItemChecked(moved, true)
        if (!model.downloadedFile(next.name).exists()) {
            // Advancing onto a track that is not on the phone is not the player failing. It is the end of
            // what this phone can play by itself, and saying so is what keeps a session from looking stuck.
            playerLine.text = "${next.name} is not on the phone yet - Take it first."
            player.stop()
            playerView.visibility = View.GONE
            return
        }
        startTrack(next)
    }

    /** What the bar's buttons are painted with when they have nothing to say. */
    private val BAR_BASE: Int = Color.parseColor("#D8D8D8")



    /**
     * Put the keyboard away. It is needed for one thing in this window - naming the sync code - and it covers
     * half of the screen while it is up, which is exactly the half holding the file list a person is picking
     * from. Leaving it up is also what made the first run on an emulator look like a window with two lines.
     */
    private fun putKeyboardAway() {
        val manager = getSystemService(InputMethodManager::class.java) ?: return
        val view = currentFocus ?: codeBox
        val token = view.windowToken ?: return
        manager.hideSoftInputFromWindow(token, 0)
        codeBox.clearFocus()
    }

    /** The volume in the words the bar shows beside it. A dial at 0 is named, because a 0 is silence. */
    private fun volumeWords(level: Int): String =
        if (level == 0) "Volume 0/${volume.maxLevel} - muted" else "Volume $level/${volume.maxLevel}"

    /** The row picked in the file list, which is all a take or a play needs. */
    private fun selectedTrack(): Track? {
        val position = trackList.checkedItemPosition
        val tracks = model.tracks.value
        if (position < 0 || position >= tracks.size) return null
        return tracks[position]
    }

    /** The window's only job: read the flows the view model publishes, and put them on the screen. */
    private fun readFlows() {
        lifecycleScope.launch {
            model.status.collect { text -> statusLine.text = text }
        }
        lifecycleScope.launch {
            model.hosts.collect { hosts ->
                hostAdapter.clear()
                hostAdapter.addAll(hosts.map { host ->
                    // A saved host is named by its record, because the record carries the chain the host
                    // called itself and the code that paired with it, and a person needs to see that this row
                    // is the machine they paired with before, not a machine the scan just found.
                    val record = model.saved.value.firstOrNull { it.ip == host.ip && it.port == host.port }
                    if (host.saved && record != null) record.row()
                    else host.ip + ":" + host.port + "  " +
                        host.chains.joinToString(", ").ifEmpty { "no chain named" } +
                        "  protocol " + (host.protocolVersion ?: "not named")
                })
            }
        }
        // The file list says what is on the phone as well as what the host named, and the downloaded flow is
        // what changes under a Take, so both flows redraw the same rows.
        val showTracks = {
            val names = model.tracks.value.map { it.name }
            // A new list from a host is a new session, and the track this phone is playing is the one place
            // in it the session is standing. Rebuilding the queue on every refresh and losing where the
            // player is - which is what a naive refresh does - is how a Next lands on a random track.
            if (names != queue.names) {
                val held = playingTrack?.name
                queue = PlayQueue(names).apply { held?.let { select(it) } }
            }
            trackAdapter.clear()
            trackAdapter.addAll(names.mapIndexed { position, name ->
                name + "  " + (model.tracks.value[position].size / 1024) + " KiB" +
                    (if (model.downloadedFile(name).exists()) "  on the phone" else "")
            })
        }
        lifecycleScope.launch { model.tracks.collect { showTracks() } }
        lifecycleScope.launch { model.downloaded.collect { showTracks() } }
    }

    private fun dp(value: Int): Int = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics
    ).toInt()
}

/** What the player is doing, in the states a play bar's button cares about. */
enum class Playback { PLAYING, PAUSED, ENDED, STOPPED, GETTING_READY }

/**
 * The player. A file taken from a chain is played from where it lies on the phone - Media3 reads the local
 * file, so nothing about playback depends on the network, and a file taken in a session two weeks ago plays
 * exactly as one taken a second ago.
 *
 * The audio attributes are the whole reason this class exists rather than being one line. A player built
 * without them plays out on the phone's media stream having never asked the phone for the right to be the one
 * making sound: the phone then ducks it to a quarter of its volume under any other sound, and takes the
 * stream away entirely at the first system sound. That is exactly the music that plays barely audibly, stops
 * when the notification shade comes down, and will not start again - and `handleAudioFocus` is what makes the
 * player ask for the stream, hand it over when the phone takes it, and take it back when the phone offers it.
 *
 * The renderers factory is the other half of why it is not one line: it is where the thirty percent that
 * every track gets before the phone's volume applies is put into the audio path (see [BoostedAudio]).
 */
class PhonePlayer(
    context: Context,
    private val renderers: RenderersFactory = BoostedRenderersFactory(context),
) {

    /** The renderers this player plays with, which is what a check reads. */
    val renderersFactory: RenderersFactory get() = renderers

    /** How much louder a track is than the file on the phone, before the phone's dial does anything. */
    val boost: Float get() = BoostedAudio.GAIN

    val exo: ExoPlayer = ExoPlayer.Builder(context)
        .setRenderersFactory(renderers)
        .setAudioAttributes(
            // Media3's own attributes type, not `android.media.AudioAttributes`: the player takes its own. The
            // usage and content it names are Media3's `C.USAGE_MEDIA` and `C.AUDIO_CONTENT_TYPE_MUSIC`, which are the
            // phone's own `USAGE_MEDIA` and `CONTENT_TYPE_MUSIC` values - the phone's audio policy is what the
            // player is talking to.
            androidx.media3.common.AudioAttributes.Builder()
                .setUsage(androidx.media3.common.C.USAGE_MEDIA)
                .setContentType(androidx.media3.common.C.AUDIO_CONTENT_TYPE_MUSIC)
                .build(),
            /* handleAudioFocus = */ true,
        )
        .build()

    init {
        // A player that plays on into a phone whose headphones just came out plays into nobody.
        exo.setHandleAudioBecomingNoisy(true)
    }

    fun play(file: File) {
        exo.setMediaItem(MediaItem.fromUri(file.toURI().toString()))
        exo.prepare()
        exo.playWhenReady = true
    }

    /** Put the file on hold, with its place kept. The phone's focus loss does this, and Pause does it. */
    fun pause() {
        exo.pause()
    }

    /** Let go of the file and the decoder. Play picks a file up again from the top. */
    fun stop() {
        exo.stop()
    }

    /**
     * Every reason the player stops, in the words Media3 gives. A `Source error` alone is the message the
     * first emulator run produced and taught nothing; the cause underneath it - the file that was not there,
     * the bytes that are not audio, the decoder that refused - is the part a person needs.
     */
    fun reportErrors(report: (String) -> Unit) {
        exo.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                val reason = error.cause?.message ?: error.message ?: "the player refused the file"
                report("${error.errorCodeName} - $reason")
            }
        })
    }

    /**
     * Which state the player is in, in words. A player that lost audio focus is sitting there looking ready
     * and is not playing; without this, a pause, a lost stream, and a finished file are the same silent
     * window, which is the "buggy state" the first emulator run was in.
     *
     * Two callbacks, not one. `onPlaybackStateChanged` says nothing when a Pause is pressed - the player is
     * READY before and READY after, and only its `playWhenReady` moves - so `onPlayWhenReadyChanged` is the
     * one that can say "Paused", and it is also the one that names the reason the phone took the sound away.
     */
    fun reportState(report: (String) -> Unit) {
        exo.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                report(
                    when (state) {
                        Player.STATE_IDLE -> "The player is stopped."
                        Player.STATE_BUFFERING -> "The player is getting ready."
                        Player.STATE_ENDED -> "The file has finished."
                        else -> playingOrPaused(exo.playWhenReady)
                    }
                )
            }

            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                report(playingOrPaused(playWhenReady) + " " + reasonWords(reason))
            }
        })
    }

    /**
     * Which of the states a play bar cares about the player is in.
     *
     * The bar's middle button says what pressing it would do, so it has to be told when the player starts,
     * pauses, finishes, and stops - the same four facts the desktop's `_update_play_button` is called for.
     * Both callbacks again, for the same reason [reportState] uses both: a Pause moves only
     * `playWhenReady`, and a finished file moves only the playback state.
     */
    fun reportPlayback(report: (Playback) -> Unit) {
        exo.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                report(classify(state, exo.playWhenReady))
            }

            override fun onPlayWhenReadyChanged(playWhenReady: Boolean, reason: Int) {
                report(classify(exo.playbackState, playWhenReady))
            }
        })
    }

    /**
     * The one fact a playing session runs on: a file ran to its end.
     *
     * Advancing to the next track, stopping because "stop after current" is armed, and spending a "once" are
     * all decided by whoever is watching for this. A phone that never hears it is a phone whose session stops
     * after the first track and calls that playing.
     */
    fun reportFinished(report: () -> Unit) {
        exo.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) report()
            }
        })
    }

    private fun classify(state: Int, playing: Boolean): Playback = when (state) {
        Player.STATE_IDLE -> Playback.STOPPED
        Player.STATE_BUFFERING -> Playback.GETTING_READY
        Player.STATE_ENDED -> Playback.ENDED
        else -> if (playing) Playback.PLAYING else Playback.PAUSED
    }

    private fun playingOrPaused(playing: Boolean): String = if (playing) "Playing." else "Paused."

    /**
     * The phone's own reason for taking the sound away, in the words a person reads on a phone screen.
     *
     * Three named reasons and a number. Media3 1.5.1 names `AUDIO_FOCUS_LOSS`, `AUDIO_BECOMING_NOISY` and
     * `REMOTE` on `Player`; the reasons the older Android media library named (`USER_PRESENT`, `MUTED`) and
     * the suppression reason a later Media3 names are not in the version this app compiles against, so an
     * unrecognised reason says its number rather than a story.
     */
    private fun reasonWords(reason: Int): String =
        when (reason) {
            1 -> "You pressed Pause." // C.PLAY_WHEN_READY_CHANGE_REASON_USER - the phone says the press came from us
            Player.PLAY_WHEN_READY_CHANGE_REASON_AUDIO_FOCUS_LOSS ->
                "The phone took the sound away - something else is playing."
            Player.PLAY_WHEN_READY_CHANGE_REASON_AUDIO_BECOMING_NOISY ->
                "The phone took the sound away because nothing is plugged into it."
            Player.PLAY_WHEN_READY_CHANGE_REASON_REMOTE -> "Something outside the app asked for this."
            else -> "The phone paused it (reason $reason)."
        }

    fun release() {
        exo.release()
    }
}

