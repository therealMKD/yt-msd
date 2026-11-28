// Open Source Software under the Apache License, Version 2.0
// Part of the yt-msd phone client (dev.ytmsd.phone).
//
// The thirty percent that is added to a track before the phone's volume does anything to it.
//
// A phone's media volume is a coarse, quiet dial: on the emulator this app was tested on, a track is barely
// audible until the dial is at 13 of 15, which leaves a person with three usable steps. The phone's dial is
// also not this app's to fix - it is the phone's own audio policy, and a ducking notification and a headset
// switch live on top of it. So the loudness is added where a media player can add it: to the decoded samples,
// before they are handed to the phone's audio track at all. That is the same place the desktop's own volume
// control works, which is why the desktop's dial goes to 150 percent.
//
// Media3's `SonicAudioProcessor` - the processor a player runs between decoding and playing - scales speed
// and pitch in the version this app compiles against, and has no volume methods: `setVolumeScalingEnabled`
// and `setVolume` arrived in Media3 1.6. So the scaling is a processor of this app's own, installed into the
// player's audio sink. `BoostedRenderersFactory` is what puts it there.
package dev.ytmsd.phone

import android.content.Context
import android.os.Handler
import androidx.media3.common.C
import androidx.media3.common.audio.AudioProcessor
import androidx.media3.common.audio.BaseAudioProcessor
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.Renderer
import androidx.media3.exoplayer.audio.AudioRendererEventListener
import androidx.media3.exoplayer.audio.AudioSink
import androidx.media3.exoplayer.audio.DefaultAudioSink
import androidx.media3.exoplayer.audio.MediaCodecAudioRenderer
import androidx.media3.exoplayer.mediacodec.MediaCodecSelector
import java.nio.ByteBuffer
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/**
 * How much louder a track is made before the phone's volume applies: thirty percent, so 1.00 becomes 1.30.
 *
 * It is one number in one place for the same reason the desktop's is: it is a taste, and a person argues with
 * it, and the argument is about this number and not about the code around it.
 */
object BoostedAudio {
    const val GAIN = 1.30f
}

/**
 * The thirty percent, applied to decoded samples.
 *
 * It runs inside the player's audio sink - between the decoder and the phone's audio track - so the phone's
 * volume dial, its ducking, its headset switch and its volume curve all apply to a signal that is already
 * thirty percent louder. That is what "before the volume applies at all" means in a media player's terms, and
 * it is the only place a player is allowed to make sound louder than the phone's dial.
 *
 * Samples are clamped at full scale rather than allowed to wrap. A track that is already recorded hot clips
 * at the top of the range, which is what a gain of any kind does; a wrapped sample is a loud buzz, and a
 * clamped one is not.
 */
@OptIn(UnstableApi::class)
class GainAudioProcessor(private val gain: Float = BoostedAudio.GAIN) : BaseAudioProcessor() {

    /** The format that comes out is the format that came in: loudness is not a format change. */
    override fun onConfigure(inputAudioFormat: AudioProcessor.AudioFormat): AudioProcessor.AudioFormat =
        inputAudioFormat

