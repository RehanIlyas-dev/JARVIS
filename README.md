# JARVIS - Just A Rather Very Intelligent System

A fully voice-controlled personal AI assistant with full system access, built in Python for Linux. Powered by Google's Gemini, Antigravity and Big Pickle.
JARVIS listens for a wake word, processes natural language via a large language model, executes
shell commands autonomously, and speaks responses aloud using a high-quality neural voice.

---

## Features

- **Wake Word Detection** — Passive listening mode activated by saying "JARVIS"
- **Always-On Voice (Web UI)** — Say "JARVIS" once, JARVIS responds "Yes, Sir?", then stays in command mode indefinitely for follow-up commands
- **Active Follow-Up Window (Terminal)** — After each response, JARVIS stays active for 30 seconds to accept follow-up commands without repeating the wake word
- **Speech-to-Text** — Microphone input processed via Google Speech Recognition (SpeechRecognition + PyAudio)
- **Text-to-Speech** — High-quality British neural voice via Microsoft Edge TTS (edge-tts), decoded in-process using miniaudio and streamed through PyAudio
- **Agentic Loop** — Runs shell commands, reads the output, and iterates up to 8 times per turn to complete multi-step tasks autonomously
- **Multiple LLM Backends** — Supports Google Gemini, OpenAI, or a locally-hosted Ollama model
- **Safety Guardrails** — Hard-blocks destructive commands (fork bombs, disk wipes) and requires typed confirmation for dangerous operations (shutdown, rm -r, etc.)
- **Persistent Working Directory** — cd commands persist across turns; the brain always knows the current directory
- **Text Mode** — Full functionality via keyboard if microphone is unavailable
- **Web Interface** — Optional browser-based chat UI served via Flask with Iron Man HUD design

---

## Technology Stack

### Speech-to-Text (STT)

| Component | Library / Tool | Purpose |
|-----------|---------------|---------|
| Audio capture | PyAudio | Reads raw PCM audio from the microphone |
| Speech recognition | SpeechRecognition | Wraps the Google Speech Recognition API |
| Recognition engine | Google Speech API (cloud) | Converts spoken audio to text |
| Microphone selection | SpeechRecognition device enumeration | Prefers PulseAudio device for stability on Linux |

Calibration is performed once at startup by sampling ambient noise for one second. The energy
threshold is fixed after calibration to prevent the recognizer from drifting and requiring
progressively louder speech over time.

### Text-to-Speech (TTS)

| Component | Library / Tool | Purpose |
|-----------|---------------|---------|
| Voice synthesis | edge-tts | Generates speech using Microsoft Edge neural TTS voices |
| Voice used | en-GB-RyanNeural | British male voice suited to the JARVIS persona |
| MP3 decoding | miniaudio | Pure-Python MP3 decoder; no system tools required |
| Audio output | PyAudio | Streams decoded PCM frames to the system audio device |
| ALSA noise suppression | ctypes + libasound | Silences harmless ALSA/JACK probe messages at startup |

The pipeline is fully self-contained: edge-tts generates an MP3 to a temporary file,
miniaudio decodes it to raw PCM, and PyAudio streams it to the speakers. No external
tools such as mpg123, ffmpeg, or espeak are required. espeak-ng is used as an offline
fallback only when internet access is unavailable.

### LLM Brain

| Backend | Environment Variable | Notes |
|---------|---------------------|-------|
| Google Gemini (default) | GEMINI_API_KEY | gemini-2.5-flash, free tier available |
| OpenAI | OPENAI_API_KEY | Model configurable via OPENAI_MODEL |
| Ollama (local) | OLLAMA_API_URL | Fully offline; set OLLAMA_MODEL for the model name |

---

## Project Structure

```
jarvis/
├── jarvis/              # Core Python package namespace
│   ├── __init__.py      # Package initializer
│   ├── main.py          # Entry point — voice loop, text loop, agentic orchestration
│   ├── brain.py         # LLM integration (Gemini / OpenAI / Ollama), fallback mode
│   ├── stt.py           # Speech-to-Text (PyAudio + Google Speech Recognition)
│   ├── tts.py           # Text-to-Speech (edge-tts + miniaudio + PyAudio)
│   ├── system_agent.py  # Shell command execution, safety guardrails, cd tracking
│   ├── web_app.py       # Optional Flask web interface with SSE streaming
│   ├── templates/       # Flask HTML templates
│   └── static/          # Web interface assets (CSS/JS)
├── pyproject.toml       # Modern Python packaging configuration
├── .env.example         # Template configuration file
├── run.sh               # Voice mode launcher script
├── run_web.sh           # Web interface launcher script
├── requirements.txt     # Python dependencies list
└── venv/                # Python virtual environment
```

