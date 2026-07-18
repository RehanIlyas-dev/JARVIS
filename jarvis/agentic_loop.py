# ---------------------------------------------------------------------------
# Shared agentic loop — the LLM→command→result iteration used by both
# main.py (voice/text TUI) and web_app.py (SSE-over-HTTP).
#
# Exposes a generator so each consumer can wrap the events with their own
# presentation layer (TTS + print vs. Server-Sent Events).
# ---------------------------------------------------------------------------

from typing import Any, Dict, Generator, Optional

from .config import MAX_AGENTIC_ITERATIONS


def generate_agentic_loop(
    brain: Any,
    system_agent: Any,
    user_message: str,
    max_iterations: Optional[int] = None,
) -> Generator[Dict[str, Any], None, None]:
    """
    Generator that yields structured event dicts for each step of the
    agentic (LLM → command → result) loop.

    The caller iterates over these events and handles side effects
    (speaking, SSE frames, logging, etc.).  The loop itself is driven
    entirely inside this generator.

    Parameters
    ----------
    brain : JarvisBrain
    system_agent : SystemAgent
    user_message : str
        The user's input for this turn.
    max_iterations : int or None
        Override for ``MAX_AGENTIC_ITERATIONS`` (from config).

    Yields
    ------
    dict
        Every dict has at least a ``"type"`` key.
        Possible types:

        ``"status"``
            {"type": "status", "state": str, "label": str}
        ``"assistant_response"``
            {"type": "assistant_response", "content": str, "iteration": int}
        ``"command"``
            {"type": "command", "content": str, "iteration": int}
        ``"command_output"``
            {"type": "command_output", "status": str, "exit_code": int,
             "stdout": str, "stderr": str, "iteration": int}
        ``"done"``
            {"type": "done"}
        ``"error"``
            {"type": "error", "content": str}
    """
    if max_iterations is None:
        max_iterations = MAX_AGENTIC_ITERATIONS

    current_message = user_message

    try:
        for iteration in range(1, max_iterations + 1):
            yield {
                "type": "status",
                "state": "thinking",
                "label": "ANALYZING QUERY...",
            }

            response = brain.get_response(current_message)

            if not response or not response.strip():
                yield {"type": "status", "state": "thinking", "label": "PROCESSING COMPLETE"}
                break

            cmd_to_run = brain.extract_command(response)
            speech_text = brain.clean_speech_text(response)

            if speech_text:
                yield {
                    "type": "assistant_response",
                    "content": speech_text,
                    "iteration": iteration,
                }

            if cmd_to_run:
                yield {
                    "type": "command",
                    "content": cmd_to_run,
                    "iteration": iteration,
                }
                yield {
                    "type": "status",
                    "state": "executing",
                    "label": f"EXECUTING: {cmd_to_run}",
                }

                exec_result = system_agent.execute_command(cmd_to_run)

                yield {
                    "type": "command_output",
                    "status": exec_result["status"],
                    "exit_code": exec_result["exit_code"],
                    "stdout": exec_result["stdout"],
                    "stderr": exec_result["stderr"],
                    "iteration": iteration,
                }

                # Build result string efficiently — avoid repeated .get_cwd() calls
                cwd = system_agent.get_cwd()
                current_message = (
                    "[System Execution Result]\n"
                    f"Status: {exec_result['status']}\n"
                    f"Exit Code: {exec_result['exit_code']}\n"
                    f"STDOUT:\n{exec_result['stdout']}\n"
                    f"STDERR:\n{exec_result['stderr']}\n"
                    "[/System Execution Result]\n"
                    f"CWD: {cwd}"
                )

                if iteration == max_iterations:
                    yield {
                        "type": "assistant_response",
                        "content": "I have reached my maximum command iterations for this turn, Sir.",
                        "iteration": iteration,
                    }
                    break
            else:
                # No command — the response is the final answer
                break

        yield {"type": "done"}

    except Exception as e:
        yield {"type": "error", "content": str(e)}
