// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The phone's own media volume. The window's volume bar is not a volume of its own: it reads and moves the
// same stream the phone's hardware keys, headset buttons and system slider move, so the app's number and the
// phone's number cannot disagree.
package dev.ytmsd.phone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import androidx.core.content.ContextCompat

/**
 * The phone's own "the volume moved" broadcast.
 *
 * Named by the string the framework uses, not by `AudioManager.VOLUME_CHANGED_ACTION`: that constant is
 * deprecated on the API this app compiles against, and Kotlin 2.0 refuses to resolve a deprecated-and-hidden
 * framework symbol. The broadcast itself is what the hardware keys, a headset button and a system slider send,
 * and the string is the same on every phone.
 */
private const val VOLUME_CHANGED_ACTION = "android.media.VOLUME_CHANGED_ACTION"

/**
 * The phone's media volume, read and moved the way the phone's own controls move it.
 *
 * `STREAM_MUSIC` is the stream a music player's audio goes out on - it is where `USAGE_MEDIA`, which is what
 * the player asks the phone for, lands. The bar in the window and the hardware keys are the same dial, which
 * is the only way a volume bar on a phone screen is honest about the sound coming out of the phone.
 */
class PhoneVolume(private val context: Context) {

    private val audio: AudioManager =
        context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    /** The top of the dial. Phones differ in where that is, so nothing here is written as a constant. */
    val maxLevel: Int get() = audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC)

    /** Where the dial is now. */
    val level: Int get() = audio.getStreamVolume(AudioManager.STREAM_MUSIC)

    /** Move the dial. A level off the end of the dial is the end of the dial, not a crash. */
    fun setLevel(value: Int) {
        audio.setStreamVolume(AudioManager.STREAM_MUSIC, value.coerceIn(0, maxLevel), 0)
    }

    /** A media volume of 0 is silence, and no player in the world can make it louder. */
    val isMuted: Boolean get() = level == 0

    /**
     * Make the phone audible, if it is not.
     *
     * The phone ducks, mutes and restores this stream under its own audio policy - opening the notification
     * shade is enough to do it - and a player that starts while the dial is at 0 plays silently with nothing
     * on the phone's screen saying why. Raising the dial and saying so is the difference between an app that
     * looks broken and a phone that was simply muted.
     *
     * It raises to a quarter of the dial, not to 1. A level of 1 out of 15 is so quiet it reads as broken
     * too, which is the complaint this exists to answer; a quarter is hearable, and it is far enough from the
     * top of the dial that it does not shout at the room.
     */
    fun raiseFromMute(): Boolean {
        if (!isMuted) return false
        setLevel(quietComfortLevel)
        return true
    }

    /** A level worth playing at when the phone had none: a quarter of the dial, and never 0. */
    val quietComfortLevel: Int get() = maxOf(1, maxLevel / 4)

    /**
     * Follow the phone.
     *
     * The hardware keys, a headset's own control, and a system slider all move this volume without asking the
     * app, and each says so on the `VOLUME_CHANGED_ACTION` broadcast. A bar that does not listen to that
     * broadcast is a bar showing the app's last guess at the phone's volume, which is how a slider ends up
     * saying 5 while the phone is playing at 1.
     *
     * Closing what this returns takes the listener off the phone's broadcasts.
     */
    fun follow(report: (Int) -> Unit): AutoCloseable {
        val listener = object : BroadcastReceiver() {
            override fun onReceive(where: Context, what: Intent) {
                report(level)
            }
        }
        ContextCompat.registerReceiver(
            context,
            listener,
            IntentFilter(VOLUME_CHANGED_ACTION),
            // A listener on a system broadcast is not a door the app opens to other apps.
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        return AutoCloseable { context.unregisterReceiver(listener) }
    }
}