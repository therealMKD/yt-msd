// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// Which track plays next, and what "next" means. The desktop has had this for as long as it has played
// playlists: a shuffle that picks out of the tracks not played yet, a Previous that walks back through the
// order shuffle made, and a "stop after current" button with three states. This is the same behaviour, in
// plain Kotlin, with no Android and no player in it, so the rules can be checked without a phone - and so the
// window is a reader of these rules rather than the place they live.
//
// The words are the desktop's own words (`set_stop_after_current` and `_finish_stop_after_current` in
// `yt_msd_gui.pyx`): a phone that says something else about the same control is two programs describing one
// control differently, which is how a manual and a support answer stop agreeing.
package dev.ytmsd.phone

import kotlin.random.Random

/**
 * "Stop after current", cycled one click at a time - the same three states the desktop's
 * `STOP_AFTER_OFF` / `STOP_AFTER_ONCE` / `STOP_AFTER_ALWAYS` name, with the same labels.
 */
enum class StopAfter(val label: String) {
    /** A track ending advances to the next one, exactly as it always did. */
    OFF("Off"),

    /** The current track is the last one; when it ends the state returns to Off. */
    ONCE("Once"),

    /** Every track stops when it ends, until the button is clicked again. */
    ALWAYS("Always"),
}

/** The sentences this control says, in the desktop's words. */
object PlaybackWords {
    val stopAfterOff = "Stop after current: off - playback will advance to the next track."
    val stopAfterOnce = "Stop after current: once - this track is the last one."
    val stopAfterAlways = "Stop after current: always - every track stops when it ends."
    val stoppedAfterOnce = "Stopped after the current track."
    val stoppedAfterAlways = "Stopped after the current track - Stop after current is still on."

    /** The desktop's tooltips, so a long-press on a phone says what a hover says on the desktop. */
    val stopAfterTooltips = mapOf(
        StopAfter.OFF to "Stop After Current: Off - playback advances to the next track.",
        StopAfter.ONCE to "Stop After Current: Once - this track is the last one, then the button returns to Off.",
        StopAfter.ALWAYS to "Stop After Current: Always - every track stops when it ends.",
    )

    val shuffleOn = "Shuffle is on - each Next is one of the tracks not played yet."
    val shuffleOff = "Shuffle is off - each Next is the track after this one."
    val noNext = "This is the last track in the host's list."
    val noPrevious = "This is the first track in the host's list."
    val nothingPlaying = "Nothing is playing - pick a file, or press Play."
}
/**
 * The host's file list as a playing session.
 *
 * [names] is the list the host named, in the host's order. [index] is where the session is standing, and -1
 * means a track has not been started yet. Under shuffle, `history` is the order the session has played in,
 * which is what makes Previous mean "the one I heard before this one" and not "the one above it in the list".
 */
class PlayQueue(val names: List<String>, private val random: Random = Random.Default) {

    var index: Int = -1
        private set

    var shuffled: Boolean = false
        private set

    var stopAfter: StopAfter = StopAfter.OFF
        private set

    /** The tracks played in shuffle order, oldest first. The desktop keeps this the same way. */
    private val history = mutableListOf<Int>()

    val size: Int get() = names.size

    /** The track the session is standing on, or null when it has not started. */
    fun current(): String? = names.getOrNull(index)

    /**
     * Stand on the track named [name] and count it as played. This is what a list click, a Play, and a
     * Prev/Next all do, and it is why the shuffle order knows where the session has been.
     */
    fun select(name: String): Int = selectAt(names.indexOf(name))

    /** Stand on the track at position [at]. */
    fun selectAt(at: Int): Int {
        if (at < 0 || at >= names.size) return -1
        index = at
        if (shuffled && at !in history) history.add(at)
        return at
    }

    /**
     * Turn shuffle on or off.
     *
     * Turning it on seeds the order with the track that is playing, so the track a person is hearing is not
     * one of the tracks the shuffle can pick again immediately. Turning it off throws the order away, which
     * is what the desktop's `toggle_shuffle` does.
     */
    fun toggleShuffle(): Boolean {
        shuffled = !shuffled
        history.clear()
        if (shuffled && index >= 0) history.add(index)
        return shuffled
    }

    /**
     * The next track, in the desktop's rule: under shuffle a random one of the tracks not played yet, and
     * when the shuffle has played everything, a fresh order that does not repeat the track just heard.
     * Without shuffle, the track after this one, and null when this is the last one.
     */
    fun next(): Int? {
        if (names.isEmpty()) return null
        if (shuffled) {
            val unplayed = names.indices.filter { it !in history }
            val pool = if (unplayed.isNotEmpty()) {
                unplayed
            } else {
                // Everything has been played: the order starts again, and the track playing now is not the
                // one it starts with. A list of one track has nowhere to go but the same track.
                history.clear()
                if (index >= 0) history.add(index)
                names.indices.filter { it != index }.ifEmpty { names.indices.toList() }
            }
            val picked = pool.random(random)
            history.add(picked)
            index = picked
            return picked
        }
        if (index < 0) {
            index = 0
            return 0
        }
        if (index + 1 >= names.size) return null
        index += 1
        return index
    }

    /**
     * The track before this one. Under shuffle that is the track the shuffle played before this one, walked
     * back out of the order; with nothing behind it, and off shuffle, it is the track above this one in the
     * list. Null at the front of the list.
     */
    fun previous(): Int? {
        if (names.isEmpty()) return null
        if (shuffled && history.size > 1) {
            history.removeAt(history.size - 1)  // take the current track off the end of the order
            index = history[history.size - 1]
            return index
        }
        if (index > 0) {
            index -= 1
            return index
        }
        return null
    }

    /**
     * Move to the next state in the Off -> Once -> Always -> Off cycle. A click is the person taking the
     * state in hand, which is the only way this state is ever chosen.
     */
    fun cycleStopAfter(): StopAfter {
        val states = StopAfter.values()
        stopAfter = states[(stopAfter.ordinal + 1) % states.size]
        return stopAfter
    }

    /** What the state is, in the words the button shows and the status line says. */
    fun stopAfterWords(): String = when (stopAfter) {
        StopAfter.OFF -> PlaybackWords.stopAfterOff
        StopAfter.ONCE -> PlaybackWords.stopAfterOnce
        StopAfter.ALWAYS -> PlaybackWords.stopAfterAlways
    }

    /**
     * Is a track that has just ended the last one this session is going to start by itself?
     *
     * Calling this is what spends a "Once": the state that has just been used on the track that finished is
     * back to Off afterwards, exactly as the desktop's `_finish_stop_after_current` spends it. Read
     * [stopAfter] before calling this when the words to say depend on which state was armed.
     */
    fun shouldStopAfterCurrent(): Boolean = when (stopAfter) {
        StopAfter.OFF -> false
        StopAfter.ONCE -> {
            stopAfter = StopAfter.OFF
            true
        }
        StopAfter.ALWAYS -> true
    }
}