    override fun queueInput(input: ByteBuffer) {
        val encoding = inputAudioFormat.encoding
        val unit = bytesPerSample(encoding)
        val remaining = input.remaining()
        // The samples are copied out of the input buffer before anything is written, and that is not
        // bookkeeping, it is the whole shape of a Media3 audio processor: the pipeline hands over the buffer
        // the sink last produced, and the sink produces it out of *this processor's own output buffer*, so
        // `input` can be the very buffer `replaceOutputBuffer` returns. Writing into the buffer being read
        // throws `IllegalArgumentException: The source buffer is this buffer` - which is what the first
        // build on the emulator did, with the player dying on its first buffer - and a processor that read
        // and wrote the same buffer would multiply the gain once per round until the track clipped.
        val bytes = ByteArray(remaining)
        input.get(bytes)
        val output = replaceOutputBuffer(remaining)
        var at = 0
        if (gain == 1.0f || unit == 0) {
            // Nothing to scale, or a sample format this processor does not touch - the bytes go out as they
            // came in, because a player that hands over audio this code cannot read is a player that must
            // still play it.
            output.put(bytes)
            output.flip()
            return
        }
        repeat(remaining / unit) {
            when (encoding) {
                C.ENCODING_PCM_16BIT -> {
                    val scaled = (read16(bytes, at) * gain).roundToInt()
                        .coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt())
                    output.putShort(scaled.toShort())
                }
                C.ENCODING_PCM_24BIT -> {
                    // Media3's 24-bit packed samples are three bytes, least significant first.
                    val scaled = (read24(bytes, at) * gain).roundToInt().coerceIn(-8388608, 8388607)
                    output.put((scaled and 0xFF).toByte())
                    output.put(((scaled shr 8) and 0xFF).toByte())
                    output.put(((scaled shr 16) and 0xFF).toByte())
                }
                C.ENCODING_PCM_32BIT -> {
                    val scaled = (read32(bytes, at).toLong() * gain.toDouble()).roundToLong()
                        .coerceIn(Int.MIN_VALUE.toLong(), Int.MAX_VALUE.toLong())
                    output.putInt(scaled.toInt())
                }
                else -> {
                    val scaled = (java.lang.Float.intBitsToFloat(read32(bytes, at)) * gain).coerceIn(-1.0f, 1.0f)
                    output.putFloat(scaled)
                }
            }
            at += unit
        }
        // A decoder is allowed to hand over a sample stream in chunks that are not multiples of the sample
        // size. The bytes that do not make a whole sample go out as they came in, so the next chunk lines up.
        while (at < remaining) output.put(bytes[at++])
        output.flip()
    }

    /**
     * Whether the pipeline has any reason to run this processor at all.
     *
     * `AudioProcessingPipeline` skips a processor that answers `false` here - it is Media3's own way of
     * saying "this audio does not need me", and the way `SonicAudioProcessor` says it when speed and pitch
     * are at their defaults. At a gain of 1.00 there is nothing to do to a track, and a processor that says
     * so is not in the audio path at all.
     */
    override fun isActive(): Boolean = super.isActive() && gain != 1.0f

    /** A 16-bit little-endian sample, signed. */
    private fun read16(bytes: ByteArray, at: Int): Int {
        val raw = (bytes[at].toInt() and 0xFF) or ((bytes[at + 1].toInt() and 0xFF) shl 8)
        return if (raw and 0x8000 != 0) raw - 0x10000 else raw
    }

    /** A 24-bit little-endian packed sample, sign-extended. */
    private fun read24(bytes: ByteArray, at: Int): Int {
        val raw = (bytes[at].toInt() and 0xFF) or
            ((bytes[at + 1].toInt() and 0xFF) shl 8) or
            ((bytes[at + 2].toInt() and 0xFF) shl 16)
        return if (raw and 0x800000 != 0) raw - 0x1000000 else raw
    }

    /** A 32-bit little-endian word. */
    private fun read32(bytes: ByteArray, at: Int): Int =
        (bytes[at].toInt() and 0xFF) or
            ((bytes[at + 1].toInt() and 0xFF) shl 8) or
            ((bytes[at + 2].toInt() and 0xFF) shl 16) or
            ((bytes[at + 3].toInt() and 0xFF) shl 24)

    private fun bytesPerSample(encoding: Int): Int = when (encoding) {
        C.ENCODING_PCM_16BIT -> 2
        C.ENCODING_PCM_24BIT -> 3
        C.ENCODING_PCM_32BIT -> 4
        C.ENCODING_PCM_FLOAT -> 4
        else -> 0
    }
}

/**
 * The renderers a phone plays with, with the gain in the audio path.
 *
 * `DefaultRenderersFactory` builds the player's audio renderer with a `DefaultAudioSink` of its own, and the
 * sink is where an audio processor chain lives - so the factory is the place an app adds one. Replacing the
 * audio renderers here takes the sink the parent would have built, and with it the audio-offload path: a
 * processor in the chain is a processor in the phone's PCM path, which is the same trade every app that
 * scales its own audio makes.
 */
@OptIn(UnstableApi::class)
class BoostedRenderersFactory(context: Context) : DefaultRenderersFactory(context) {

    // The last parameter is `java.util.ArrayList` and not `List` on purpose: `DefaultRenderersFactory`'s
    // method is Java, and this Kotlin accepts the override only with the Java list type in it. Naming `List`
    // is a signature Kotlin says overrides nothing - which is a compile error, and a much better one than a
    // factory that quietly never gets called.
    override fun buildAudioRenderers(
        context: Context,
        extensionMode: Int,
        mediaCodecSelector: MediaCodecSelector,
        enableFallback: Boolean,
        audioSink: AudioSink,
        eventHandler: Handler,
        eventListener: AudioRendererEventListener,
        audioRenderers: java.util.ArrayList<Renderer>,
    ) {
        val boosted = DefaultAudioSink.Builder(context)
            .setAudioProcessors(arrayOf(GainAudioProcessor()))
            .build()
        audioRenderers.add(
            MediaCodecAudioRenderer(context, mediaCodecSelector, eventHandler, eventListener, boosted),
        )
    }
}

