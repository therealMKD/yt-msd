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
}