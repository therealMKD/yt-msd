// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// Finding a host. `yt_msd.sync.wire.probe_host` and `scan_for_hosts`, with the same rules: a `HELLO` names
// no chain and asks for nothing, ports are asked in port order so the port almost every host answers on is
// asked first, and a search has a budget it stops spending.
package dev.ytmsd.protocol

import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.Socket
import java.util.concurrent.Callable
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** One host's answer, and where it came from. */
data class HostAnswer(val hostIp: String, val port: Int, val reply: JsonObject)

object Lan {

    /**
     * Ask one address on one port "are you a yt-msd, and what do you host there?".
     *
     * Nothing at all is the answer for a closed port, a port answering with something that is not JSON, and a
     * port that says nothing - and those are the common case on a network of any size.
     */
    fun probeHost(hostIp: String, port: Int, syncCode: String = "", protocolVersion: Int? = null,
                  timeoutMs: Int = Protocol.SCAN_CONNECT_TIMEOUT_MS + Protocol.SCAN_READ_TIMEOUT_MS): JsonObject? {
        var socket: Socket? = null
        try {
            socket = Socket()
            socket.connect(InetSocketAddress(hostIp, port), Protocol.SCAN_CONNECT_TIMEOUT_MS)
            socket.soTimeout = timeoutMs
            Frames.write(socket.getOutputStream(), buildJsonObject {
                put("cmd", Protocol.CMD_HELLO)
                if (syncCode.isNotEmpty()) put("sync_code", syncCode)
                if (protocolVersion != null) put(Protocol.VERSION_KEY, protocolVersion)
            })
            return Frames.read(socket.getInputStream())
        } catch (_: Exception) {
            return null
        } finally {
            try {
                socket?.close()
            } catch (_: Exception) {
                // A socket that will not close is a socket that is not ours to keep.
            }
        }
    }

    /**
     * Ask a list of addresses on a list of ports for their `HELLO` answers, in port order.
     *
     * Port order is not a detail: a host takes the first free port upward from [Protocol.SYNC_PORT_START],
     * so almost every host answers on 63350, and asking that port across the whole network first is what puts
     * a host on a screen in the first second rather than the last. [onReply] gets each answer as it arrives.
     */
    fun scanForHosts(targets: List<String>, ports: List<Int>, syncCode: String = "",
                     maxWorkers: Int = Protocol.SCAN_MAX_CONCURRENCY,
                     budgetMs: Long = Protocol.SCAN_BUDGET_MS,
                     onReply: ((HostAnswer) -> Unit)? = null): List<HostAnswer> {
        val bounded = targets.take(Protocol.SCAN_MAX_TARGETS)
        val pairs = ports.sorted().flatMap { port -> bounded.map { it to port } }
        val found = mutableListOf<HostAnswer>()
        if (pairs.isEmpty()) return found
        val pool = Executors.newFixedThreadPool(maxOf(1, minOf(maxWorkers, pairs.size)))
        val started = System.nanoTime()
        try {
            val futures = pairs.map { (target, port) ->
                pool.submit(Callable { probeHost(target, port, syncCode) to (target to port) })
            }
            futures.forEach { future ->
                val remaining = budgetMs - TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started)
                if (remaining <= 0) return@forEach
                val (answer, pair) = try {
                    future.get(remaining, TimeUnit.MILLISECONDS)
                } catch (_: Exception) {
                    null to ("" to 0)
                }
                if (answer != null) {
                    val record = HostAnswer(pair.first, pair.second, answer)
                    found.add(record)
                    onReply?.invoke(record)
                }
            }
            futures.forEach { it.cancel(true) }
        } finally {
            pool.shutdownNow()
        }
        return found
    }

    /** The addresses this machine can be reached on, which is where a phone's search starts. */
    fun localAddresses(): List<String> = try {
        NetworkInterface.getNetworkInterfaces().toList()
            .filter { it.isUp && !it.isLoopback && !it.isVirtual }
            .flatMap { nic -> nic.inetAddresses.toList().filterIsInstance<Inet4Address>() }
            .mapNotNull { it.hostAddress }
    } catch (_: Exception) {
        emptyList()
    }

    /** The /24s a phone is allowed to search: the networks it is on, 254 hosts each, under one budget. */
    fun candidateTargets(maxNetworks: Int = Protocol.SCAN_MAX_NETWORKS): List<String> =
        localAddresses().take(maxNetworks).filter { it.count { c -> c == '.' } == 3 }
            .map { it.substringBeforeLast('.') }
            .flatMap { prefix -> (1..254).map { "$prefix.$it" } }
            .take(Protocol.SCAN_MAX_TARGETS)

    /** What this machine calls itself, which is what the host writes on its card. */
    fun localIp(): String = try {
        InetAddress.getLocalHost().hostAddress
    } catch (_: Exception) {
        localAddresses().firstOrNull() ?: "0.0.0.0"
    }
}
