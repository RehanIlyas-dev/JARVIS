# JARVIS

A fully voice-controlled personal AI assistant with system-level access, built in Python. Powered by Google Gemini, OpenAI, or a local Ollama model.

JARVIS listens for a wake word, processes natural language via a large language model, executes shell commands autonomously, and speaks responses aloud using a high-quality neural voice. Fully functional on **Linux**, **macOS**, and **Windows**.

---

## Features

- **Wake Word Detection** — Passive listening mode activated by saying "JARVIS"
- **Active Follow-Up Window** — After each response, stays active for 30 seconds to accept follow-up commands without repeating the wake word
- **Speech-to-Text** — Microphone input processed via Google Speech Recognition or Gemini multimodal transcription (no daily quota)
- **Text-to-Speech** — High-quality British neural voice via Microsoft Edge TTS (edge-tts), decoded in-process using miniaudio and streamed through sounddevice
- **Agentic Loop** — Runs shell commands, reads the output, and iterates up to 8 times per turn to complete multi-step tasks autonomously
- **Multiple LLM Backends** — Google Gemini, OpenAI, or locally-hosted Ollama
- **Safety Guardrails** — Hard-blocks destructive commands (fork bombs, disk wipes) and requires typed confirmation for dangerous operations
- **Persistent Working Directory** — `cd` commands persist across turns; the brain always knows the current directory
- **Text Mode** — Full functionality via keyboard if microphone is unavailable
- **Web Interface** — Browser-based chat UI served via Flask with Iron Man HUD design
- **Offline Fallback** — Built-in command matcher handles 50+ commands without any API key

---

## Technology Stack

### Speech-to-Text (STT)

| Component | Library / Tool | Purpose |
|-----------|---------------|---------|
| Audio capture | PyAudio / PyAudioWPatch | Reads raw PCM audio from the microphone |
| Speech recognition | SpeechRecognition | Wraps the Google Speech Recognition API |
| Recognition engine | Google Speech API or Gemini multimodal | Converts spoken audio to text |
| Microphone selection | SpeechRecognition device enumeration | Prefers PulseAudio on Linux; default mic on Windows |

Calibration is performed once at startup by sampling ambient noise for one second. The energy threshold is fixed after calibration to prevent the recognizer from drifting.

### Text-to-Speech (TTS)

| Component | Library / Tool | Purpose |
|-----------|---------------|---------|
| Voice synthesis | edge-tts | Generates speech using Microsoft Edge neural TTS voices |
| Voice used | en-GB-RyanNeural | British male voice suited to the JARVIS persona |
| MP3 decoding | miniaudio | Pure-Python MP3 decoder; no system tools required |
| Audio output | sounddevice | Streams decoded PCM frames to the system audio device |

The pipeline is fully self-contained: edge-tts generates an MP3 to a temporary file, miniaudio decodes it to raw PCM, and sounddevice streams it to the speakers. No external tools such as mpg123 or ffmpeg are required. espeak-ng is used as an offline fallback only when internet is unavailable (Linux) or Windows SAPI (Windows).

### LLM Brain

| Backend | Environment Variable | Notes |
|---------|---------------------|-------|
| Google Gemini (default) | GEMINI_API_KEY | gemini-2.5-flash, free tier available |
| OpenAI | OPENAI_API_KEY | Model configurable via OPENAI_MODEL |
| Ollama (local) | OLLAMA_API_URL | Fully offline; set OLLAMA_MODEL for model name |

---

## System Requirements

| | Linux | macOS | Windows |
|---|---|---|---|---|
| Python | 3.9+ | 3.9+ | 3.9+ |
| Audio library | libportaudio2 | portaudio (Homebrew) | Included in PyAudio wheel |
| Shell | bash | zsh | cmd.exe / PowerShell |
| Launcher | run.sh | run.sh | run.bat |
| Internet (TTS/STT) | Required for voice | Required for voice | Required for voice |
| Offline brain | Fallback mode | Fallback mode | Fallback mode |
| Offline TTS | espeak-ng | espeak-ng (brew) | espeak-ng |

---

## Installation

### Quick install (recommended for end users)

```bash
pip install jarvis
```

