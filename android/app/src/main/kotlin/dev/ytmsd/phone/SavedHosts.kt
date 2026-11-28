// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The hosts this phone has synced with, kept on the phone. A desktop that has paired with a chain knows that
// chain exists even when it is asleep, and the person opening it expects the same host on the screen the next
// time. A phone that forgets on every start forces a scan - on a network with a firewall, a VPN or a hotspot,
// a scan is the part that fails - so the address, the port, the code and the chain name are written down on a
// successful pair and read back on the next start.
//
// What is stored is what a pair needs to be repeated, and nothing a phone can invent: the code is the one the
// person typed and the host accepted, the chain name is the one the host answered with, the protocol version
// is the one the host named. A record is an invitation to pair again, not a promise that the host is there.
package dev.ytmsd.phone

import android.content.Context
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** One host this app has paired with, as it was written down. */
data class SavedHost(
    val ip: String,
    val port: Int,
    val code: String,
    val chainName: String,
    val protocolVersion: Int?,
    val lastSeen: Long,
) {
    /** The address, in the words a window prints. */
    val address: String get() = "$ip:$port"

    /**
     * The host list's row for this record. It says the host is a remembered one, because a scan answer and a
     * remembered host are the same shape to the window and a person needs to know which one they are pressing.
     */
    fun row(): String = "$address  " +
        chainName.ifEmpty { "no chain named" } +
        "  code $code  protocol " + (protocolVersion ?: "not named") +
        "  saved"
}
/**
 * The phone's own list of hosts it has synced with.
 *
 * `SharedPreferences` is used rather than a file because it is the one store on a phone that is written
 * synchronously and is guaranteed to be there for the next start of the same app, and because a record this
 * small has no reason to need a parser of its own: what goes in is a JSON array of the six facts above, and
 * what comes out of a store somebody has tampered with is an empty list, never a crash.
 */
class SavedHosts(context: Context) {

    private val prefs = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE)

    /** Every remembered host, the newest one first. */
    fun all(): List<SavedHost> = read()

    /**
     * Write a host down. The newest pairing goes first, and an address already written down is updated in
     * place rather than duplicated - a phone that pairs with the same PC forty times a day is a phone with a
     * host list nobody can read - and the list is kept short for the same reason.
     *
     * Returns the list as it now stands, which is what the view model publishes.
     */
    fun remember(host: SavedHost): List<SavedHost> {
        val records = read().toMutableList()
        records.removeAll { it.ip == host.ip && it.port == host.port }
        records.add(0, host)
        write(records.take(MAX_HOSTS))
        return all()
    }

    /**
     * Cross a host off. A host that has moved, been renamed, or stopped hosting its chain is a host a person
     * needs to be able to get rid of, and a record is not a reason to keep asking an address that stopped
     * answering. Returns the list as it now stands.
     */
    fun forget(ip: String, port: Int): List<SavedHost> {
        val records = read().filterNot { it.ip == ip && it.port == port }
        write(records)
        return records
    }

    /** Forget every host, which is what the app's own "start over" means. */
    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    // -- the store ------------------------------------------------------------------------

    private fun read(): List<SavedHost> {
        val text = prefs.getString(KEY, null) ?: return emptyList()
        val parsed = try {
            Json.parseToJsonElement(text)
        } catch (_: Exception) {
            return emptyList()
        }
        val entries = parsed as? JsonArray ?: return emptyList()
        return entries.mapNotNull { entry ->
            val record = entry as? JsonObject ?: return@mapNotNull null
            val ip = text(record["ip"]) ?: return@mapNotNull null
            val port = number(record["port"]) ?: return@mapNotNull null
            SavedHost(
                ip = ip,
                port = port.toInt(),
                code = text(record["code"]).orEmpty(),
                chainName = text(record["chain"]).orEmpty(),
                protocolVersion = number(record["version"])?.toInt(),
                lastSeen = number(record["seen"]) ?: 0L,
            )
        }
    }

    private fun write(records: List<SavedHost>) {
        val array = JsonArray(records.map { host ->
            JsonObject(
                mapOf<String, JsonElement>(
                    "ip" to JsonPrimitive(host.ip),
                    "port" to JsonPrimitive(host.port),
                    "code" to JsonPrimitive(host.code),
                    "chain" to JsonPrimitive(host.chainName),
                    "version" to (host.protocolVersion?.let { JsonPrimitive(it) } ?: JsonNull),
                    "seen" to JsonPrimitive(host.lastSeen),
                ),
            )
        })
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    private fun text(element: JsonElement?): String? =
        (element as? JsonPrimitive)?.takeIf { it.isString }?.content

    private fun number(element: JsonElement?): Long? =
        (element as? JsonPrimitive)?.let { it.content.trim().toLongOrNull() }

    companion object {
        /** The preferences file. Named for the app, so a reset of the app's own settings is a reset of this. */
        const val PREFERENCES = "ytmsd-hosts"

        /** The one key inside it. */
        const val KEY = "hosts"

        /** How many hosts a phone remembers. Ten is more than a person has PCs. */
        const val MAX_HOSTS = 10
    }
}