---

## System Requirements

| | Linux | macOS | Windows |
|---|---|---|---|
| Python | 3.9+ | 3.9+ | 3.9+ |
| Audio library | libportaudio2 | portaudio (via Homebrew) | Included in PyAudio wheel |
| Shell | bash | bash | cmd.exe / PowerShell |
| Launcher | run.sh | run.sh | run.bat |
| Internet (TTS/STT) | Required for voice | Required for voice | Required for voice |
| Offline brain | Fallback mode (no API key needed) | Fallback mode | Fallback mode |
| Offline TTS | espeak-ng (`sudo apt install espeak-ng`) | espeak-ng (`brew install espeak`) | espeak-ng |
| Offline STT | Not available — use text mode | Not available — use text mode | Not available — use text mode |

---

## Installation

### Linux (Debian / Ubuntu)

```bash
# 1. Clone the repository
git clone https://github.com/RehanIlyas-dev/JARVIS.git
cd JARVIS

# 2. Install system audio dependency
sudo apt install libportaudio2

# 3. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Run JARVIS
./run.sh
```

### macOS

```bash
# 1. Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install PortAudio (required for PyAudio)
brew install portaudio

# 3. Clone the repository
git clone https://github.com/RehanIlyas-dev/JARVIS.git
cd JARVIS

# 4. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 5. Install Python dependencies
pip install -r requirements.txt

# 6. Run JARVIS
./run.sh
```

Note: macOS uses different microphone device names than Linux. JARVIS will attempt to auto-detect
your Built-in Microphone. If detection fails, run in text mode with `./run.sh --text`.

### Windows

Windows support requires a few extra steps because PyAudio does not ship a pre-built wheel
for recent Python versions on Windows and the default launcher is a `.bat` file.

```powershell
# 1. Install Python 3.9 or later from https://www.python.org/downloads/
#    During install, check "Add Python to PATH"

# 2. Clone the repository (requires Git for Windows: https://git-scm.com)
git clone https://github.com/RehanIlyas-dev/JARVIS.git
cd JARVIS

# 3. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# 4. Install PyAudio via a pre-built wheel
#    Download the correct wheel from: https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio
#    Example for Python 3.11 64-bit:
pip install PyAudio-0.2.14-cp311-cp311-win_amd64.whl

# 5. Install remaining dependencies
pip install -r requirements.txt

# 6. Create run.bat (one-time setup)
copy NUL run.bat
```

Paste the following into `run.bat`:

```bat
@echo off
call "%~dp0venv\Scripts\activate.bat"
python "%~dp0main.py" %*
```

Then run JARVIS:

```bat
run.bat --text
```

Note: Voice mode works on Windows. However, the system commands that JARVIS is taught
(`ls`, `free -h`, `df -h`, etc.) are Linux/macOS commands. When using the Gemini or
OpenAI backend the LLM will receive your OS name in the system prompt and should
adapt its commands to Windows equivalents (`dir`, `tasklist`, `ipconfig`, etc.).
The offline fallback mode is not adapted for Windows and will only run safe read-only
commands correctly.

---

## Configuration

JARVIS requires at least one LLM API key. Set one of the following environment variables:

```bash
# Google Gemini (recommended — fast, free tier available)
export GEMINI_API_KEY="your-key-here"
# Obtain a key at: https://aistudio.google.com/apikey

# OpenAI
export OPENAI_API_KEY="your-key-here"
export OPENAI_MODEL="gpt-4o-mini"          # optional, defaults to gpt-4o-mini

# Local Ollama (fully offline)
export OLLAMA_API_URL="http://localhost:11434/v1"
export OLLAMA_MODEL="llama3"
```

To make the key permanent:

- **Linux / macOS**: Add the export line to `~/.bashrc` or `~/.zshrc`
- **Windows (PowerShell)**: Use `[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "your-key-here", "User")`
- **Windows (System Settings)**: Search for "Edit the system environment variables" and add it via the GUI

---

## Usage

### Voice Mode (Terminal)

```bash
./run.sh
```

