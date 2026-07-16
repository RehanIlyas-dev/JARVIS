import asyncio
import os
import platform
import tempfile

import miniaudio
import sounddevice as sd


class TextToSpeech:
    """
    High-quality TTS using Microsoft Edge TTS (edge-tts).
    Audio pipeline: edge-tts -> MP3 file -> miniaudio decoder -> sounddevice output.
    No system-level audio tools (mpg123, ffmpeg, etc.) required.
    Voice: en-GB-RyanNeural - British male, fits the JARVIS aesthetic perfectly.
    """

    VOICE = "en-GB-RyanNeural"
    RATE  = "+5%"   # slight speed-up; 0% is natural pace
    PITCH = "-5Hz"  # slightly deeper for that JARVIS timbre

    def __init__(self):
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
        """Speak text synchronously - blocks until audio finishes playing."""
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

    def _speak_edge(self, text: str):
        """Generate MP3 with edge-tts, decode with miniaudio, play via sounddevice."""
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
        """Decode mp3 with miniaudio and play via sounddevice."""
        decoded = miniaudio.decode_file(mp3_path)

        try:
            import numpy as np
            raw = bytes(decoded.samples)
            audio_array = np.frombuffer(raw, dtype=np.int16).reshape(-1, decoded.nchannels)
            sd.play(audio_array, samplerate=decoded.sample_rate)
            sd.wait()
        except Exception as e:
            print(f"[JARVIS TTS] Playback error: {e}")

    def stop(self):
        """Stop any currently-playing audio immediately (cross-platform)."""
        try:
            sd.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Gemini STT (no daily quota)
    # ------------------------------------------------------------------

    def _recognize_gemini(self, audio):
        """
        Transcribe raw AudioData via Gemini's multimodal API.
        Avoids the free Google Speech API's ~50 req/day quota that
        otherwise silently breaks recognition.
        Raises sr.UnknownValueError if no speech is recognised.
        """
        import google.genai as genai
        from google.genai import types

        wav_bytes = audio.get_wav_data()

        client = genai.Client(api_key=self._gemini_key)
        contents = [
            "Transcribe this short spoken audio clip. Reply with ONLY the spoken words, "
            "no punctuation commentary, no quotes. If there is no speech, reply with an empty string.",
            types.Part(
                inline_data=types.Blob(
                    mime_type="audio/wav",
                    data=wav_bytes,
                )
            ),
        ]
        config = types.GenerateContentConfig(
            temperature=0.0,
        )
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        )
        text = (resp.text or "").strip()
        if not text:
            raise sr.UnknownValueError("Gemini returned no transcript")
        return text

    def _speak_espeak(self, text: str):
        """Offline fallback: Windows SAPI on Windows, espeak-ng elsewhere."""
        if platform.system() == "Windows":
            self._speak_windows_sapi(text)
        else:
            self._speak_espeak_linux(text)

    def _speak_windows_sapi(self, text: str):
        """Windows offline fallback using SAPI via pyttsx3 or direct COM."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 170)
            engine.say(text)
            engine.runAndWait()
            return
        except Exception:
            pass
        # Direct COM fallback - works without pyttsx3
        try:
            import comtypes.client
            speaker = comtypes.client.CreateObject("SAPI.SpVoice")
            speaker.Speak(text)
        except Exception as e:
            print(f"[JARVIS TTS] Windows SAPI failed: {e}. Text was: {text}")

    def _speak_espeak_linux(self, text: str):
        """Linux/macOS offline fallback using espeak-ng."""
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
