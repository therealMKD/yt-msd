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

/** A host that answered a `HELLO`, as the phone read it. [saved] says it is a host this app paired with
 *  before, which is a fact the window has to show: a scan answer and a remembered host are pressed
 *  differently, because a remembered host already has the code the pair needs. */
data class HostCard(
    val ip: String,
    val port: Int,
    val chains: List<String>,
    val protocolVersion: Int?,
    val saved: Boolean = false,
)

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

    private val _saved = MutableStateFlow<List<SavedHost>>(emptyList())
    val saved: StateFlow<List<SavedHost>> = _saved.asStateFlow()

    private var storage = File(".")
    private var store: SavedHosts? = null
    private var client: WireClient? = null

    /**
     * Where the app keeps its files, and who it has synced with before.
     *
     * The saved hosts go on the screen as the window starts, the way the desktop's own chain list is on the
     * screen the moment a desktop starts: a host this app has paired with is available before any scanning,
     * and pressing it pairs with the code that pair used. The files already taken are listed too, because a
     * track that is on the phone plays the moment the app opens, and a window that said "Nothing asked yet"
     * about a phone with forty files on it would be a window lying about what it can do.
     */
    fun init(context: Context) {
        storage = File(context.filesDir, "yt-msd").apply { mkdirs() }
        store = SavedHosts(context)
        _saved.value = store!!.all()
        _hosts.value = savedCards()
        _downloaded.value = storage.listFiles()?.filter { it.isFile }?.sortedBy { it.name }.orEmpty()
        _status.value = when {
            _saved.value.isNotEmpty() && _downloaded.value.isNotEmpty() ->
                "${_saved.value.size} saved host(s), and ${_downloaded.value.size} file(s) on the phone. " +
                    "Press a host to pair with it again."
            _saved.value.isNotEmpty() ->
                "${_saved.value.size} saved host(s). Press one to pair with it again."
            _downloaded.value.isNotEmpty() ->
                "${_downloaded.value.size} file(s) on the phone. Scan or add a host to take more."
            else -> "Nothing asked yet."
        }
    }

    private fun savedCards(): List<HostCard> = _saved.value.map { host ->
        HostCard(
            ip = host.ip,
            port = host.port,
            chains = listOf(host.chainName).filter { it.isNotEmpty() },
            protocolVersion = host.protocolVersion,
            saved = true,
        )
    }
    /**
     * Ask a list of addresses on a list of ports for their `HELLO` answers, in port order, and put each host
     * on the list as it answers. The addresses a phone searches are the networks it is standing on, under the
     * same budget the desktop search spends.
     *
     * The saved hosts stay on the list. A scan is a question about the network, and a host this app has
     * synced with is not a fact about the network: a person does not lose a host because they pressed Scan,
     * and the reason a phone remembers hosts at all is the networks where a scan finds nothing.
     */
    fun scan(
        targets: List<String> = Lan.candidateTargets(),
        ports: List<Int> = listOf(Protocol.SYNC_PORT_START),
    ) {
        _status.value = "Asking ${targets.size} addresses on ${ports.joinToString()} ..."
        _hosts.value = savedCards()
        work.submit {
            val found = Lan.scanForHosts(targets, ports, onReply = { answer ->
                _hosts.value = withCard(_hosts.value, cardFor(answer))
                _status.value = "${_hosts.value.size} host(s) on the list."
            })
            _status.value = if (found.isEmpty()) {
                "Nothing answered on ${ports.joinToString()}. Check that the phone and the PC are on the " +
                    "same network, that the PC's firewall allows yt-msd, and that the PC is hosting a chain." +
                    if (_saved.value.isNotEmpty()) " Your saved hosts are still in the list." else ""
            } else {
                "${found.size} host(s) answered."
            }
            Log.i("ytmsd", "scan: ${found.size} answer(s) across ${targets.size} addresses on " +
                ports.joinToString() + " - " + found.joinToString { it.hostIp + ":" + it.port })
        }
    }

    /**
     * Put an address on the host list without asking it anything.
     *
     * A scan asks the networks the phone is standing on, within its own budget. A phone behind a VPN, on a
     * hotspot with no broadcast, on a guest network, or on a subnet bigger than the scan is a phone that can
     * know an address and still not reach it by scanning - and the desktop has always let a person name an
     * address. A hand-added host is paired by pressing it with the code typed in the box, and it is
     * remembered the moment it pairs, so the next start does not need the typing again.
     */
    fun addHost(ip: String, port: Int = Protocol.SYNC_PORT_START) {
        val address = ip.trim()
        if (address.isEmpty()) {
            _status.value = "Type the host's address first - an IP like 192.168.1.20, or a machine name."
            return
        }
        if (port !in 1..65535) {
            _status.value = "$port is not a port number. A host's port is the number beside its address."
            return
        }
        _hosts.value = withCard(_hosts.value, HostCard(address, port, emptyList(), null))
        _status.value = "$address:$port is on the list - type the code and press it to pair."
    }

    /** One more host on the list, where an address already on it is replaced rather than doubled. */
    private fun withCard(cards: List<HostCard>, card: HostCard): List<HostCard> =
        cards.filterNot { it.ip == card.ip && it.port == card.port } + card



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
                remember(card, syncCode, phone.chainName, phone.hostProtocolVersion)
                _status.value = "${_tracks.value.size} file(s) from ${phone.chainName} at ${card.ip}:${card.port}" +
                    (if (card.saved) " - the saved host answered." else " - this host is saved for next time.")
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

    /**
     * Pair with a host this app paired with before, using the code that pair used.
     *
     * This is the whole point of remembering a host: a person presses the host that is already on the screen
     * and gets its list, with no scan and no typing. The address, the port, the code and the chain name are
     * the ones the host itself answered with last time, so nothing here is guessed - and if the host has
     * moved, this fails the way a pair against an address that moved fails, with the phone saying so.
     */
    fun pairSaved(host: SavedHost, clientIp: String = Lan.localIp()) {
        pairAndLoad(
            HostCard(
                ip = host.ip,
                port = host.port,
                chains = listOf(host.chainName).filter { it.isNotEmpty() },
                protocolVersion = host.protocolVersion,
                saved = true,
            ),
            host.code,
            clientIp,
        )
    }

    /** Write down the host a successful pair just landed on. The store is the phone's, not this class's. */
    private fun remember(card: HostCard, syncCode: String, chainName: String, version: Int?) {
        val store = store ?: return
        _saved.value = store.remember(
            SavedHost(
                ip = card.ip,
                port = card.port,
                code = syncCode,
                chainName = chainName.ifEmpty { card.chains.firstOrNull().orEmpty() },
                protocolVersion = version ?: card.protocolVersion,
                lastSeen = System.currentTimeMillis(),
            ),
        )
        _hosts.value = _hosts.value.map { if (it.ip == card.ip && it.port == card.port) it.copy(saved = true) else it }
    }

    /**
     * Cross a host off the phone's list. A host that has moved or stopped hosting is a host a person should
     * be able to get rid of, and a record is not a reason to keep pressing an address that stopped answering.
     * A connection to the host being forgotten goes with it.
     */
    fun forgetSaved(host: SavedHost) {
        val store = store ?: return
        _saved.value = store.forget(host.ip, host.port)
        _hosts.value = savedCards() + _hosts.value.filterNot { it.ip == host.ip && it.port == host.port }
        if (client?.hostIp == host.ip && client?.port == host.port) {
            client?.close()
            client = null
        }
        _status.value = "$host.address is forgotten. " +
            "Take it off the phone's player first if you want the files gone too."
    }

    /** Forget the host a pair would land on - the newest saved one, which is the one at the top of the list. */
    fun forgetNewest() {
        val newest = _saved.value.firstOrNull()
        if (newest == null) {
            _status.value = "There is no saved host to forget."
            return
        }
        forgetSaved(newest)
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

    /**
     * Put the window back to the state it was in before a host was asked for anything.
     *
     * The saved hosts stay. "Clear" is letting go of *this* host, and a phone that forgot every host it has
     * ever synced with because a person pressed a button labelled Clear is a phone that lost the thing this
     * class exists to keep.
     */
    fun clear() {
        client?.close()
        client = null
        _hosts.value = savedCards()
        _tracks.value = emptyList()
        _downloaded.value = storage.listFiles()?.filter { it.isFile }?.sortedBy { it.name }.orEmpty()
        _status.value = if (_saved.value.isEmpty()) {
            "Not paired. Scan, or add a host by hand."
        } else {
            "Not paired. ${_saved.value.size} saved host(s) are in the list."
        }
    }

    override fun onCleared() {
        client?.close()
        work.shutdownNow()
    }
}