1. JARVIS boots, calibrates the microphone, and announces readiness.
2. Say **"Jarvis"** followed by a command, for example:
   - "Jarvis, what time is it?"
   - "Jarvis, how much memory do I have?"
   - "Jarvis, list all files in my home directory"
   - "Jarvis, open Firefox"
3. Or say **"Jarvis"** alone and wait for "Yes, Sir?" before speaking your command.
4. After each response, JARVIS remains active for **30 seconds** for follow-up commands without requiring the wake word again.
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

Opens a browser-based chat interface at `http://127.0.0.1:5000`. The web UI features an Iron Man HUD design with real-time system monitoring, voice control, and edge-tts speech output.

#### First Launch

1. Run `./run_web.sh` and open `http://127.0.0.1:5000` in **Chrome or Edge** (required for Web Speech API).
2. You'll see a splash screen with an arc reactor animation. Click **ACTIVATE SYSTEMS** to start.
3. The system boots with an animated sequence and JARVIS greets you with a time-appropriate message spoken aloud.

#### Voice Commands (Web UI)

The web UI uses an **always-on microphone** with wake word detection:

1. **Say "JARVIS"** — JARVIS responds "Yes, Sir?" and enters **command mode** (green indicator).
2. **Speak your command** — e.g., "list files", "what time is it", "check disk space".
3. JARVIS processes the command, speaks the response, and **stays in command mode**.
4. **Speak your next command** — no need to say "JARVIS" again.
5. Repeat as many commands as you like — the mic stays active the entire session.

#### Visual Indicators

| State | Indicator | Meaning |
|-------|-----------|---------|
| Green pulse | "VOICE ACTIVE — Say JARVIS" | Listening for wake word |
| Blue pulse | "COMMAND MODE — Speak your command" | Ready for your command |
| Waveform | Audio bars animating | JARVIS is speaking |

#### Keyboard Input (Web UI)

You can also type commands at the bottom input bar. Type your command and press Enter or click the send button. Voice stays active in the background.

#### Quick Commands

Click the preset buttons on the right panel for common tasks:
- **List Files** — Shows directory contents
- **System Info** — Displays OS and CPU details
- **Check Memory** — Shows RAM usage
- **Disk Space** — Reports storage usage
- **Who Am I** — Shows current user
- **Network** — Displays IP and network info

#### System Monitoring

The left panel shows real-time system metrics updated every 3 seconds:
- **CPU Usage** — Live graph with percentage
- **RAM** — Used / total with progress bar
- **Disk** — Used / total with progress bar
- **Working Directory** — Current JARVIS cwd

### Debug Mode

```bash
./run.sh --verbose
```

Prints the full LLM responses and any tracebacks to the terminal.

### Offline Mode (No API Key)

If no API key is set, JARVIS runs in **fallback mode** with a built-in command matcher. No LLM API required. Say the wake word and command as usual, or type them in text mode.

**What works offline:**
- **Brain**: Built-in command matcher handles 50+ commands without any API
- **TTS**: Falls back to `espeak-ng` (robotic but functional). Install with `sudo apt install espeak-ng`
- **Text mode**: Fully offline — type commands directly

**What needs internet offline:**
- **STT (Voice input)**: Uses Google Speech Recognition API — requires internet. There is no offline STT fallback in the terminal version. Use text mode (`./run.sh --text`) if offline.
- **Web UI voice**: Uses browser's Web Speech API — also requires internet.

**Tip**: In a fully offline environment, use text mode: `./run.sh --text`

#### Greetings

| Command | Action |
|---------|--------|
| "Hello" / "Hi" / "Hey" | JARVIS greets you and confirms offline mode |

#### Navigation & Files

| Command | Action |
|---------|--------|
| "List files" / "Show me" / "What's in" | `ls -la` |
| "Where am I" / "Working directory" | `pwd` |
| "Go home" | `cd ~` |
| "Go to downloads" | `cd ~/Downloads` |
| "Go to documents" | `cd ~/Documents` |
| "Go to desktop" | `cd ~/Desktop` |
| "Read file X" / "Show file X" | `cat X` |
| "Delete file X" / "Remove file X" | `rm -i X` (with confirmation) |
| "Create folder X" / "Make directory X" | `mkdir -p X` |
| "Search for X" / "Find X" | `find . -iname '*X*' -maxdepth 3` |

#### Applications

