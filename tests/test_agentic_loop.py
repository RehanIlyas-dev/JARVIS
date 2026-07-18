#!/usr/bin/env python3
"""
Unit tests for jarvis/agentic_loop.py — test the generator:
  - Regular flow (response → command → output → done)
  - Iteration cap
  - Empty responses
  - No command (final answer)
  - Error handling
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock
from jarvis.agentic_loop import generate_agentic_loop


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_brain(get_response=None, extract_command=None, clean_speech_text=None):
    brain = MagicMock()
    brain.get_response.side_effect = get_response or (lambda msg: "Hello, Sir.")
    brain.extract_command.side_effect = extract_command or (lambda resp: None)
    brain.clean_speech_text.side_effect = clean_speech_text or (lambda resp: resp)
    return brain


def _make_system_agent(execute_return=None):
    agent = MagicMock()
    agent.execute_command.return_value = execute_return or {
        "status": "success", "exit_code": 0, "stdout": "ok", "stderr": "",
    }
    agent.get_cwd.return_value = "/home/test"
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBasicFlow:
    """Happy path: normal response, command, output cycle."""

    def _make_one_shot_brain(self, response, cmd, speech):
        """Brain that returns a command on first call, then empty response (no cmd) on subsequent calls."""
        call_count = [0]

        def get_response(msg):
            call_count[0] += 1
            if call_count[0] == 1:
                return response
            return ""  # empty response stops the loop

        def extract_command(resp):
            if call_count[0] == 1:
                return cmd
            return None

        def clean_speech_text(resp):
            if call_count[0] == 1:
                return speech
            return ""

        return _make_brain(
            get_response=get_response,
            extract_command=extract_command,
            clean_speech_text=clean_speech_text,
        )

    def test_single_command_no_speech(self):
        """Response has a command but no speech text."""
        brain = self._make_one_shot_brain(
            response="Doing it. <run>echo hello</run>",
            cmd="echo hello",
            speech="Doing it.",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        # After the command, the loop iterates again with the result,
        # gets an empty response, yields a "PROCESSING COMPLETE" status, then done.
        assert types[:5] == ["status", "assistant_response", "command",
                             "status", "command_output"]
        assert types[-2] == "status"  # PROCESSING COMPLETE
        assert types[-1] == "done"

    def test_single_command_no_speech_text_empty_after_clean(self):
        """clean_speech_text returns empty string — no assistant_response yielded."""
        brain = self._make_one_shot_brain(
            response="<run>ls</run>",
            cmd="ls",
            speech="",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        # No "assistant_response" because speech_text is empty
        assert "assistant_response" not in types
        assert "command" in types
        assert "command_output" in types

    def test_final_answer_no_command(self):
        """Response is a final answer — no command extracted."""
        brain = _make_brain(
            get_response=lambda msg: "That is all, Sir.",
            extract_command=lambda resp: None,
            clean_speech_text=lambda resp: "That is all, Sir.",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        assert types == ["status", "assistant_response", "done"]

    def test_command_and_speech_both_present(self):
        """Both speech and command appear."""
        brain = self._make_one_shot_brain(
            response="Listing files. <run>ls -la</run>",
            cmd="ls -la",
            speech="Listing files.",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        # First 5 events are the main cycle, then PROCESSING COMPLETE, then done
        assert types[:5] == ["status", "assistant_response", "command",
                             "status", "command_output"]
        assert types[-2] == "status"
        assert types[-1] == "done"
        # Check data
        asst = [e for e in events if e["type"] == "assistant_response"]
        assert len(asst) >= 1
        assert asst[0]["content"] == "Listing files."
        cmd = [e for e in events if e["type"] == "command"][0]
        assert cmd["content"] == "ls -la"
        co = [e for e in events if e["type"] == "command_output"][0]
        assert co["stdout"] == "ok"
        assert co["exit_code"] == 0
        assert co["status"] == "success"

    def test_status_events_have_correct_labels(self):
        """Status events carry thinking/executing state."""
        brain = _make_brain(
            get_response=lambda msg: "Running. <run>echo hi</run>",
            extract_command=lambda resp: "echo hi",
            clean_speech_text=lambda resp: "Running.",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        statuses = [e for e in events if e["type"] == "status"]
        # First status: thinking
        assert statuses[0]["state"] == "thinking"
        assert "ANALYZING" in statuses[0]["label"]
        # Second status: executing
        assert statuses[1]["state"] == "executing"
        assert "EXECUTING" in statuses[1]["label"]


class TestEmptyResponse:
    """Edge case: brain returns empty or whitespace-only response."""

    def test_empty_response_breaks(self):
        """Empty string response yields done."""
        brain = _make_brain(
            get_response=lambda msg: "",
            extract_command=lambda resp: None,
            clean_speech_text=lambda resp: "",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        # Should yield status, then break, then done
        assert types == ["status", "status", "done"]
        # The second status should be "PROCESSING COMPLETE"
        assert events[1]["label"] == "PROCESSING COMPLETE"

    def test_whitespace_only_response_breaks(self):
        """Whitespace-only response yields done."""
        brain = _make_brain(
            get_response=lambda msg: "   \n  \t  ",
            extract_command=lambda resp: None,
            clean_speech_text=lambda resp: "",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        assert types == ["status", "status", "done"]


class TestIterationCap:
    """Generator respects max_iterations."""

    def test_hits_max_iterations(self):
        """After max iterations, assistant_response says so and loop ends."""
        brain = _make_brain(
            get_response=lambda msg: "Again. <run>echo next</run>",
            extract_command=lambda resp: "echo next",
            clean_speech_text=lambda resp: "Again.",
        )
        agent = _make_system_agent()

        events = list(generate_agentic_loop(brain, agent, "test", max_iterations=2))
        types = [e["type"] for e in events]
        assert types[-1] == "done"

        # There should be a cap message
        caps = [e for e in events if e["type"] == "assistant_response"
                and "maximum command iterations" in e["content"].lower()]
        assert len(caps) == 1

    def test_exactly_max_iterations_commands(self):
        """Run exactly max_iterations commands, see cap message at the end."""
        brain = _make_brain(
            get_response=lambda msg: "Do. <run>echo x</run>",
            extract_command=lambda resp: "echo x",
            clean_speech_text=lambda resp: "Do.",
        )
        agent = _make_system_agent()

        n = 3
        events = list(generate_agentic_loop(brain, agent, "test", max_iterations=n))
        # Count commands (they should be n)
        commands = [e for e in events if e["type"] == "command"]
        assert len(commands) == n

    def test_default_max_iterations_from_config(self):
        """When max_iterations is None, use config.MAX_AGENTIC_ITERATIONS."""
        from jarvis.config import MAX_AGENTIC_ITERATIONS
        brain = _make_brain(
            get_response=lambda msg: "Do. <run>echo x</run>",
            extract_command=lambda resp: "echo x",
            clean_speech_text=lambda resp: "Do.",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        commands = [e for e in events if e["type"] == "command"]
        assert len(commands) == MAX_AGENTIC_ITERATIONS


class TestErrorHandling:
    """Generator handles exceptions gracefully."""

    def test_brain_get_response_raises(self):
        """If brain.get_response raises, an error event is yielded."""
        brain = _make_brain()
        brain.get_response.side_effect = RuntimeError("API failure")
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        assert "error" in types
        # NOTE: "done" is NOT yielded when an exception occurs
        # (the except block yields "error" but does not yield "done")
        err = [e for e in events if e["type"] == "error"][0]
        assert "API failure" in err["content"]

    def test_system_agent_execute_raises(self):
        """If system_agent.execute_command raises, loop catches and yields error."""
        calls = [0]

        def get_resp(msg):
            calls[0] += 1
            return "Run. <run>bad</run>" if calls[0] == 1 else "Done."

        brain = _make_brain(
            get_response=get_resp,
            extract_command=lambda resp: "bad",
            clean_speech_text=lambda resp: "Run.",
        )
        agent = _make_system_agent()
        agent.execute_command.side_effect = RuntimeError("boom")
        events = list(generate_agentic_loop(brain, agent, "test"))
        types = [e["type"] for e in events]
        assert "error" in types
        err = [e for e in events if e["type"] == "error"][0]
        assert "boom" in err["content"]

    def test_error_in_first_iteration_yields_error_not_done(self):
        """On error, the last event type is 'error' (not 'done')."""
        brain = _make_brain()
        brain.get_response.side_effect = ValueError("crash")
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        # The except block yields "error" but NOT "done"
        assert events[-1]["type"] == "error"


class TestEventIntegrity:
    """Every event dict has required keys."""

    REQUIRED_KEYS = {
        "status": ["type", "state", "label"],
        "assistant_response": ["type", "content", "iteration"],
        "command": ["type", "content", "iteration"],
        "command_output": ["type", "status", "exit_code", "stdout", "stderr", "iteration"],
        "done": ["type"],
        "error": ["type", "content"],
    }

    def test_all_events_have_required_keys(self):
        brain = _make_brain(
            get_response=lambda msg: "Run. <run>ls</run>",
            extract_command=lambda resp: "ls",
            clean_speech_text=lambda resp: "Run.",
        )
        agent = _make_system_agent()
        events = list(generate_agentic_loop(brain, agent, "test"))
        for ev in events:
            keys = self.REQUIRED_KEYS.get(ev["type"])
            assert keys is not None, f"Unknown event type: {ev['type']}"
            for k in keys:
                assert k in ev, f"Event {ev['type']} missing key {k}"
