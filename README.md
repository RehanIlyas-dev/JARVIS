# J.A.R.V.I.S. - Just A Rather Very Intelligent System

A fully voice-controlled personal AI assistant with system access, built in Python.

## Features

- **Voice Input**: Listens to your commands via microphone (Google Speech Recognition)
- **Voice Output**: Speaks responses back using `pyttsx3` (offline, no API needed)
- **Wake Word**: Activate by saying "Jarvis" (passive listening mode)
- **System Access**: Can execute any shell command on your machine
- **Agentic Loop**: Runs commands, reads output, and iterates until the task is complete
- **Multiple LLM Backends**: Supports Google Gemini, OpenAI, or Local Ollama
- **Text Mode Fallback**: Type commands if microphone is unavailable

## Project Structure

```
~/jarvis/
├── main.py              # Main orchestrator (entry point)
├── stt.py               # Speech-to-Text module
├── tts.py               # Text-to-Speech module
├── brain.py             # LLM integration (Gemini / OpenAI / Ollama)
├── system_agent.py      # Shell command execution engine
├── run.sh               # Quick launcher script
├── requirements.txt     # Python dependencies
└── venv/                # Python virtual environment
```

## Quick Start

### 1. Set Up an API Key (Choose ONE)

JARVIS needs an LLM brain. Set ONE of these environment variables:

```bash
# Option A: Google Gemini (Recommended - Fast & Free Tier Available)
export GEMINI_API_KEY="your-gemini-api-key-here"
# Get one at: https://aistudio.google.com/apikey

# Option B: OpenAI
export OPENAI_API_KEY="your-openai-api-key-here"

# Option C: Local Ollama (Fully Offline)
export OLLAMA_API_URL="http://localhost:11434/v1"
export OLLAMA_MODEL="llama3"
```

To make it persistent, add the export line to your `~/.bashrc` or `~/.zshrc`.

### 2. Run JARVIS

```bash
# Voice mode (default)
cd ~/jarvis
./run.sh

# Text terminal mode
./run.sh --text
```

### 3. Voice Mode Usage

1. JARVIS starts listening for the wake word: **"Jarvis"**
2. Say **"Jarvis"** followed by your command, e.g.:
   - "Jarvis, what time is it?"
   - "Jarvis, list all python files in my home directory"
   - "Jarvis, check my system memory usage"
   - "Jarvis, open Firefox"
3. Or just say **"Jarvis"** alone, and JARVIS will say "Yes, Sir?" then listen for your next command.
4. Press `Ctrl+C` to exit.

### 4. Text Mode Usage

Just type your command and press Enter. JARVIS will speak and display the response.
Type `exit` or `quit` to shut down.

## Example Commands

| You Say | JARVIS Does |
|---------|-------------|
| "What time is it?" | Runs `date` and speaks the time |
| "List my files" | Runs `ls -la` and reads them out |
| "How much memory do I have?" | Runs `free -h` and reports |
| "Find all images on my desktop" | Runs `find` and lists them |
| "Create a new Python project" | Runs `mkdir` + `touch` to scaffold |
| "What's my IP address?" | Runs `hostname -I` and reports |
| "Run my script" | Executes the script and reports output |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Microphone  │────>│  STT Module  │────>│  Wake Word  │
│  (PyAudio)   │     │  (Google)    │     │  Detection  │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
                                        ┌────────▼────────┐
                                        │   LLM Brain     │
                                        │  (Gemini/OAI/   │
                                        │   Ollama)       │
                                        └───┬────────┬────┘
                                            │        │
                              ┌─────────────▼─┐  ┌──▼──────────────┐
                              │  TTS Speaker  │  │  System Agent   │
                              │  (pyttsx3)    │  │  (subprocess)   │
                              └───────────────┘  └───────┬─────────┘
                                                         │
                                                  ┌──────▼───────┐
                                                  │  Shell/Bash  │
                                                  │  Commands    │
                                                  └──────────────┘
```

## System Requirements

- **OS**: Linux (tested), macOS, Windows
- **Python**: 3.8+
- **Audio**: `portaudio19-dev` (Linux) for microphone input
- **Speakers**: Required for TTS output

## Troubleshooting

### No microphone detected
```bash
# Install PortAudio (Debian/Ubuntu)
sudo apt install portaudio19-dev python3-pyaudio

# Or run in text mode instead
./run.sh --text
```

### TTS not speaking
```bash
# Install espeak (Linux)
sudo apt install espeak espeak-data
```

### Gemini API errors
- Ensure `GEMINI_API_KEY` is set and valid
- Test with: `echo $GEMINI_API_KEY`
