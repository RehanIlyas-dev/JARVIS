import os
import speech_recognition as sr

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


class SpeechToText:
    """
    Speech recognition via SpeechRecognition.

    STT backend priority:
      1. Gemini (if GEMINI_API_KEY is set) - no daily quota, multimodal
         transcription through gemini-2.5-flash. Avoids the free Google
         Speech API's ~50 req/day limit that silently breaks recognition.
      2. Google's free Speech API (fallback) - used only when no key is set.

    Fixes vs. original:
    - Ambient noise calibration happens only ONCE at startup (not every listen call),
      which prevents the recognizer from miscalibrating its threshold mid-session.
    - Explicit microphone device index: prefers 'pulse' or the first real input device
      so ALSA's virtual/HDMI devices don't interfere.
    - Cleaner error messages.
    """

    def __init__(self):
        self.recognizer = sr.Recognizer()
        # Gemini STT is preferred (no quota). Uses the same key as the brain.
        self._gemini_key = os.environ.get("GEMINI_API_KEY")
        self._use_gemini = bool(self._gemini_key)
        if self._use_gemini:
            print("[JARVIS STT] Using Gemini speech recognition (no daily quota).")
        else:
            print("[JARVIS STT] GEMINI_API_KEY not set - using free Google Speech API "
                  "(limited to ~50 req/day).")
        # Do NOT use dynamic threshold - it recalibrates too aggressively on Linux/ALSA
        # and causes the recognizer to require louder and louder input over time.
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.energy_threshold = 300  # Sensible baseline for typical rooms
        self.recognizer.pause_threshold = 0.5   # Seconds of silence to mark end of phrase (lower = quicker cutoff)
        self.recognizer.operation_timeout = None
        self.recognizer.phrase_threshold = 0.3  # Minimum seconds of speech before a phrase is registered
        self.recognizer.non_speaking_duration = 0.5  # Max seconds of non-speaking allowed before phrase ends

        self._mic_index = self._find_best_mic()
        self._calibrated = False
        self._calibrate()

    # ------------------------------------------------------------------
    # Device selection
    # ------------------------------------------------------------------

    def _find_best_mic(self):
        """
        Pick the best input device index.
        On Windows, use the OS default microphone (no device_index needed).
        On Linux, prefer PulseAudio 'pulse' device.
        """
        import platform
        if platform.system() == "Windows":
            print("[JARVIS STT] Using default Windows microphone.")
            return None

        try:
            mics = sr.Microphone.list_microphone_names()
            print(f"[JARVIS STT] Available microphones: {mics}")

            # Prefer PulseAudio/PipeWire 'pulse' device (most reliable on modern Linux)
            for i, name in enumerate(mics):
                if "pulse" in name.lower():
                    print(f"[JARVIS STT] Selected microphone [{i}]: {name}")
                    return i

            # Second choice: first real analog input
            for i, name in enumerate(mics):
                if "hda" in name.lower() or "cx8200" in name.lower() or "analog" in name.lower():
                    print(f"[JARVIS STT] Selected microphone [{i}]: {name}")
                    return i

        except Exception as e:
            print(f"[JARVIS STT] Could not enumerate microphones: {e}")

        print("[JARVIS STT] Using default microphone.")
        return None  # Let the library pick the OS default

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def _calibrate(self):
        """
        Calibrate the energy threshold once by sampling ambient noise for 1 second.
        Called at startup only.
        """
        print("[JARVIS STT] Calibrating for ambient noise - please stay quiet for 1 second...")
        try:
            kwargs = {}
            if self._mic_index is not None:
                kwargs["device_index"] = self._mic_index

            with sr.Microphone(**kwargs) as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)

            print(f"[JARVIS STT] Calibration complete. Energy threshold set to {self.recognizer.energy_threshold:.0f}")
            self._calibrated = True
        except Exception as e:
            print(f"[JARVIS STT] Calibration failed: {e}. Using default threshold.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def listen(self, timeout=None, phrase_time_limit=None):
        """
        Block until a phrase is spoken, then return the recognised text (or None).

        Args:
            timeout: Seconds to wait for speech to start. None = wait forever.
            phrase_time_limit: Max seconds for a single phrase. None = unlimited.
        """
        kwargs = {}
        if self._mic_index is not None:
            kwargs["device_index"] = self._mic_index

        try:
            # On Windows the PyAudio input stream from a previous listen() call can be
            # left in a consumed/closed state, so a subsequent listen() silently ignores
            # speech until the mic is physically toggled. To fix this, open a BRAND NEW
            # sr.Microphone (and thus a fresh PyAudio stream) on every attempt and retry
            # once if a half-open stream raises OSError. The `with` block guarantees the
            # stream is closed before the next iteration, so no stream survives across loops.
            audio = None
            for attempt in range(2):
                try:
                    with sr.Microphone(**kwargs) as source:
                        print("[JARVIS STT] Listening...")
                        audio = self.recognizer.listen(
                            source,
                            timeout=timeout,
                            phrase_time_limit=phrase_time_limit,
                        )
                    break
                except OSError as e:
                    # Half-open / stale PyAudio stream. Retry with a fresh microphone.
                    if attempt == 0:
                        print(f"[JARVIS STT] Microphone stream error, reopening: {e}")
                        continue
                    raise

            if audio is None:
                # Recognizer returned no audio object (some Windows builds after a
                # command). The fresh-mic retry above already ran; give up gracefully.
                print("[JARVIS STT] No audio captured.")
                return None

            print("[JARVIS STT] Processing speech...")
            try:
                if self._use_gemini:
                    text = self._recognize_gemini(audio)
                else:
                    text = self.recognizer.recognize_google(audio, language="en-US")
            except sr.UnknownValueError:
                # Audio WAS captured but the engine returned no transcript.
                # Two common causes:
                #   1. Background noise triggered the mic but no real speech -> lower energy_threshold
                #   2. Free Google Speech API daily quota (≈50 req/day) exhausted
                #      (set GEMINI_API_KEY and restart the terminal to avoid this)
                print("[JARVIS STT] Audio captured but no speech recognised.")
                print("[JARVIS STT]   -> If this happens often: reduce background noise, or the free Google quota may be exhausted.")
                return None
            print(f"[JARVIS STT] Heard: '{text}'")
            return text

        except sr.WaitTimeoutError:
            print("[JARVIS STT] No speech detected (timeout).")
            return None  # Silence for `timeout` seconds - normal in wake-word loop
        except sr.RequestError as e:
            # Google's free endpoint rejected the request (quota/network/auth).
            print(f"[JARVIS STT] Google Speech API request failed: {e}")
            print("[JARVIS STT]   -> Free Google STT has a ~50 req/day limit. Set GEMINI_API_KEY and restart the terminal to use Gemini instead.")
            return None
        except OSError as e:
            print(f"[JARVIS STT] Microphone error: {e}")
            return None
        except Exception as e:
            print(f"[JARVIS STT] Unexpected error: {e}")
            return None


if __name__ == "__main__":
    stt = SpeechToText()
    print("\nSpeak something to test...")
    heard = stt.listen(timeout=5, phrase_time_limit=8)
    if heard:
        print(f"Success! Recognized text: '{heard}'")
    else:
        print("Failed to recognize speech.")
