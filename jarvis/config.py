# ---------------------------------------------------------------------------
# J.A.R.V.I.S. — Central configuration constants
# ---------------------------------------------------------------------------
# Single source of truth for hardcoded values used across the application.
# Import these instead of defining them in individual files.

from typing import Final

# Maximum LLM->command->result iterations per user turn (prevents infinite loops)
MAX_AGENTIC_ITERATIONS: Final[int] = 8

# Number of consecutive STT failures before prompting the user to check microphone
STT_FAIL_THRESHOLD: Final[int] = 4

# Seconds of silence before the active follow-up window expires
ACTIVE_SECS: Final[int] = 30

# Maximum history messages kept in memory
HISTORY_LIMIT: Final[int] = 40

# How many history messages to send to the API each turn
CONTEXT_WINDOW: Final[int] = 10

# Flask web interface
FLASK_HOST: Final[str] = "127.0.0.1"
FLASK_PORT: Final[int] = 5000
