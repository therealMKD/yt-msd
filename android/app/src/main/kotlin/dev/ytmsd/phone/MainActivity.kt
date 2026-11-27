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
import android.os.Bundle
import android.text.InputType
import android.util.TypedValue
import android.view.View
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
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
    private lateinit var statusLine: TextView
    private lateinit var codeBox: EditText
    private lateinit var hostList: ListView
    private lateinit var trackList: ListView
    private lateinit var playerView: PlayerView
    private lateinit var hostAdapter: ArrayAdapter<String>
    private lateinit var trackAdapter: ArrayAdapter<String>

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        model.init(applicationContext)
        player = PhonePlayer(this)
        setContentView(buildWindow())
        readFlows()
    }

    override fun onDestroy() {
        player.release()
        super.onDestroy()
    }

    /** The window, built in code: one column of the four steps, in the order they happen. */
    private fun buildWindow(): View {
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val edge = dp(14)
            setPadding(edge, edge, edge, edge)
        }

        column.addView(TextView(this).apply { text = "yt-msd"; textSize = 20f })

        statusLine = TextView(this).apply {
            text = model.status.value
            textSize = 14f
        }
        column.addView(statusLine)

        val codeRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        codeBox = EditText(this).apply {
            hint = "Sync code"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            setSingleLine()
        }
        codeRow.addView(codeBox, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        codeRow.addView(Button(this).apply {
            text = "Scan"
            setOnClickListener { model.scan() }
        })
        column.addView(codeRow)

        hostList = ListView(this)
        hostAdapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, mutableListOf<String>())
        hostList.adapter = hostAdapter
        // A host is paired by naming the code the person typed - the code is what the host's `AUTH` answer
        // is checked against, and the chain it hosts is what its `HELLO` named.
        hostList.setOnItemClickListener { _, _, position, _ ->
            model.pairAndLoad(model.hosts.value[position], codeBox.text.toString())
        }
        column.addView(hostList, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))

        trackList = ListView(this).apply {
            choiceMode = ListView.CHOICE_MODE_SINGLE
        }
        trackAdapter = ArrayAdapter(this, android.R.layout.simple_list_item_single_choice, mutableListOf<String>())
        trackList.adapter = trackAdapter
        trackList.setOnItemClickListener { _, _, position, _ -> trackList.setItemChecked(position, true) }
        column.addView(trackList, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))

        val fileRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        fileRow.addView(Button(this).apply {
            text = "Take"
            setOnClickListener { selectedTrack()?.let { model.pull(it) } }
        })
        fileRow.addView(Button(this).apply {
            text = "Play"
            setOnClickListener {
                selectedTrack()?.let { track ->
                    player.play(model.downloadedFile(track.name))
                    playerView.visibility = View.VISIBLE
                }
            }
        })
        column.addView(fileRow)

        playerView = PlayerView(this).apply {
            player = this@MainActivity.player.exo
            visibility = View.GONE
        }
        column.addView(playerView, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(120)))

        return ScrollView(this).apply { addView(column) }
    }

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
                    host.ip + ":" + host.port + "  " +
                        host.chains.joinToString(", ").ifEmpty { "no chain named" } +
                        "  protocol " + (host.protocolVersion ?: "not named")
                })
            }
        }
        // The file list says what is on the phone as well as what the host named, and the downloaded flow is
        // what changes under a Take, so both flows redraw the same rows.
        val showTracks = {
            trackAdapter.clear()
            trackAdapter.addAll(model.tracks.value.map { track ->
                track.name + "  " + (track.size / 1024) + " KiB" +
                    (if (model.downloadedFile(track.name).exists()) "  on the phone" else "")
            })
        }
        lifecycleScope.launch { model.tracks.collect { showTracks() } }
        lifecycleScope.launch { model.downloaded.collect { showTracks() } }
    }

    private fun dp(value: Int): Int = TypedValue.applyDimension(
        TypedValue.COMPLEX_UNIT_DIP, value.toFloat(), resources.displayMetrics
    ).toInt()
}

/**
 * The player. A file taken from a chain is played from where it lies on the phone - Media3 reads the local
 * file, so nothing about playback depends on the network, and a file taken in a session two weeks ago plays
 * exactly as one taken a second ago.
 */
class PhonePlayer(context: Context) {

    val exo: ExoPlayer = ExoPlayer.Builder(context).build()

    fun play(file: File) {
        exo.setMediaItem(MediaItem.fromUri(file.toURI().toString()))
        exo.prepare()
        exo.playWhenReady = true
    }

    fun release() {
        exo.release()
    }
}

