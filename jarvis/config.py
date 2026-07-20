import os
from typing import Final

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Maximum LLM->command->result iterations per user turn (prevents infinite loops)
MAX_AGENTIC_ITERATIONS: Final[int] = int(os.getenv("MAX_AGENTIC_ITERATIONS", "8"))

# Number of consecutive STT failures before prompting the user to check microphone
STT_FAIL_THRESHOLD: Final[int] = int(os.getenv("STT_FAIL_THRESHOLD", "4"))

# Seconds of silence before the active follow-up window expires
ACTIVE_SECS: Final[int] = int(os.getenv("ACTIVE_SECS", "30"))

# Maximum history messages kept in memory
HISTORY_LIMIT: Final[int] = int(os.getenv("HISTORY_LIMIT", "40"))

# How many history messages to send to the API each turn
CONTEXT_WINDOW: Final[int] = int(os.getenv("CONTEXT_WINDOW", "10"))

# Flask web interface
FLASK_HOST: Final[str] = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT: Final[int] = int(os.getenv("FLASK_PORT", "5000"))
