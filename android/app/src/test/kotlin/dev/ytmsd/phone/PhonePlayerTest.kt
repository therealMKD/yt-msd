// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The two things the window makes sound with: a player that asked the phone for the right to make sound, and a
// volume bar on the phone's own media volume. Both were broken on the first run on a real device - music at a
// quarter of its volume that stopped at the first system sound, and no volume control in the app at all - and
// neither is visible in a protocol check, so they are checked here.
package dev.ytmsd.phone

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioManager
import android.os.Looper
import androidx.media3.common.C
import androidx.media3.common.audio.AudioProcessor
import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PhonePlayerTest {

    /** The broadcast the phone sends when its own volume moved - the string, as `PhoneVolume` names it. */
    private fun phoneMovedTheVolume(context: Context) {
        context.sendBroadcast(Intent("android.media.VOLUME_CHANGED_ACTION"))
    }

    /** Let the main looper run what it has been handed - a broadcast is delivered on it. */
    private fun settle() {
        shadowOf(Looper.getMainLooper()).idle()
    }

    private fun await(millis: Long = 5000, condition: () -> Boolean): Boolean {
        val until = System.currentTimeMillis() + millis
        while (System.currentTimeMillis() < until) {
            settle()
            if (condition()) return true
            Thread.sleep(50)
        }
        settle()
        return condition()
    }

    @Test
    fun `the player asks the phone for the media stream, so a system sound cannot take it away`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val player = PhonePlayer(activity)
        try {
            // USAGE_MEDIA with MUSIC content is what the phone treats as music: the thing it lets play at full
            // volume, the thing it ducks under a notification, and the thing it hands back afterwards.
            assertEquals(AudioAttributes.USAGE_MEDIA, player.exo.audioAttributes.usage)
            assertEquals(AudioAttributes.CONTENT_TYPE_MUSIC, player.exo.audioAttributes.contentType)
        } finally {
            player.release()
        }
    }

    @Test
    fun `the volume bar is the phone's media volume, both ways`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val volume = PhoneVolume(activity)
        val audio = activity.getSystemService(Context.AUDIO_SERVICE) as AudioManager

        assertTrue("the phone named no media volume at all", volume.maxLevel > 0)

        // The app's bar moves the phone's volume.
        volume.setLevel(volume.maxLevel)
        assertEquals(volume.maxLevel, audio.getStreamVolume(AudioManager.STREAM_MUSIC))
        assertEquals(volume.maxLevel, volume.level)
        volume.setLevel(0)
        assertEquals(0, volume.level)
        // A level off the end of the dial is the end of the dial, and not a crash and not a negative volume.
        volume.setLevel(volume.maxLevel + 9)
        assertEquals(volume.maxLevel, volume.level)
        volume.setLevel(-4)
        assertEquals(0, volume.level)

        // The phone's volume moves the app's bar. The hardware keys, a headset and a system slider all say so
        // on this broadcast, and the bar has to listen.
        var seen = -1
        val watch = volume.follow { level -> seen = level }
        try {
            volume.setLevel(2)
            phoneMovedTheVolume(activity)
            assertTrue("the bar did not follow the phone", await { seen == 2 })
        } finally {
            watch.close()
        }

        // Closing the follow takes the bar off the phone's broadcasts.
        volume.setLevel(1)
        phoneMovedTheVolume(activity)
        settle()
        Thread.sleep(200)
        settle()
        assertEquals("the bar kept listening after it was closed", 2, seen)
    }

    @Test
    fun `a phone volume of zero is raised to audible, and only from zero`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val volume = PhoneVolume(activity)

        volume.setLevel(0)
        assertTrue("a media volume of 0 should read as muted", volume.isMuted)
        assertTrue("a muted phone should be raised", volume.raiseFromMute())
        assertEquals(
            "a raised phone should sit at the quiet comfort level",
            volume.quietComfortLevel,
            volume.level,
        )
        assertTrue("the quiet comfort level should be hearable", volume.quietComfortLevel > 1)
        assertFalse("an audible phone should be left alone", volume.raiseFromMute())
        assertEquals("an audible phone should keep its own level", volume.quietComfortLevel, volume.level)
    }

    @Test
    fun `every track is boosted by thirty percent before the phone's volume applies`() {
        val activity = Robolectric.buildActivity(MainActivity::class.java).setup().get()
        val player = PhonePlayer(activity)
        try {
            assertEquals("a track must be thirty percent louder than the file on it", 1.30f, player.boost, 0.0001f)
            assertTrue(
                "the boost has to live in the renderers the player plays with, not somewhere the player ignores",
                player.renderersFactory is BoostedRenderersFactory,
            )
        } finally {
            player.release()
        }

        // The arithmetic the boost is made of: 16-bit samples scaled by thirty percent, with the top of the
        // range held rather than wrapped. This is the code the player's audio sink runs on every sample of
        // every track, between the decoder and the phone's audio track - which is what "before the volume
        // applies" means, and the only place a player is allowed to make a track louder than the phone's dial.
        val gain = GainAudioProcessor(1.30f)
        val shape = gain.configure(AudioProcessor.AudioFormat(44100, 2, C.ENCODING_PCM_16BIT))
        // `configure` parks the format in the *pending* pair; `flush` is what makes it the format the
        // processor reads while it works, and a player calls flush before it feeds a processor any bytes.
        // A check that skips the flush hands the processor `NOT_SET`, and it passes audio through - which is
        // the correct behaviour for a processor that has not been told what it is being fed.
        gain.flush()
        val samples = intArrayOf(0, 1000, -1000, 20000, -20000, 32767, -32768)
        val inBuffer = ByteBuffer.allocateDirect(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        samples.forEach { inBuffer.putShort(it.toShort()) }
        inBuffer.flip()
        gain.queueInput(inBuffer)
        val out = gain.output
        val scaled = IntArray(samples.size) { out.short.toInt() }
        assertArrayEquals(
            "16-bit samples must come out thirty percent louder, clipped at full scale - got " +
                scaled.joinToString(", "),
            intArrayOf(0, 1300, -1300, 26000, -26000, 32767, -32768),
            scaled,
        )
        assertEquals(
            "the gain must not change the format it is handed",
            C.ENCODING_PCM_16BIT,
            shape.encoding,
        )
        assertEquals("the gain must not change the rate", 44100, shape.sampleRate)
        assertEquals("the gain must not change the channels", 2, shape.channelCount)
        gain.reset()

        // 32-bit audio, the format a player hands over when it is asked for float-free high-depth output.
        val deep = GainAudioProcessor(1.30f)
        deep.configure(AudioProcessor.AudioFormat(48000, 1, C.ENCODING_PCM_32BIT))
        deep.flush()
        val deepIn = ByteBuffer.allocateDirect(8).order(ByteOrder.LITTLE_ENDIAN)
        deepIn.putInt(1_000_000)
        deepIn.putInt(-2_000_000_000)
        deepIn.flip()
        deep.queueInput(deepIn)
        val deepOut = deep.output
        assertEquals("32-bit samples take the same thirty percent", 1_300_000, deepOut.int)
        assertEquals("full scale is held, not wrapped", Int.MIN_VALUE, deepOut.int)
        deep.reset()

        // A format the processor does not read is handed over untouched - a player must still play audio
        // this code cannot scale, and silence from a decoder is not an option.
        val untouched = GainAudioProcessor(1.30f)
        untouched.configure(AudioProcessor.AudioFormat(48000, 2, C.ENCODING_PCM_8BIT))
        untouched.flush()
        val raw = ByteBuffer.allocateDirect(4).order(ByteOrder.LITTLE_ENDIAN)
        raw.put(byteArrayOf(1, 2, 3, 4))
        raw.flip()
        untouched.queueInput(raw)
        // `getOutput()` is a hand-over, not a peek: Media3's implementation returns the filled buffer and
        // puts an empty one back in its place, so a check takes the output once and reads it from there.
        val untouchedOut = untouched.output
        assertEquals("an encoding this code does not read must come out the same size it went in",
            4, untouchedOut.remaining())
        assertArrayEquals(
            "the bytes must come out in the order they went in",
            byteArrayOf(1, 2, 3, 4),
            ByteArray(4) { untouchedOut.get() },
        )
        untouched.reset()
    }

    @Test
    fun `the buffer Media3 hands back is the processor's own output, and a pass scales the track once`() {
        val gain = GainAudioProcessor(1.30f)
        gain.configure(AudioProcessor.AudioFormat(44100, 2, C.ENCODING_PCM_16BIT))
        gain.flush()
        val samples = intArrayOf(1000, 20000, -20000, 30000)
        val first = ByteBuffer.allocateDirect(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        samples.forEach { first.putShort(it.toShort()) }
        first.flip()
        gain.queueInput(first)
        val out = gain.output
        assertArrayEquals(
            "the first pass scales by thirty percent",
            intArrayOf(1300, 26000, -26000, 32767),
            IntArray(samples.size) { out.short.toInt() },
        )

        // The pipeline and the codec's buffer pool hand the buffer the player just produced back to the
        // processor as its next input - the same object. A processor that writes into the buffer it is
        // reading throws here (`The source buffer is this buffer`, which is what the emulator caught on its
        // first buffer of audio), and a processor that reads and writes the same bytes compounds the gain
        // within one pass - 1.30 becoming 1.69, then 2.20, a track turned up to a wall of clipping.
        out.flip()
        gain.queueInput(out)
        val out2 = gain.output
        val second = IntArray(samples.size) { out2.short.toInt() }
        assertArrayEquals(
            "the second pass scales the samples it was handed, once each",
            intArrayOf(1690, 32767, -32768, 32767),
            second,
        )
        gain.reset()

        // A processor with nothing to add says the pipeline can skip it, which is how Media3 keeps an idle
        // processor out of the audio path. `BaseAudioProcessor.isActive()` answers whether the processor has a
        // format to work on, and the pipeline asks after `configure`, so these are configured before they are
        // asked - the same order the player's sink uses.
        val format = AudioProcessor.AudioFormat(44100, 2, C.ENCODING_PCM_16BIT)
        val idle = GainAudioProcessor(1.00f)
        idle.configure(format)
        val boosted = GainAudioProcessor(1.30f)
        boosted.configure(format)
        assertFalse(
            "a gain of 1.00 has nothing to do to a track",
            idle.isActive(),
        )
        assertTrue(
            "a gain of 1.30 is in the path",
            boosted.isActive(),
        )
        idle.reset()
        boosted.reset()
    }
}
