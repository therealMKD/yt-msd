// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// What the phone knows about a host and what it is doing about it. Every decision a phone makes - which
// address to ask, which chain to name, which file to take - lives here in plain Kotlin, and no Compose
// exists in this file: the window is a small reader of these flows, and this is the part testable without
// a window.
package dev.ytmsd.phone

import android.content.Context
import android.util.Log
import dev.ytmsd.protocol.FrameRead
import dev.ytmsd.protocol.HostAnswer
import dev.ytmsd.protocol.Lan
import dev.ytmsd.protocol.Protocol
import dev.ytmsd.protocol.WireClient
import java.io.File
import java.util.concurrent.Executors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.JsonObject
import androidx.lifecycle.ViewModel

/** A host that answered a `HELLO`, as the phone read it. */
data class HostCard(val ip: String, val port: Int, val chains: List<String>, val protocolVersion: Int?)

/** One row of the host's file list, as the `GET_INDEX` answer named it. */
data class Track(val name: String, val size: Long, val sha256: String)

class SyncViewModel : ViewModel() {

    private val work = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "yt-msd-phone").apply { isDaemon = true }
    }

    private val _hosts = MutableStateFlow<List<HostCard>>(emptyList())
    val hosts: StateFlow<List<HostCard>> = _hosts.asStateFlow()

    private val _status = MutableStateFlow("Nothing asked yet.")
    val status: StateFlow<String> = _status.asStateFlow()

    private val _tracks = MutableStateFlow<List<Track>>(emptyList())
    val tracks: StateFlow<List<Track>> = _tracks.asStateFlow()

    private val _downloaded = MutableStateFlow<List<File>>(emptyList())
    val downloaded: StateFlow<List<File>> = _downloaded.asStateFlow()

    private var storage = File(".")
    private var client: WireClient? = null

    fun init(context: Context) {
        storage = File(context.filesDir, "yt-msd").apply { mkdirs() }
    }

    /**
     * Ask a list of addresses on a list of ports for their `HELLO` answers, in port order, and put each host
     * on the list as it answers. The addresses a phone searches are the networks it is standing on, under the
     * same budget the desktop search spends.
     */
    fun scan(
        targets: List<String> = Lan.candidateTargets(),
        ports: List<Int> = listOf(Protocol.SYNC_PORT_START),
    ) {
        _status.value = "Asking ${targets.size} addresses on ${ports.joinToString()} ..."
        _hosts.value = emptyList()
        work.submit {
            val found = Lan.scanForHosts(targets, ports, onReply = { answer ->
                _hosts.value = _hosts.value + cardFor(answer)
                _status.value = "${_hosts.value.size} host(s) answered."
            })
            _status.value = if (found.isEmpty()) {
                "Nothing answered on ${ports.joinToString()}. Check that the phone and the PC are on the " +
                    "same network, that the PC's firewall allows yt-msd, and that the PC is hosting a chain."
            } else {
                "${found.size} host(s) answered."
            }
            Log.i("ytmsd", "scan: ${found.size} answer(s) across ${targets.size} addresses on " +
                ports.joinToString() + " - " + found.joinToString { it.hostIp + ":" + it.port })
        }
    }


    private fun cardFor(answer: HostAnswer): HostCard = HostCard(
        ip = answer.hostIp,
        port = answer.port,
        // A host answers a `HELLO` with the chains it hosts as `{sync_code, name, visible}` - the shape
        // `yt_msd.sync.host.hello_reply` writes. The two older keys are kept as fallbacks because a phone
        // pairs with hosts older than it.
        chains = FrameRead.array(answer.reply, "chains").mapNotNull { entry ->
            (entry as? JsonObject)?.let { FrameRead.text(it, "name") }
        }.ifEmpty { FrameRead.names(answer.reply, "chain_names") }
            .ifEmpty { listOf(FrameRead.text(answer.reply, "chain_name")) }
            .filter { it.isNotEmpty() },
        protocolVersion = Protocol.answeredProtocolVersion(answer.reply),
    )

    /**
     * Pair with a host and read its list: `AUTH` then `GET_INDEX`, and nothing else.
     *
     * [clientIp] is the address the phone puts on its `AUTH` - the address the host sees it at. The window
     * leaves it as the machine's own, and a check that replays a recorded session names the address that
     * session was recorded from, which is the only way the two AUTH frames can be the same frame.
     */
    fun pairAndLoad(card: HostCard, syncCode: String, clientIp: String = Lan.localIp()) {
        _status.value = "Pairing with ${card.ip}:${card.port} ..."
        work.submit {
            client?.close()
            val phone = WireClient(card.ip, card.port, syncCode, clientIp)
            try {
                phone.connect()
                val answer = phone.authenticate()
                if (FrameRead.status(answer) != Protocol.STATUS_OK) {
                    _status.value = "The host refused: " +
                        FrameRead.reason(answer).ifEmpty { "the host refused without a reason" }
                    return@submit
                }
                val refusal = Protocol.versionRefusalFor(answer)
                if (refusal != null) {
                    _status.value = refusal
                    return@submit
                }
                val (files, indexError) = phone.index()
                if (indexError.isNotEmpty()) {
                    _status.value = "The host's list did not arrive: $indexError"
                    return@submit
                }
                client = phone
                _tracks.value = files.map { row ->
                    Track(
                        FrameRead.text(row, "name"),
                        FrameRead.long(row, "size", 0L),
                        FrameRead.text(row, "sha256"),
                    )
                }
                _status.value = "${_tracks.value.size} file(s) from ${phone.chainName} at ${card.ip}:${card.port}."
                Log.i("ytmsd", "paired with ${card.ip}:${card.port} chain ${phone.chainName}: " +
                    "${_tracks.value.size} file(s)")
                // The list is on the screen and a person is reading it, and the host is reading its next command
                // with a 30-second timeout. This is the gap the protocol says a client keeps warm with a PING;
                // a phone that leaves it cold finds its connection closed and every ask after it answered by
                // nothing at all.
                phone.startWarm()
            } catch (problem: Exception) {
                _status.value = "The host at ${card.ip}:${card.port} could not be reached: ${problem.message}"
                Log.w("ytmsd", "pairing with ${card.ip}:${card.port} failed: ${problem.message}")
            }
        }
    }

    /** Take one file into the app's own folder - and only when every byte hashes to what the host promised. */
    fun pull(track: Track) {
        val phone = client
        if (phone == null) {
            // Saying nothing here is what made the first run on a phone look like a take that never happened.
            _status.value = "Pair with a host first - there is no connection to take a file from."
            return
        }
        _status.value = "Taking ${track.name} ..."
        work.submit {
            // The pings come away before the ask and go back after it: a PING in the middle of a file transfer
            // is bytes the host reads as its next frame.
            phone.stopWarm()
            try {
                val result = phone.pull(track.name, File(storage, track.name))
                _status.value = result.note + lostHostWords(phone)
                Log.i("ytmsd", "pull ${track.name}: ok=" + result.ok + " " + result.note)
                if (result.ok) {
                    _downloaded.value = _downloaded.value + File(storage, track.name)
                }
            } catch (problem: Exception) {
                // A take that threw and said nothing is a window that says "Taking ..." forever, which is what
                // a phone does the second time it asks a host that has already hung up on it.
                _status.value = "The take of ${track.name} stopped: ${problem.message} " +
                    lostHostWords(phone).ifEmpty { "Try it again, and pair with the host if it stops again." }
                Log.w("ytmsd", "pull ${track.name} stopped: ${problem.message}")
            } finally {
                if (phone.isConnected) phone.startWarm()
            }
        }
    }

    /** The words to add when the host has this connection no longer, which is what a phone cannot see itself. */
    private fun lostHostWords(phone: WireClient): String =
        if (phone.isConnected) "" else " The host closed this connection - pair with it again."

    /** The pings sent to keep this connection warm, which is what a check reads. */
    fun warmPings(): Long = client?.warmPings ?: 0L

    /** Where a pulled file lives, which is what the player is given. */
    fun downloadedFile(name: String): File = File(storage, name)

    /** Put the window back to the state it was in before a host was asked for anything. */
    fun clear() {
        client?.close()
        client = null
        _hosts.value = emptyList()
        _tracks.value = emptyList()
        _downloaded.value = emptyList()
        _status.value = "Nothing asked yet."
    }

    override fun onCleared() {
        client?.close()
        work.shutdownNow()
    }
}