Then create a `.env` file for your API key (see [Configuration](#configuration)) and install the system audio library:

| Platform | One-time setup |
|----------|---------------|
| Linux | `sudo apt install libportaudio2` |
| macOS | `brew install portaudio` |
| Windows | `pip install pipwin && pipwin install pyaudio` |

Then run:

```bash
jarvis                    # voice mode (terminal)
jarvis-web                # web UI at http://0.0.0.0:8080
jarvis --text             # text-only mode
```

### From source (for contributors)

```bash
git clone https://github.com/RehanIlyas-dev/JARVIS.git
cd JARVIS
python -m venv venv
source venv/bin/activate                    # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

Then run with `./run.sh` (Linux/macOS) or `run.bat` (Windows).

#### Per-platform audio setup

**Linux (Debian / Ubuntu):**
```bash
sudo apt install libportaudio2
```

**macOS:**
```bash
brew install portaudio
```

**Windows:**
```powershell
pip install pipwin
pipwin install pyaudio
```

> **If `pipwin install pyaudio` fails**, download the wheel from [https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) and install it manually:
> ```powershell
> pip install path\to\PyAudio‑*.whl
> ```

> **Note:** macOS auto-detects the Built-in Microphone. If detection fails, use `jarvis --text` for text mode. On Windows, the fallback mode auto-detects your OS and runs native PowerShell commands.

---

## Configuration

JARVIS requires at least one LLM API key. Copy `.env.example` to `.env` and fill in your keys:

```bash
# Google Gemini (recommended — fast, free tier available)
GEMINI_API_KEY="your-key-here"

# OpenAI
OPENAI_API_KEY="your-key-here"
OPENAI_MODEL="gpt-4o-mini"          # optional, defaults to gpt-4o-mini

# Local Ollama (fully offline)
OLLAMA_API_URL="http://localhost:11434/v1"
OLLAMA_MODEL="llama3"
```

To persist the key:

- **Linux / macOS:** Add export lines to `~/.bashrc` or `~/.zshrc`
- **Windows (PowerShell):** `[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "your-key-here", "User")`
- **Windows (GUI):** Search for "Edit the system environment variables" and add via the dialog

---

## Usage

### Voice Mode (Terminal)

```bash
./run.sh
```

1. JARVIS boots, calibrates the microphone, and announces readiness.
2. Say **"Jarvis"** followed by a command:
   - "Jarvis, what time is it?"
   - "Jarvis, how much memory do I have?"
   - "Jarvis, list all files in my home directory"
   - "Jarvis, open Firefox"
3. Or say **"Jarvis"** alone and wait for "Yes, Sir?" before speaking.
4. After each response, JARVIS remains active for **30 seconds** for follow-up commands without the wake word.
5. Press `Ctrl+C` to exit.

### Text Mode

```bash
./run.sh --text
```

Type commands at the prompt. JARVIS speaks and prints each response. Type `exit` or `quit` to shut down.

### Web Interface

```bash
./run_web.sh
```

Opens a browser-based chat interface at `http://127.0.0.1:8080` featuring an Iron Man HUD design with real-time system monitoring, voice control, and TTS output. The web UI uses an **always-on microphone** with wake word detection — say "JARVIS" once, then issue commands freely.

### Debug Mode

```bash
./run.sh --verbose
```

Prints full LLM responses and tracebacks to the terminal.

---

## Offline Mode (No API Key)

If no API key is set or the Gemini free-tier quota is exhausted, JARVIS automatically switches to **fallback mode**. No LLM API required.

**Available commands in offline mode:**

| Category | Commands |
|----------|----------|
| Greetings | "Hello", "Hi", "Hey" |
| Navigation | "List files", "Where am I", "Go home", "Go to downloads" |
| File management | "Read file X", "Delete file X", "Create folder X", "Search for X" |
| Applications | "Open Firefox", "Open Chrome", "Open VS Code", "Open terminal", and 15+ more |
| System info | "What time is it", "Memory", "Disk", "IP", "Processes", "System info", "Who am I", "Temperature", "Battery", "Resolution" |
| System controls | "Volume up/down", "Mute", "Lock screen", "Screenshot", "Ping" |
| Git | 60+ git commands: "git status", "commit changes", "create branch", "push changes", etc. |
| Docker | "Docker containers", "Docker images" |

Any safe shell command typed directly also works (e.g., `ls -la`). Destructive commands remain blocked.

---

## Security

- JARVIS executes real shell commands as the current user. Do not run it as root.
- Destructive commands (`rm -rf /`, fork bombs, disk format commands) are permanently blocked.
- Commands such as `shutdown`, `rm -r`, and `passwd` require explicit typed confirmation.
- API keys must be set as environment variables only. Never commit them to version control.


---

## Troubleshooting

### Microphone not detected

```bash
# Install PortAudio (Linux)
sudo apt install libportaudio2

# Verify microphone visibility
source venv/bin/activate
python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"

# Fallback to text mode
./run.sh --text
```

### No audio output

TTS requires internet access for edge-tts. If offline, install the espeak-ng fallback:

```bash
# Linux
sudo apt install espeak-ng

# macOS
brew install espeak

# Windows
# Download from: https://github.com/espeak-ng/espeak-ng/releases
```

### Gemini rate limit (HTTP 429)

The free Gemini tier is limited to ~20 requests/day per model. Options:

- Wait until the daily quota resets (midnight Pacific Time)
- Switch to a paid Gemini plan
- Use OpenAI or a local Ollama model

### macOS

#### Microphone not detected

macOS requires microphone permission for Python processes. Terminal (or your IDE) must be granted access:

1. Open **System Settings → Privacy & Security → Microphone**
2. Ensure **Terminal** (or your app) is enabled
3. Restart JARVIS after changing this setting

If the mic still fails, try the default CoreAudio input:

```bash
# List audio input devices
python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"

# Fallback to text mode
./run.sh --text
```

#### PortAudio not found

```bash
brew install portaudio
pip install --force-reinstall pyaudio
```

#### Gatekeeper blocking edge-tts / Python

If macOS blocks Python from accessing the network or audio:

1. Open **System Settings → Privacy & Security → Files and Folders**
2. Ensure **Terminal** has necessary permissions
3. Or run from a terminal launched directly (not from an IDE)

#### espeak-ng not found (offline TTS)

```bash
brew install espeak-ng
```

### Windows

#### PyAudio installation fails

PyAudio does not ship a pre-built wheel for all Python versions on Windows.

**Option A — pipwin (recommended):**
```powershell
pip install pipwin
pipwin install pyaudio
```

**Option B — Manual wheel:**
1. Download the correct wheel from [https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)
2. Install it: `pip install path\to\PyAudio‑*.whl`

**Option C — PyAudioWPatch (alternative):**
```powershell
pip install PyAudioWPatch
# Then replace pyaudio with pyaudiowpatch in stt.py imports
```

#### PowerShell execution policy blocks scripts

If you see execution policy errors when running `run.ps1`:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Or use `run.bat` (Command Prompt) instead — it doesn't require script execution.

#### Antivirus / Windows Defender flagging JARVIS

JARVIS executes shell commands. Some antivirus software may flag this behavior:

- Add the project folder to your antivirus exclusion list
- Or use **text mode** (`run.bat --text`) which only runs commands you type
- Windows Defender SmartScreen may warn on first run — click **More info → Run anyway**

#### Microphone not working

1. Check **Settings → Privacy & Security → Microphone** — ensure "Let apps access your microphone" is **On**
2. Verify the correct input device is selected in **Sound Settings → Input**
3. If using a laptop, check for a physical microphone mute switch/key (Fn+F4 or similar)

#### Speech recognition stops after a few commands

The free Google Speech API has a ~50 requests/day limit. Once exhausted, recognition silently fails.

**Solution:** Set `GEMINI_API_KEY` in your `.env` file — Gemini has no daily quota and provides more accurate transcription.

```powershell
# Create .env file with your key
echo GEMINI_API_KEY=your-key-here > .env
```

#### No audio output

TTS requires internet for edge-tts. If offline, install espeak-ng:

1. Download from [https://github.com/espeak-ng/espeak-ng/releases](https://github.com/espeak-ng/espeak-ng/releases)
2. Run the installer and ensure `espeak-ng.exe` is in your PATH
3. Restart JARVIS

### Web UI voice not working

- Use **Chrome or Edge** — other browsers lack Web Speech API support.
- Allow microphone permission when prompted by the browser.
- Click the microphone button in the input bar to toggle voice on/off.
- Ensure the correct microphone is selected in browser site settings.

---

## CI/CD

Every push and pull request triggers **GitHub Actions** (`.github/workflows/ci.yml`):

| Job | Runners | What it does |
|-----|---------|-------------|
| **lint** | ubuntu | `py_compile` checks all source files for syntax errors |
| **test** | ubuntu / macos / windows × Python 3.9–3.12 | Runs the 90-test cross-platform suite (`pytest tests/`) — verifies every fallback command is correct for Linux, macOS, and Windows |
| **build** | ubuntu | Creates a pip-installable wheel and source distribution |
| **publish** | ubuntu (tags only) | On `v*` tags: builds, publishes to PyPI, and creates a GitHub Release with release notes |

To trigger a release:
```bash
git tag v1.1.0
git push origin v1.1.0
```

The `publish` job requires a `PYPI_API_TOKEN` secret in your GitHub repository settings. Without it, the build step still runs but publishing is skipped.

---

## Contributing

### Setup

```bash
git clone https://github.com/RehanIlyas-dev/JARVIS.git
cd JARVIS
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
```

### Running tests

```bash
pytest tests/ -v
```

The test suite requires no API keys, no microphone, and no internet. It validates the offline fallback command matcher across all three platforms (Linux, macOS, Windows) — 90 test cases total.


### Submitting changes

1. **Fork** the repo on GitHub
2. **Clone** your fork and create a branch:
   ```bash
   git clone https://github.com/YOUR_USERNAME/JARVIS.git
   cd JARVIS
   git checkout -b your-feature-branch
   ```
3. **Install and verify** the existing tests pass:
   ```bash
   python -m venv venv && source venv/bin/activate
   pip install -e ".[dev]"
   pytest tests/
   ```
4. **Make your changes** — keep functions short, match the surrounding style, and add platform-specific branches (`_IS_WINDOWS`, `_IS_MAC`) for any new system commands
5. **Run `pytest tests/`** again — all 90 tests must pass
6. **Push** your branch and open a Pull Request to the `main` branch

The CI pipeline will automatically run your PR against Linux, macOS, and Windows across Python 3.9–3.12. All checks must pass before merging.

---

## Acknowledgments

- **Google Gemini** — LLM for natural language understanding and command generation
- **edge-tts** — Microsoft Edge neural TTS for high-quality voice synthesis
- **SpeechRecognition** — Google Speech API for speech-to-text
- **PyAudio** / **PyAudioWPatch** — Cross-platform audio I/O
- **miniaudio** — In-process MP3 decoding
- **sounddevice** — Audio output streaming
- **Flask** — Web framework for the browser interface
