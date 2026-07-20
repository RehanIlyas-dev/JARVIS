# JARVIS

A fully voice-controlled personal AI assistant with system-level access, powered by Google Gemini, OpenAI, or a local Ollama model. Listens for a wake word, processes natural language via an LLM, executes shell commands autonomously, and speaks responses aloud. Works on **Linux**, **macOS**, and **Windows**.

---

## Quick Start

```bash
# Install
pip install jarvis-voice-assistant

# Run
jarvis                    # voice mode (terminal)
jarvis --text             # text-only mode
jarvis-web                # web UI at http://127.0.0.1:5000
```

### Docker (no system deps)

```bash
docker run -d -p 5000:5000 --env-file .env rehanilyas4726/jarvis
```

### From source

```bash
git clone https://github.com/RehanIlyas-dev/JARVIS.git
cd JARVIS
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
./run.sh
```

---

## Usage

| Mode | Command | Description |
|------|---------|-------------|
| **Voice** | `jarvis` | Say "Jarvis" + command, or "Jarvis" alone and wait for "Yes, Sir?". 30s follow-up window after each response. |
| **Text** | `jarvis --text` | Type commands. JARVIS speaks + prints responses. `exit` to quit. |
| **Web** | `jarvis-web` | Browser chat at `http://127.0.0.1:5000` with Iron Man HUD, always-on wake word, real-time system monitoring. |

---

## Configuration

Copy `.env.example` to `.env` and set at least one API key:

```bash
GEMINI_API_KEY="..."              # Recommended — fast, free tier available
OPENAI_API_KEY="..."              # Optional
OLLAMA_API_URL="http://localhost:11434/v1"  # Fully offline
```

---

## Offline Mode (No API Key)

When no API key is available or the Gemini quota is exhausted, JARVIS switches to **fallback mode** with 50+ built-in commands: greetings, file management, app launcher, system info (time, memory, disk, IP, processes, battery), git, docker, volume controls, screenshots, and more. Destructive commands remain blocked.

---

## Architecture

```
main.py / web_app.py → generate_agentic_loop() → yields events (thinking, response, command, output, done)
```

| Module | Responsibility |
|--------|---------------|
| `brain.py` | LLM dispatch (Gemini / OpenAI / Ollama / fallback), conversation history |
| `agentic_loop.py` | Shared generator driving both TUI and web UI |
| `fallback_matcher.py` | 50+ offline command intents (git, docker, files, apps, system) |
| `system_agent.py` | Safe shell execution, `cd` persistence, dangerous-command guard |
| `stt.py` / `tts.py` | Speech-to-text (Google/Gemini) and text-to-speech (edge-tts with miniaudio + sounddevice) |
| `config.py` | Single source of truth for all tunables |

Configurable cap: `MAX_AGENTIC_ITERATIONS = 8` in `config.py`.

---

## CI/CD

Every push triggers GitHub Actions (`.github/workflows/ci.yml`):

| Job | What it does |
|-----|-------------|
| **lint** | `py_compile` syntax check |
| **test** | `pytest tests/` across ubuntu/macos/windows × Python 3.9–3.12 |
| **build** | Pip wheel + source distribution |
| **docker** | Builds + pushes `rehanilyas4726/jarvis:latest` (and `:vX.Y.Z` on tags) |
| **publish** | On `v*` tags: PyPI release + GitHub Release |

Trigger a release: bump version in `pyproject.toml`, tag, push:

```bash
git tag v1.1.0 && git push origin main --follow-tags
```

---

## Security

- JARVIS executes real shell commands as the current user. Do not run as root.
- Destructive commands (`rm -rf /`, fork bombs, disk format) are permanently blocked.
- `shutdown`, `rm -r`, `passwd` require typed confirmation.
- API keys are environment variables only — never commit them.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| **Microphone not detected** | `sudo apt install libportaudio2` (Linux) or `brew install portaudio` (macOS) |
| **No audio output** | Install `espeak-ng` as offline TTS fallback |
| **Gemini 429 rate limit** | Wait for reset, switch to paid plan, or use OpenAI/Ollama |
| **PyAudio fails (Windows)** | `pip install pipwin && pipwin install pyaudio` |
| **Web UI voice not working** | Use Chrome/Edge, allow mic permission, click microphone button |
| **macOS mic blocked** | System Settings → Privacy → Microphone → enable Terminal |

---

## Contributing

```bash
git clone https://github.com/RehanIlyas-dev/JARVIS.git
cd JARVIS
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

1. Fork, create a feature branch, make changes
2. Run `pytest tests/` — all tests must pass
3. Push and open a Pull Request to `main`

CI runs lint + tests across Linux/macOS/Windows × Python 3.9–3.12. All checks must pass before merging.

---

## Acknowledgments

Google Gemini, edge-tts, SpeechRecognition, PyAudio, miniaudio, sounddevice, Flask.
