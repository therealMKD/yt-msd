// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.protocol).
//
// Reading a frame's facts the way the Python host reads them: with a fallback, because a frame from a
// machine this program has never talked to is a frame that can hold anything, and a phone that throws when
// a host puts text where a size belongs is a phone that crashes on a machine it was meant to report on.
package dev.ytmsd.protocol

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.put

/** The frame parser. Lenient about the things a host is allowed to be lenient about. */
val PhoneJson: Json = Json {
    ignoreUnknownKeys = true
    isLenient = true
    encodeDefaults = true
    explicitNulls = true
}

object NumberRead {

    /** A whole number, or null when this is not one. A boolean is not a number, which is what the Python
     *  host does with `True` where a version belongs, and this agrees with it. */
    fun whole(element: JsonElement?): Int? = real(element)?.let {
        if (it.isNaN() || it.isInfinite()) null else it.toInt()
    }

    /** A whole number that may be big: a file size, a timestamp. */
    fun long(element: JsonElement?): Long? = real(element)?.let {
        if (it.isNaN() || it.isInfinite()) null else it.toLong()
    }

    /** A number that may have a fractional part: an index entry's mtime. */
    fun real(element: JsonElement?): Double? {
        val primitive = element as? JsonPrimitive ?: return null
        if (primitive.booleanOrNull != null) return null
        if (primitive.isString) return primitive.content.toDoubleOrNull()
        return primitive.doubleOrNull
    }
}

/** Reading the fields of a frame. Every one of these has a fallback and none of them throw. */
object FrameRead {

    fun status(frame: JsonElement?): String = text(frame, "status")

    fun reason(frame: JsonElement?): String = text(frame, "reason")

    fun command(frame: JsonElement?): String = text(frame, "cmd")

    fun type(frame: JsonElement?): String = text(frame, "type")

    fun text(frame: JsonElement?, key: String, fallback: String = ""): String {
        val primitive = (frame as? JsonObject)?.get(key) as? JsonPrimitive ?: return fallback
        return if (primitive.isString) primitive.content else primitive.content
    }

    fun int(frame: JsonElement?, key: String, fallback: Int = 0): Int =
        NumberRead.whole((frame as? JsonObject)?.get(key)) ?: fallback

    fun long(frame: JsonElement?, key: String, fallback: Long = 0L): Long =
        NumberRead.long((frame as? JsonObject)?.get(key)) ?: fallback

    fun real(frame: JsonElement?, key: String, fallback: Double = 0.0): Double =
        NumberRead.real((frame as? JsonObject)?.get(key)) ?: fallback

    /** A list of frames under a key - an index, a chain list. Absent is an empty list. */
    fun array(frame: JsonElement?, key: String): JsonArray =
        (frame as? JsonObject)?.get(key) as? JsonArray ?: JsonArray(emptyList())

    /** The strings under a key: the names a host says it wants. */
    fun names(frame: JsonElement?, key: String): List<String> =
        array(frame, key).mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content }

    /** The object under a key: a host's settings, a chain description. */
    fun obj(frame: JsonElement?, key: String): JsonObject? = (frame as? JsonObject)?.get(key) as? JsonObject
}

/** Building the frames a client sends. */
object FrameWrite {

    fun string(text: String): JsonElement = JsonPrimitive(text)

    /** This frame, with this machine's protocol version named on it. A copy, never the caller's object. */
    fun withProtocolVersion(frame: JsonObject): JsonObject =
        JsonObject(frame + (Protocol.VERSION_KEY to JsonPrimitive(Protocol.VERSION)))

    /** One row of a file index, in the six facts a host judges a file by. */
    fun indexEntry(name: String, size: Long, mtimeSeconds: Double, sha256: String,
                   artist: String?, title: String?): JsonObject = buildJsonObject {
        put("name", name)
        put("size", size)
        put("mtime", mtimeSeconds)
        put("sha256", sha256)
        put("artist", artist)
        put("title", title)
    }

    val empty: JsonObject = JsonObject(emptyMap())
}

/**
 * Comparing two parsed frames the way Python compares the dicts it parsed: same keys, same values, in any
 * order, and a number equal to the same number written a different way.
 *
 * kotlinx-serialization compares the *text* of a number, so `1.7E9` - how a JVM prints it - and
 * `1700000000.0` - how Python prints it - are the same value and compare unequal. [equal] is the comparison
 * the acceptance checks use, and [describe] is how a failing check prints what it found.
 */
object JsonCompat {

    fun equal(first: JsonElement?, second: JsonElement?): Boolean {
        if (first == null && second == null) return true
        if (first == null || second == null) return false
        if (first is JsonNull || second is JsonNull) return first is JsonNull && second is JsonNull
        if (first is JsonObject && second is JsonObject) {
            if (first.size != second.size) return false
            first.forEach { (key, value) ->
                if (!second.containsKey(key)) return false
                if (!equal(value, second[key])) return false
            }
            return true
        }
        if (first is JsonArray && second is JsonArray) {
            if (first.size != second.size) return false
            for (index in first.indices) if (!equal(first[index], second[index])) return false
            return true
        }
        if (first is JsonPrimitive && second is JsonPrimitive) {
            // A string is a string: Python compares `"1"` and `1` as unequal, and a phone that read the
            // first as the second would answer a host's `filesize` promise with text.
            if (first.isString != second.isString) return false
            if (first.isString) return first.content == second.content
            val leftNumber = NumberRead.real(first)
            val rightNumber = NumberRead.real(second)
            if (leftNumber != null && rightNumber != null) return leftNumber == rightNumber
            return first.content == second.content
        }
        return false
    }

    /** The first frame that is not the frame the recording says should be there, in words. */
    fun firstDifference(expected: List<JsonElement>, actual: List<JsonElement>): String? {
        if (expected.size != actual.size) {
            return "frame count: ${expected.size} recorded, ${actual.size} spoken"
        }
        expected.forEachIndexed { index, wanted ->
            if (!equal(wanted, actual[index])) {
                return "frame ${index + 1}:\n  recorded ${describe(wanted)}\n  spoken     ${describe(actual[index])}"
            }
        }
        return null
    }

    /** A frame written the way the recording writes it: sorted keys, two-space indent. */
    fun describe(element: JsonElement?): String =
        if (element == null) "null" else buildString { writeCanonical(element, 0) }

    private fun StringBuilder.writeCanonical(element: JsonElement, depth: Int) {
        when (element) {
            is JsonObject -> {
                if (element.isEmpty()) { append("{}"); return }
                append("{\n")
                element.toSortedMap().forEach { (key, value) ->
                    repeat(depth + 1) { append("  ") }
                    append('"').append(key).append("\": ")
                    writeCanonical(value, depth + 1)
                    append(",\n")
                }
                setLength(length - 2)
                append('\n')
                repeat(depth) { append("  ") }
                append('}')
            }
            is JsonArray -> {
                if (element.isEmpty()) { append("[]"); return }
                append("[\n")
                element.forEach { value ->
                    repeat(depth + 1) { append("  ") }
                    writeCanonical(value, depth + 1)
                    append(",\n")
                }
                setLength(length - 2)
                append('\n')
                repeat(depth) { append("  ") }
                append(']')
            }
            is JsonPrimitive -> append(if (element.isString) "\"${element.content}\"" else element.content)
            JsonNull -> append("null")
        }
    }
}

