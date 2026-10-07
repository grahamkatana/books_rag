package com.graham_katana.bookrag.feature.chat

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.unit.dp
import java.util.Locale

/** Voice in: the phone's own speech recogniser, with partial results so the words appear while you speak. */
@Stable
class Listener(private val context: Context, private val onText: (String, Boolean) -> Unit) {
    var listening by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    private var recognizer: SpeechRecognizer? = null

    val available: Boolean get() = SpeechRecognizer.isRecognitionAvailable(context)
    val permitted: Boolean get() = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    fun start() {
        if (listening) return
        if (!available) { error = "Speech recognition is not available on this phone."; return }
        error = null
        val r = recognizer ?: SpeechRecognizer.createSpeechRecognizer(context).also { recognizer = it }
        r.setRecognitionListener(object : RecognitionListener {
            override fun onResults(results: Bundle?) { listening = false; deliver(results, true) }
            override fun onPartialResults(partialResults: Bundle?) = deliver(partialResults, false)
            override fun onError(code: Int) {
                listening = false
                error = when (code) {
                    SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Did not catch that. Tap the microphone and try again."
                    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission is off."
                    SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Speech recognition needs a connection on this phone."
                    else -> "Speech recognition failed (code $code)."
                }
            }
            override fun onReadyForSpeech(params: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })
        listening = true
        r.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "en-ZA")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        })
    }

    fun stop() { recognizer?.stopListening() }

    fun release() { listening = false; recognizer?.destroy(); recognizer = null }

    private fun deliver(bundle: Bundle?, final: Boolean) {
        val text = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim().orEmpty()
        if (text.isNotEmpty()) onText(text, final)
    }
}

/** Voice out: the phone's text-to-speech engine, fed sentence by sentence while an answer streams in. */
@Stable
class Speaker(context: Context) {
    var speaking by mutableStateOf(false); private set
    var ready by mutableStateOf(false); private set
    private var tts: TextToSpeech? = null
    private var queued = 0
    private var n = 0

    init {
        tts = TextToSpeech(context.applicationContext) { status ->
            val engine = tts
            if (status == TextToSpeech.SUCCESS && engine != null) {
                val set = engine.setLanguage(Locale("en", "ZA"))
                if (set == TextToSpeech.LANG_MISSING_DATA || set == TextToSpeech.LANG_NOT_SUPPORTED) engine.setLanguage(Locale.ENGLISH)
                engine.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                    override fun onStart(utteranceId: String?) { speaking = true }
                    override fun onDone(utteranceId: String?) = finished()
                    @Deprecated("Deprecated in Java") override fun onError(utteranceId: String?) = finished()
                })
                ready = true
            }
        }
    }

    /** Adds text to the end of what is being said. */
    fun say(text: String) {
        val engine = tts?.takeIf { ready } ?: return
        for (piece in pieces(text, minOf(TextToSpeech.getMaxSpeechInputLength(), 3000))) {
            queued++
            speaking = true
            if (engine.speak(piece, TextToSpeech.QUEUE_ADD, null, "u${n++}") != TextToSpeech.SUCCESS) finished()
        }
    }

    /** Stops at once and drops whatever was waiting. */
    fun stop() { tts?.stop(); queued = 0; speaking = false }

    fun release() { tts?.stop(); tts?.shutdown(); tts = null; ready = false; speaking = false }

    private fun finished() { if (queued > 0) queued--; if (queued == 0) speaking = false }
}

@Composable
fun rememberSpeaker(): Speaker {
    val context = LocalContext.current
    val speaker = remember { Speaker(context) }
    DisposableEffect(speaker) { onDispose { speaker.release() } }
    return speaker
}

@Composable
fun rememberListener(onText: (String, Boolean) -> Unit): Listener {
    val context = LocalContext.current
    val latest = androidx.compose.runtime.rememberUpdatedState(onText)
    val listener = remember { Listener(context) { t, f -> latest.value(t, f) } }
    DisposableEffect(listener) { onDispose { listener.release() } }
    return listener
}

/** Microphone, speaker and stop drawn here so the app does not need the large extended icon set. */
object VoiceIcons {
    private fun icon(name: String, path: String) = ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).addPath(
        pathData = PathParser().parsePathString(path).toNodes(), fill = SolidColor(Color.Black)
    ).build()

    val Mic: ImageVector by lazy { icon("Mic", "M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zM17.3 11c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z") }
    val Speaker: ImageVector by lazy { icon("Speaker", "M3 9v6h4l5 5V4L7 9H3zM16.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z") }
    val Stop: ImageVector by lazy { icon("Stop", "M6 6h12v12H6z") }
}
