import speech_recognition as sr


class SpeechToText:
    """
    Speech recognition using Google's free API via SpeechRecognition.

    Fixes vs. original:
    - Ambient noise calibration happens only ONCE at startup (not every listen call),
      which prevents the recognizer from miscalibrating its threshold mid-session.
    - Explicit microphone device index: prefers 'pulse' or the first real input device
      so ALSA's virtual/HDMI devices don't interfere.
    - Cleaner error messages.
    """

    def __init__(self):
        self.recognizer = sr.Recognizer()
        # Do NOT use dynamic threshold — it recalibrates too aggressively on Linux/ALSA
        # and causes the recognizer to require louder and louder input over time.
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.energy_threshold = 300  # Sensible baseline for typical rooms
        self.recognizer.pause_threshold = 0.8   # Seconds of silence to mark end of phrase

        self._mic_index = self._find_best_mic()
        self._calibrated = False
        self._calibrate()

    # ------------------------------------------------------------------
    # Device selection
    # ------------------------------------------------------------------

    def _find_best_mic(self):
        """
        Pick the best input device index.
        Priority: pulse > default hardware mic (hw:0,0) > None (library default).
        """
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
        print("[JARVIS STT] Calibrating for ambient noise — please stay quiet for 1 second...")
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
        try:
            kwargs = {}
            if self._mic_index is not None:
                kwargs["device_index"] = self._mic_index

            with sr.Microphone(**kwargs) as source:
                print("[JARVIS STT] Listening...")
                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )

            print("[JARVIS STT] Processing speech...")
            text = self.recognizer.recognize_google(audio, language="en-US")
            print(f"[JARVIS STT] Heard: '{text}'")
            return text

        except sr.WaitTimeoutError:
            return None  # Silence for `timeout` seconds — normal in wake-word loop
        except sr.UnknownValueError:
            print("[JARVIS STT] Could not understand the audio.")
            return None
        except sr.RequestError as e:
            print(f"[JARVIS STT] Google Speech API error: {e}")
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
