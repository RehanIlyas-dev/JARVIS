"""
J.A.R.V.I.S. — Just A Rather Very Intelligent System.

A fully voice-controlled personal AI assistant with system-level access.
Powered by Google Gemini, OpenAI, or a local Ollama model.

Modules
-------
main : CLI entry point — voice-mode loop and text-mode REPL.
web_app : Flask web server with SSE streaming and Iron Man HUD UI.
brain : JarvisBrain — LLM provider dispatch, conversation history, system-prompt assembly.
agentic_loop : Shared generator for the LLM→command→result iteration loop.
fallback_matcher : FallbackMatcher — offline command matching without any API key.
system_agent : SystemAgent — safe shell execution, cd persistence, output redaction.
stt : SpeechToText — microphone capture and speech recognition.
tts : TextToSpeech — high-quality TTS via edge-tts with miniaudio/sounddevice.
config : Centralised configuration constants.
"""

# Modules are imported by consumers; no top-level eager imports to keep
# the package importable even when optional deps (like speech_recognition)
# are not installed or are incompatible with the current Python version.