| Command | Action |
|---------|--------|
| "Open Firefox" / "Browser" | Launches Firefox |
| "Open Chrome" | Launches Google Chrome |
| "Open Brave" | Launches Brave Browser |
| "Open VS Code" / "Open code" | Launches VS Code |
| "Open Sublime" | Launches Sublime Text |
| "Open PyCharm" | Launches PyCharm |
| "Open Slack" | Launches Slack |
| "Open Discord" | Launches Discord |
| "Open Telegram" | Launches Telegram |
| "Open Spotify" / "Music" | Launches Spotify |
| "Open terminal" / "Console" | Opens a terminal window |
| "Open file manager" / "Open files" | Opens the file manager |
| "Open calculator" / "Calc" | Opens the calculator |
| "Open system monitor" | Opens System Monitor |
| "Open notepad" / "Text editor" | Opens the text editor |

#### System Info

| Command | Action |
|---------|--------|
| "What time is it" / "Date" | `date` |
| "Memory" / "RAM" / "How much memory" | `free -h` |
| "Disk" / "Storage" / "Space" | `df -h` |
| "IP" / "Network" / "Internet" | `hostname -I && ip route` |
| "Processes" / "What's running" | `ps aux --sort=-%mem \| head -15` |
| "System info" / "Machine" | `uname -a && lscpu` |
| "Who am I" / "My user" | `whoami && id` |
| "Temperature" / "CPU temp" | `sensors` or `/sys/class/thermal` |
| "Battery" / "Charge" / "Power status" | `upower` or `acpi` |
| "Sound status" / "Audio devices" | `aplay -l && arecord -l` |
| "Resolution" / "Screen size" | `xrandr` |
| "Weather" / "Forecast" | `curl wttr.in` |

#### System Controls

| Command | Action |
|---------|--------|
| "Volume up" / "Louder" | `amixer sset Master 10%+` |
| "Volume down" / "Quieter" | `amixer sset Master 10%-` |
| "Mute" / "Unmute" / "Toggle sound" | `amixer sset Master toggle` |
| "Lock screen" | Locks the screen |
| "Screenshot" / "Screen capture" | Takes a screenshot |
| "Ping" / "Check internet" | `ping -c 3 google.com` |

#### Git & Docker

| Command | Action |
|---------|--------|
| "Git status" / "Repo status" | `git status` |
| "Git log" / "Commits" | `git log -n 5 --oneline` |
| "Git branch" / "Branches" | `git branch -a` |
| "Docker containers" / "Docker status" | `docker ps -a` |
| "Docker images" | `docker images` |

#### Other

| Command | Action |
|---------|--------|
| "Help" / "What can you do" | Lists available capabilities |
| "Thanks" / "Thank you" | JARVIS acknowledges |
| "Goodbye" / "Shutdown" | JARVIS signs off |

In offline mode, JARVIS can also run any safe shell command directly (e.g., typing `ls -la` or `whoami`). Destructive commands are still blocked.

### Git Commands (Offline Mode)

JARVIS understands **60+ git commands** with natural language. Say them or type them directly.

| Category | Examples |
|----------|----------|
| Basic | "git init", "clone repo [URL]", "git status" |
| Staging | "stage all", "stage [file]", "unstage", "remove file [file]" |
| Committing | "commit changes", "commit [message]", "amend commit" |
| Branching | "list branches", "create branch [name]", "switch to [branch]", "merge [branch]", "delete branch [name]" |
| Remote | "list remotes", "add remote [name] [URL]", "rename remote [old] to [new]" |
| Fetching & Pulling | "git fetch", "git pull" |
| Pushing | "push changes", "force push", "push all branches", "push tags" |
| Stashing | "stash changes", "unstash", "apply stash", "list stashes", "stash to branch [name]" |
| Inspecting | "git log", "log graph", "git diff", "who wrote [file]", "contributors", "recent activity" |
| Tagging | "list tags", "create tag [name]", "delete tag [name]" |
| Undoing | "undo last commit", "revert commit", "discard changes", "hard reset" |
| Advanced | "cherry-pick [commit]", "rebase [branch]", "update submodules", "count commits", "verify repo" |
| Config | "show config", "set user name [name]", "set user email [email]" |

Any raw git command typed directly also works (e.g., `git log --oneline --graph`).

---

## Example Commands

