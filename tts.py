import asyncio
import ctypes
import ctypes.util
import os
import tempfile

import miniaudio
import pyaudio


# Must be kept alive at module level so the GC doesn't destroy it
# while ALSA still holds a pointer to it.
_ALSA_ERROR_HANDLER_CB = None


def _suppress_alsa_errors():
    """
    Suppress the flood of ALSA/JACK probing errors that PyAudio prints to stderr
    on every init. These are harmless — PyAudio just tries every backend.
    """
    global _ALSA_ERROR_HANDLER_CB
    try:
        asound = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("asound") or "libasound.so.2"
        )
        ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
            None, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        )
        _ALSA_ERROR_HANDLER_CB = ERROR_HANDLER_FUNC(lambda *_: None)
        asound.snd_lib_error_set_handler(_ALSA_ERROR_HANDLER_CB)
    except Exception:
        pass  # If we can't suppress them, just live with the noise


class TextToSpeech:
    """
    High-quality TTS using Microsoft Edge TTS (edge-tts).
    Audio pipeline: edge-tts → MP3 file → miniaudio decoder → PyAudio output.
    No system-level audio tools (mpg123, ffmpeg, etc.) required.
    Voice: en-GB-RyanNeural — British male, fits the JARVIS aesthetic perfectly.
    """

    VOICE = "en-GB-RyanNeural"
    RATE  = "+5%"   # slight speed-up; 0% is natural pace
    PITCH = "-5Hz"  # slightly deeper for that JARVIS timbre

    def __init__(self):
        _suppress_alsa_errors()          # silence ALSA/JACK probe noise
        self._pa = pyaudio.PyAudio()
        self._verify_edge_tts()

    def _verify_edge_tts(self):
        try:
            import edge_tts  # noqa: F401
            self._use_edge = True
        except ImportError:
            self._use_edge = False
            print("[JARVIS TTS] edge-tts not found. Install: pip install edge-tts")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str):
        """Speak text synchronously — blocks until audio finishes playing."""
        if not text or not text.strip():
            return

        text = text.strip()
        print(f"[JARVIS TTS] Speaking: {text[:90]}{'...' if len(text) > 90 else ''}")

        if self._use_edge:
            try:
                self._speak_edge(text)
                return
            except Exception as e:
                print(f"[JARVIS TTS] edge-tts failed ({e}), falling back to espeak.")

        self._speak_espeak(text)

    def __del__(self):
        try:
            self._pa.terminate()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _speak_edge(self, text: str):
        """Generate MP3 with edge-tts, decode with miniaudio, play via PyAudio."""
        import edge_tts

        async def _generate(path: str):
            communicate = edge_tts.Communicate(text, voice=self.VOICE, rate=self.RATE, pitch=self.PITCH)
            await communicate.save(path)

        # Write to a named temp mp3 file
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        try:
            asyncio.run(_generate(tmp_path))
            self._play_mp3(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _play_mp3(self, mp3_path: str):
        """Decode mp3 with miniaudio and stream PCM frames through PyAudio."""
        decoded = miniaudio.decode_file(mp3_path)

        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=decoded.nchannels,
            rate=decoded.sample_rate,
            output=True,
        )
        try:
            # Write in chunks for smoother playback
            raw = bytes(decoded.samples)
            chunk_size = 4096
            for i in range(0, len(raw), chunk_size):
                stream.write(raw[i : i + chunk_size])
        finally:
            stream.stop_stream()
            stream.close()

    def _speak_espeak(self, text: str):
        """Offline fallback using espeak-ng (robotic but always works)."""
        import subprocess
        for cmd in ["espeak-ng", "espeak"]:
            try:
                subprocess.run([cmd, "-v", "en-gb", "-s", "170", "-p", "40", text],
                               capture_output=True)
                return
            except FileNotFoundError:
                continue
        print(f"[JARVIS TTS] No TTS engine available. Text was: {text}")


if __name__ == "__main__":
    tts = TextToSpeech()
    tts.speak("Hello Sir. I am JARVIS. I am fully operational and ready to assist you.")
