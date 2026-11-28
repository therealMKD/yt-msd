// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The rules a playing session runs on, checked on this machine. Shuffle, Previous, Next and the three states
// of "stop after current" are the controls the desktop has had for years, and they are the rules a phone
// screen has no room to explain - so they are checked here as plain rules, and the window is left being a
// reader of them.
package dev.ytmsd.phone

import kotlin.random.Random
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PlayQueueTest {

    private val names = listOf("one", "two", "three", "four", "five")

    @Test
    fun `a session starts nowhere, and a Play stands it on the track it names`() {
        val queue = PlayQueue(names)
        assertEquals(-1, queue.index)
        assertNull(queue.current())
        assertEquals(2, queue.select("three"))
        assertEquals("three", queue.current())
        assertEquals(-1, queue.select("not in the list"))
    }

    @Test
    fun `off shuffle, next walks the host's order and stops at the end of it`() {
        val queue = PlayQueue(names)
        queue.select("one")
        assertEquals(1, queue.next())
        assertEquals(2, queue.next())
        queue.select("five")
        assertNull("the last track has no track after it", queue.next())
        assertEquals("five", queue.current())
    }

    @Test
    fun `off shuffle, previous walks back and stops at the front of it`() {
        val queue = PlayQueue(names)
        queue.select("three")
        assertEquals(1, queue.previous())
        assertEquals(0, queue.previous())
        assertNull("the first track has no track before it", queue.previous())
    }

    @Test
    fun `shuffle plays every track before it repeats any, and never plays the same track twice`() {
        val queue = PlayQueue(names, Random(20261128))
        queue.select("one")
        assertTrue(queue.toggleShuffle())
        val order = mutableListOf(queue.current()!!)
        repeat(40) {
            val moved = queue.next()
            assertTrue("shuffle ran out of tracks to play", moved != null)
            order += queue.current()!!
        }
        // The first five plays are five different tracks: a shuffle that plays a track twice before it has
        // played the others is the complaint every listener makes about shuffle.
        assertEquals(5, order.take(5).distinct().size)
        // No track follows itself, at any point in the 41 plays.
        order.zip(order.drop(1)).forEach { (before, after) ->
            assertTrue("shuffle played $after straight after playing it", before != after)
        }
    }

    @Test
    fun `shuffle on a list of one track plays that track, which is the only thing it can do`() {
        val queue = PlayQueue(listOf("only"), Random(7))
        queue.select("only")
        queue.toggleShuffle()
        assertEquals(0, queue.next())
        assertEquals("only", queue.current())
    }

    @Test
    fun `under shuffle, previous walks back out of the order the shuffle made`() {
        val queue = PlayQueue(names, Random(99))
        queue.select("one")
        queue.toggleShuffle()
        val heard = mutableListOf(queue.current()!!)
        repeat(3) {
            queue.next()
            heard += queue.current()!!
        }
        // Three Previous presses retrace the last three plays, in order, and the fourth has nowhere to go.
        assertEquals(heard[2], queue.names[queue.previous()!!])
        assertEquals(heard[1], queue.names[queue.previous()!!])
        assertEquals(heard[0], queue.names[queue.previous()!!])
        assertNull(queue.previous())
        assertEquals("one", queue.current())
    }

    @Test
    fun `turning shuffle off hands the session back to the host's order`() {
        val queue = PlayQueue(names, Random(5))
        queue.select("four")
        assertTrue("shuffle has to turn on", queue.toggleShuffle())
        queue.next()
        assertFalse("shuffle has to turn off again", queue.toggleShuffle())
        // Off shuffle, Next is the track after the one playing, wherever the shuffle had been standing.
        val standing = queue.index
        assertEquals(if (standing + 1 < names.size) standing + 1 else null, queue.next())
    }
    @Test
    fun `stop after current walks off, once, always, off - and only one click at a time`() {
        val queue = PlayQueue(names)
        assertEquals(StopAfter.OFF, queue.stopAfter)
        assertEquals(StopAfter.ONCE, queue.cycleStopAfter())
        assertEquals(StopAfter.ALWAYS, queue.cycleStopAfter())
        assertEquals(StopAfter.OFF, queue.cycleStopAfter())
        assertEquals(StopAfter.ONCE, queue.cycleStopAfter())
    }

    @Test
    fun `a track ending with nothing armed advances, and never spends a state that is off`() {
        val queue = PlayQueue(names)
        queue.select("one")
        assertFalse(queue.shouldStopAfterCurrent())
        assertEquals(1, queue.next())
        assertEquals(StopAfter.OFF, queue.stopAfter)
    }

    @Test
    fun `a once stops the session after the track it was armed on, and is spent by that track`() {
        val queue = PlayQueue(names)
        queue.select("two")
        queue.cycleStopAfter()  // off -> once
        assertTrue(queue.shouldStopAfterCurrent())
        assertEquals("a once is back to off once it has been used", StopAfter.OFF, queue.stopAfter)
        assertFalse(queue.shouldStopAfterCurrent())
    }

    @Test
    fun `an always stops after every track and stays armed until it is clicked again`() {
        val queue = PlayQueue(names)
        queue.select("two")
        queue.cycleStopAfter()  // once
        queue.cycleStopAfter()  // always
        assertTrue(queue.shouldStopAfterCurrent())
        assertTrue("always is not spent by the track it stopped", queue.shouldStopAfterCurrent())
        assertTrue(queue.shouldStopAfterCurrent())
        assertEquals(StopAfter.ALWAYS, queue.stopAfter)
        queue.cycleStopAfter()  // back to off
        assertFalse(queue.shouldStopAfterCurrent())
    }

    @Test
    fun `the words the phone says are the words the desktop says for the same control`() {
        assertEquals(
            "Stop after current: off - playback will advance to the next track.",
            PlaybackWords.stopAfterOff,
        )
        assertEquals("Stop after current: once - this track is the last one.", PlaybackWords.stopAfterOnce)
        assertEquals(
            "Stop after current: always - every track stops when it ends.",
            PlaybackWords.stopAfterAlways,
        )
        assertEquals("Stopped after the current track.", PlaybackWords.stoppedAfterOnce)
        assertEquals(
            "Stopped after the current track - Stop after current is still on.",
            PlaybackWords.stoppedAfterAlways,
        )
        assertEquals(PlaybackWords.stopAfterOff, PlayQueue(names).stopAfterWords())
        assertEquals(
            "Stop After Current: Once - this track is the last one, then the button returns to Off.",
            PlaybackWords.stopAfterTooltips.getValue(StopAfter.ONCE),
        )
        assertEquals(
            "Stop After Current: Off - playback advances to the next track.",
            PlaybackWords.stopAfterTooltips.getValue(StopAfter.OFF),
        )
        assertEquals(
            "Stop After Current: Always - every track stops when it ends.",
            PlaybackWords.stopAfterTooltips.getValue(StopAfter.ALWAYS),
        )
        assertEquals(listOf("Off", "Once", "Always"), StopAfter.values().map { it.label })
    }

    @Test
    fun `a queue rebuilt on a new list is a new session, and a name is how the old one is carried over`() {
        val first = PlayQueue(names)
        first.select("three")
        val rebuilt = PlayQueue(names.reversed())
        assertEquals(-1, rebuilt.index)
        rebuilt.select("three")
        assertEquals(2, rebuilt.index)
        assertEquals(1, rebuilt.previous())
        assertEquals("four", rebuilt.current())
    }
}