| Voice Command | Action |
|--------------|--------|
| "What time is it?" | Runs `date` and speaks the result |
| "List my files" | Runs `ls -la` and reports contents |
| "How much memory do I have?" | Runs `free -h` and reads the output |
| "What is my IP address?" | Runs `hostname -I` and reports |
| "Find all images on my desktop" | Runs `find` and lists matches |
| "Create a folder called projects" | Runs `mkdir -p projects` |
| "Open Firefox" | Launches Firefox in the background |
| "Check disk space" | Runs `df -h` and reports |
| "What processes are running?" | Runs `ps aux` and summarizes |

---

## Architecture

```
Microphone (PyAudio)
        |
        v
SpeechRecognition + Google Speech API
        |
        v
Wake Word Detection ("jarvis")
        |
        v
    LLM Brain  <----  System Prompt (cwd, OS, directory listing)
   (Gemini /             |
  OpenAI /            <run> command extracted
   Ollama)                |
        |                 v
        |         SystemAgent.execute_command()
        |           (safety check, cd tracking,
        |            subprocess.run with cwd)
        |                 |
        +----  Result fed back to LLM
        |      (loop up to 8 iterations)
        |
        v
edge-tts  -->  miniaudio  -->  PyAudio  -->  Speakers
```

---

## Future Enhancements & Roadmap

- **Local Wake Word Engine**: Integrate `openWakeWord` or `Porcupine` to handle local wake-word detection with higher accuracy and minimal CPU overhead.
- **Local STT / TTS**: Support fully local speech-to-text (e.g., `whisper.cpp` or `faster-whisper`) and local text-to-speech (e.g., `kokoro` or `piper`) for a completely offline voice assistant.
- **Home Automation Integration**: Expand the system agent with integrations for Home Assistant, smart devices, and IoT peripherals.
- **Containerization**: Add a Dockerfile supporting audio device passthrough to isolate JARVIS's workspace.

---

## Troubleshooting

### Microphone not detected

```bash
# Install PortAudio
sudo apt install libportaudio2

# Verify PyAudio can see your microphone
source venv/bin/activate
python -c "import speech_recognition as sr; print(sr.Microphone.list_microphone_names())"

# If no microphone is available, use text mode
./run.sh --text
```

### No audio output

The TTS pipeline requires internet access to generate speech via edge-tts. If internet
is unavailable, install the espeak-ng fallback:

```bash
sudo apt install espeak-ng
```

### Gemini rate limit error (429)

The free tier of the Gemini API is limited to 20 requests per day per model. Options:

- Wait until the daily quota resets (midnight Pacific Time)
- Switch to a paid Gemini plan
- Use OpenAI or a local Ollama model instead

### API key not found

```bash
# Verify the key is set in the current shell
echo $GEMINI_API_KEY

# If empty, export it and re-run
export GEMINI_API_KEY="your-key-here"
./run.sh
```

### Web UI voice not working

- Use **Chrome or Edge** — other browsers don't support the Web Speech API.
- The browser will ask for microphone permission on first use. Click **Allow**.
- If the mic indicator stays grey, click the microphone button in the input bar to toggle voice on/off.
- Make sure your microphone is selected in the browser: click the camera/mic icon in the address bar.

### Web UI audio not playing

- Click **ACTIVATE SYSTEMS** on the splash screen first — browsers block auto-playing audio without user interaction.
- If TTS fails silently, check your internet connection (edge-tts requires network access).
- Look at the browser console (F12) for any error messages.

### Web UI command not responding to voice

- Say **"JARVIS"** clearly and wait for "Yes, Sir?" before speaking your command.
- The mic stays in command mode after the first wake word — no need to repeat "JARVIS".
- Speak clearly and at a normal pace. The Web Speech API works best with clear enunciation.
- Check the listening bar at the bottom for live transcript feedback.

---

## Security Notes

- JARVIS executes real shell commands as the current user. Do not run it as root.
- A set of destructive commands (rm -rf /, fork bombs, disk format commands) are permanently blocked regardless of LLM output.
- Commands such as shutdown, rm -r, and passwd require explicit typed confirmation before execution.
- API keys should be set as environment variables only. Never commit them to version control.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **Google Gemini** — Powerful LLM for natural language understanding and command generation
- **edge-tts** — Microsoft Edge neural TTS for high-quality voice synthesis
- **SpeechRecognition** — Google Speech API for reliable speech-to-text
- **PyAudio** — Cross-platform audio I/O for microphone input and TTS output
- **miniaudio** — In-process MP3 decoding without external tools
- **Flask** — Web framework for the optional browser interface
- **CSS Battle** — HTML/CSS template designs from the CSS Battle community
