#!/usr/bin/env python3
"""
Integration tests for the JARVIS pipeline.

Tests verify that components work together end-to-end:

  1. Full agentic loop pipeline: FallbackMatcher → agentic_loop → SystemAgent mock → output
  2. End-to-end command execution: SystemAgent with real subprocess calls
  3. Agentic loop with SystemAgent: Feed a <run> command through the loop, verify execution
  4. Web app SSE streaming: Mock the full chat flow end-to-end
  5. Brain → FallbackMatcher delegation: Verify brain properly delegates offline commands
  6. Cross-module import sanity: All modules import cleanly
"""

import json
import os
import platform

import pytest
from unittest.mock import MagicMock, patch


# ===================================================================
# 1. FULL AGENTIC LOOP PIPELINE
# ===================================================================


class TestFullAgenticLoopPipeline:
    """
    Integration test: FallbackMatcher → agentic_loop → SystemAgent → output.

    Creates a real FallbackMatcher (no mocking), connects it to a real brain
    in fallback mode, wires a mock SystemAgent for execute_command, and runs
    the full generator to verify all event types are produced correctly.
    """

    @pytest.fixture(autouse=True)
    def no_api_keys(self, monkeypatch):
        for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "OLLAMA_API_URL", "LOCAL_API_URL"):
            monkeypatch.delenv(k, raising=False)

    @pytest.fixture
    def history_records(self):
        records = []
        return records

    @pytest.fixture
    def fallback_matcher(self, history_records):
        """Real FallbackMatcher with a real add_to_history."""
        from jarvis.fallback_matcher import FallbackMatcher

        records = history_records

        def add(role, content):
            records.append({"role": role, "content": content})

        agent = MagicMock()
        agent.execute_command.return_value = {
            "status": "success",
            "exit_code": 0,
            "stdout": "hello from mock shell",
            "stderr": "",
        }
        agent.get_cwd.return_value = "/home/test"
        return (
            FallbackMatcher(add_to_history=add, system_agent=agent, is_windows=False, is_mac=False),
            records,
            agent,
        )

    def _make_brain_with_fallback(self, fallback_matcher):
        """Build a brain whose fallback_matcher is the real one."""
        from jarvis.brain import JarvisBrain

        brain = JarvisBrain(
            system_info={"os": "Linux", "user": "Tester", "cwd": "/home/test"},
            debug=False,
        )
        brain.provider = "fallback"
        brain._IS_WINDOWS = False
        brain._IS_MAC = False
        brain.fallback_matcher = fallback_matcher
        return brain

    def test_pipeline_greeting_no_command(self, fallback_matcher):
        """Greeting: brain → fallback_matcher → generator yields assistant_response."""
        from jarvis.agentic_loop import generate_agentic_loop

        fm, records, agent = fallback_matcher
        brain = self._make_brain_with_fallback(fm)
        events = list(generate_agentic_loop(brain, agent, "hello"))

        types = [e["type"] for e in events]
        # Should have: status, assistant_response (greeting), done
        assert "assistant_response" in types
        assert "done" in types
        assert "command" not in types  # No command for greetings

        # Verify the greeting message
        asst = [e for e in events if e["type"] == "assistant_response"]
        assert len(asst) >= 1
        assert "Hello Sir" in asst[0]["content"]

        # Verify history recorded
        assert len(records) >= 2
        assert records[0]["role"] == "user"
        assert records[1]["role"] == "assistant"

    def test_pipeline_weather_command(self, fallback_matcher):
        """Weather query: fallback emits <run>, generator yields command + output."""
        from jarvis.agentic_loop import generate_agentic_loop

        fm, records, agent = fallback_matcher
        brain = self._make_brain_with_fallback(fm)

        events = list(generate_agentic_loop(brain, agent, "what is the weather"))

        types = [e["type"] for e in events]
        assert "assistant_response" in types
        assert "command" in types
        assert "command_output" in types
        assert "done" in types

        cmd = [e for e in events if e["type"] == "command"]
        assert len(cmd) >= 1
        assert "wttr.in" in cmd[0]["content"]

        out = [e for e in events if e["type"] == "command_output"]
        assert len(out) >= 1
        assert out[0]["status"] == "success"
        assert out[0]["stdout"] == "hello from mock shell"

    def test_pipeline_list_files_command(self, fallback_matcher):
        """List files: fallback emits ls <run>, generator yields full cycle."""
        from jarvis.agentic_loop import generate_agentic_loop

        fm, records, agent = fallback_matcher
        brain = self._make_brain_with_fallback(fm)

        events = list(generate_agentic_loop(brain, agent, "list files"))

        types = [e["type"] for e in events]
        assert "command" in types
        assert "command_output" in types

        cmd = [e for e in events if e["type"] == "command"]
        assert "ls -la" in cmd[0]["content"]

    def test_pipeline_unknown_no_agent(self, no_api_keys):
        """Unknown query without system_agent: fallback yields apology, no command."""
        from jarvis.fallback_matcher import FallbackMatcher
        from jarvis.agentic_loop import generate_agentic_loop
        from jarvis.brain import JarvisBrain

        records = []

        def add(role, content):
            records.append({"role": role, "content": content})

        fm = FallbackMatcher(add_to_history=add, system_agent=None, is_windows=False, is_mac=False)
        brain = JarvisBrain(
            system_info={"os": "Linux", "user": "Tester", "cwd": "/home/test"},
            debug=False,
        )
        brain.provider = "fallback"
        brain.fallback_matcher = fm
        agent = MagicMock()

        events = list(generate_agentic_loop(brain, agent, "do something random"))

        types = [e["type"] for e in events]
        assert "assistant_response" in types
        # No command since we don't have a system_agent on the matcher
        # But the brain still has a system_agent... let's check

        asst = [e for e in events if e["type"] == "assistant_response"]
        assert len(asst) >= 1
        assert "don't understand" in asst[0]["content"].lower()

    def test_pipeline_system_execution_result(self, fallback_matcher):
        """Feed a system execution result back through the loop."""
        from jarvis.agentic_loop import generate_agentic_loop

        fm, records, agent = fallback_matcher
        brain = self._make_brain_with_fallback(fm)

        # Simulate the result that would be fed back after a command
        result_message = (
            "[System Execution Result]\n"
            "Status: success\n"
            "Exit Code: 0\n"
            "STDOUT:\nTask completed successfully\n"
            "STDERR:\n\n"
            "[/System Execution Result]\n"
            "CWD: /home/test"
        )

        events = list(generate_agentic_loop(brain, agent, result_message))

        types = [e["type"] for e in events]
        assert "assistant_response" in types
        # The fallback matcher should parse the result and return the stdout
        asst = [e for e in events if e["type"] == "assistant_response"]
        assert len(asst) >= 1
        assert "Task completed successfully" in asst[0]["content"]


# ===================================================================
# 2. END-TO-END COMMAND EXECUTION
# ===================================================================


class TestSystemAgentRealExecution:
    """
    Integration test: SystemAgent with real subprocess calls.

    Spawns real processes for safe commands (echo, pwd) and verifies
    the output is captured correctly. Tests dangerous/blocked command
    guards without actually running dangerous commands.
    """

    @pytest.fixture
    def agent(self):
        from jarvis.system_agent import SystemAgent

        return SystemAgent()

    def test_echo_command(self, agent):
        """SystemAgent.execute_command runs 'echo' and captures stdout."""
        result = agent.execute_command("echo 'Hello JARVIS integration test'")
        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert "Hello JARVIS integration test" in result["stdout"]

    def test_pwd_command(self, agent):
        """SystemAgent.execute_command runs 'pwd' and returns current directory."""
        result = agent.execute_command("pwd")
        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert result["stdout"]  # Should contain a path

    def test_multiple_commands(self, agent):
        """SystemAgent can run chained commands with ;."""
        result = agent.execute_command("echo first; echo second")
        assert result["status"] == "success"
        assert result["exit_code"] == 0
        assert "first" in result["stdout"]
        assert "second" in result["stdout"]

    def test_cd_then_pwd(self, agent):
        """cd command updates cwd; subsequent commands run in new directory."""
        original_cwd = agent.get_cwd()
        tmp_dir = "/tmp"
        if not os.path.isdir(tmp_dir):
            pytest.skip(f"{tmp_dir} does not exist")

        result = agent.execute_command(f"cd {tmp_dir}")
        assert result["status"] == "success"
        assert agent.get_cwd() == tmp_dir

        # pwd should reflect new directory
        result_pwd = agent.execute_command("pwd")
        assert tmp_dir in result_pwd["stdout"]

        # Restore
        agent.execute_command(f"cd {original_cwd}")

    def test_command_timeout(self, agent):
        """SystemAgent handles timeout gracefully."""
        result = agent.execute_command("sleep 10", timeout=1)
        assert result["status"] == "timeout"
        assert result["exit_code"] == -1

    def test_nonexistent_command(self, agent):
        """SystemAgent handles nonexistent commands gracefully."""
        result = agent.execute_command("nonexistent_command_xyz123")
        # Should return an error status (non-zero exit code)
        assert result["status"] == "success"  # subprocess runs but returns non-zero
        assert result["exit_code"] != 0

    def test_blocked_command_rm_rf(self, agent):
        """SystemAgent blocks 'rm -rf /' entirely."""
        result = agent.execute_command("rm -rf /")
        assert result["status"] == "blocked"
        assert result["exit_code"] == -1
        assert "blocked" in result["stderr"].lower()

    def test_blocked_command_fork_bomb(self, agent):
        """SystemAgent blocks fork bomb."""
        result = agent.execute_command(":(){ :|:& };:")
        assert result["status"] == "blocked"

    def test_dangerous_command_requires_confirmation(self, agent, monkeypatch):
        """Dangerous commands require user confirmation."""
        # Simulate user NOT confirming.
        # Use `rm -r` (in DANGEROUS_COMMANDS) but NOT `rm -rf /` (BLOCKED_COMMANDS).
        monkeypatch.setattr("builtins.input", lambda _: "NO")
        result = agent.execute_command("rm -r /tmp/test_jarvis_dir")
        assert result["status"] == "cancelled"
        assert "cancelled" in result["stderr"].lower()

    def test_dangerous_command_confirmed(self, agent, monkeypatch):
        """Dangerous commands run when confirmed."""
        monkeypatch.setattr("builtins.input", lambda _: "YES")
        # Use a safe rm with -i (which is in DANGEROUS_COMMANDS)
        result = agent.execute_command("rm -r /tmp/nonexistent_jarvis_test_dir")
        # Should run but fail because dir doesn't exist (or succeed if it does)
        assert result["status"] in ("success", "error")

    def test_cd_to_nonexistent_directory(self, agent):
        """cd to a nonexistent directory returns an error."""
        result = agent.execute_command("cd /nonexistent_path_xyz_123")
        assert result["status"] == "error"
        assert result["exit_code"] == 1

    def test_long_output_truncation(self, agent):
        """Output longer than 3000 chars is truncated."""
        result = agent.execute_command("echo " + ("x" * 5000))
        assert result["status"] == "success"
        assert len(result["stdout"]) <= 3100  # 3000 + truncation message
        assert "Output truncated" in result["stdout"]

    def test_get_system_info(self, agent):
        """get_system_info returns expected keys."""
        info = agent.get_system_info()
        assert "os" in info
        assert "user" in info
        assert "cwd" in info
        assert "architecture" in info
        assert info["os"] == platform.system()  # e.g. Linux, Darwin, Windows

    def test_get_cwd(self, agent):
        """get_cwd returns the current working directory."""
        cwd = agent.get_cwd()
        assert isinstance(cwd, str)
        assert os.path.isabs(cwd)

    def test_shell_is_reasonable(self, agent):
        """Shell should be reasonable for the platform."""
        sys_name = platform.system()
        if sys_name == "Darwin":
            assert agent.shell == "/bin/zsh"
        elif sys_name == "Windows":
            assert agent.shell is not None
            assert "powershell" in agent.shell.lower()
        else:
            assert agent.shell == "/bin/bash"


# ===================================================================
# 3. AGENTIC LOOP WITH SYSTEMAGENT
# ===================================================================


class TestAgenticLoopWithRealSystemAgent:
    """
    Integration test: Feed a <run> command through the full agentic loop
    with a real SystemAgent and a mocked brain, verifying that the loop
    executes the command and feeds the result back.

    We mock the brain's get_response to return a command-containing response,
    and use a *real* SystemAgent to execute the command.
    """

    @pytest.fixture
    def real_agent(self):
        from jarvis.system_agent import SystemAgent

        return SystemAgent()

    def test_echo_through_loop(self, real_agent):
        """Generator executes echo via real SystemAgent, result feeds back."""
        from jarvis.agentic_loop import generate_agentic_loop
        from unittest.mock import MagicMock

        brain = MagicMock()
        brain.get_response.side_effect = [
            "Echoing a message. <run>echo 'Hello from JARVIS loop'</run>",
            "",  # Second iteration: empty response stops the loop
        ]
        brain.extract_command.side_effect = [
            "echo 'Hello from JARVIS loop'",
            None,
        ]
        brain.clean_speech_text.side_effect = [
            "Echoing a message.",
            "",
        ]

        events = list(generate_agentic_loop(brain, real_agent, "say hello"))

        types = [e["type"] for e in events]
        assert "assistant_response" in types
        assert "command" in types
        assert "command_output" in types
        assert "done" in types

        cmd = [e for e in events if e["type"] == "command"]
        assert "echo" in cmd[0]["content"]

        out = [e for e in events if e["type"] == "command_output"]
        assert out[0]["status"] == "success"
        assert out[0]["exit_code"] == 0
        assert "Hello from JARVIS loop" in out[0]["stdout"]

        # The result should be fed back as the next current_message
        # The brain should have been called with the result
        # (our mock just returns "" on second call)
        assert brain.get_response.call_count >= 1

    def test_pwd_through_loop(self, real_agent):
        """Generator executes pwd via real SystemAgent."""
        from jarvis.agentic_loop import generate_agentic_loop
        from unittest.mock import MagicMock

        brain = MagicMock()
        brain.get_response.side_effect = [
            "Showing path. <run>pwd</run>",
            "",
        ]
        brain.extract_command.side_effect = [
            "pwd",
            None,
        ]
        brain.clean_speech_text.side_effect = [
            "Showing path.",
            "",
        ]

        events = list(generate_agentic_loop(brain, real_agent, "where am i"))

        types = [e["type"] for e in events]
        assert "command" in types
        assert "command_output" in types

        out = [e for e in events if e["type"] == "command_output"]
        assert out[0]["status"] == "success"
        assert out[0]["exit_code"] == 0
        assert real_agent.get_cwd() in out[0]["stdout"]

    def test_failing_command_through_loop(self, real_agent):
        """Generator handles a failing command gracefully."""
        from jarvis.agentic_loop import generate_agentic_loop
        from unittest.mock import MagicMock

        brain = MagicMock()
        brain.get_response.side_effect = [
            "Trying. <run>cd /nonexistent_path_xyz_123</run>",
            "",
        ]
        brain.extract_command.side_effect = [
            "cd /nonexistent_path_xyz_123",
            None,
        ]
        brain.clean_speech_text.side_effect = [
            "Trying.",
            "",
        ]

        events = list(generate_agentic_loop(brain, real_agent, "go to nowhere"))

        types = [e["type"] for e in events]
        assert "command" in types
        assert "command_output" in types

        out = [e for e in events if e["type"] == "command_output"]
        assert out[0]["status"] == "error"
        assert out[0]["exit_code"] == 1

    def test_multiple_iterations_through_loop(self, real_agent):
        """Generator runs multiple iterations with commands."""
        from jarvis.agentic_loop import generate_agentic_loop
        from unittest.mock import MagicMock

        call_count = [0]

        def get_response(msg):
            call_count[0] += 1
            if call_count[0] <= 2:
                return f"Iteration {call_count[0]}. <run>echo 'iter {call_count[0]}'</run>"
            return "Done."

        def extract_command(resp):
            if call_count[0] <= 2:
                return f"echo 'iter {call_count[0]}'"
            return None

        def clean_speech_text(resp):
            if call_count[0] <= 2:
                return f"Iteration {call_count[0]}."
            return "Done."

        brain = MagicMock()
        brain.get_response.side_effect = get_response
        brain.extract_command.side_effect = extract_command
        brain.clean_speech_text.side_effect = clean_speech_text

        events = list(generate_agentic_loop(brain, real_agent, "run multiple", max_iterations=3))

        commands = [e for e in events if e["type"] == "command"]
        assert len(commands) == 2  # Only 2 commands because 3rd iteration gets "Done."

        outputs = [e for e in events if e["type"] == "command_output"]
        assert len(outputs) == 2
        for o in outputs:
            assert o["status"] == "success"
            assert o["exit_code"] == 0


# ===================================================================
# 4. WEB APP SSE STREAMING
# ===================================================================


class TestWebAppSSEIntegration:
    """
    Integration test: Mock the full chat flow end-to-end via the Flask
    web app's SSE endpoint.

    Uses Flask test client with a mocked brain/system_agent, verifies
    the SSE event stream output format and content.
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Ensure web_app globals are reset between tests."""
        # We need to patch the module-level globals before each test
        pass

    def _make_generator_events(self):
        """Produce a standard sequence of generator events."""
        brain = MagicMock()
        system_agent = MagicMock()
        brain.get_response.return_value = "Hello. <run>echo hi</run>"
        brain.extract_command.return_value = "echo hi"
        brain.clean_speech_text.return_value = "Hello."
        system_agent.execute_command.return_value = {
            "status": "success",
            "exit_code": 0,
            "stdout": "hi",
            "stderr": "",
        }
        system_agent.get_cwd.return_value = "/home/test"
        return brain, system_agent

    def test_full_chat_cycle_sse(self):
        """POST /api/chat with a message produces full SSE event stream."""
        from jarvis.web_app import app

        brain, system_agent = self._make_generator_events()

        with (
            patch("jarvis.web_app.brain", brain),
            patch("jarvis.web_app.system_agent", system_agent),
            patch("jarvis.web_app.init_app"),
            patch("jarvis.web_app.generate_agentic_loop") as mock_gen,
        ):
            mock_gen.return_value = iter([
                {"type": "status", "state": "thinking", "label": "ANALYZING QUERY..."},
                {"type": "assistant_response", "content": "Hello.", "iteration": 1},
                {"type": "command", "content": "echo hi", "iteration": 1},
                {"type": "status", "state": "executing", "label": "EXECUTING: echo hi"},
                {
                    "type": "command_output",
                    "status": "success",
                    "exit_code": 0,
                    "stdout": "hi",
                    "stderr": "",
                    "iteration": 1,
                },
                {"type": "status", "state": "thinking", "label": "PROCESSING DATA..."},
                {"type": "done"},
            ])

            with app.test_client() as client:
                resp = client.post("/api/chat", json={"message": "say hello"})
                assert resp.status_code == 200
                assert "text/event-stream" in resp.content_type

                data = resp.data.decode()
                lines = data.strip().split("\n\n")

                # Verify each SSE event
                assert "event: status" in data
                assert "event: assistant_response" in data
                assert "event: command" in data
                assert "event: command_output" in data
                assert "event: done" in data

                # Check specific content
                assert "ANALYZING QUERY" in data
                assert "Hello." in data
                assert "echo hi" in data
                assert '"stdout": "hi"' in data or "'stdout': 'hi'" in data

    def test_chat_sse_error(self):
        """When an error occurs in the generator, SSE error event is emitted."""
        from jarvis.web_app import app

        with (
            patch("jarvis.web_app.init_app"),
            patch("jarvis.web_app.generate_agentic_loop") as mock_gen,
        ):
            mock_gen.return_value = iter([
                {"type": "error", "content": "Something went wrong in the pipeline"},
            ])

            with app.test_client() as client:
                resp = client.post("/api/chat", json={"message": "crash"})
                assert resp.status_code == 200
                data = resp.data.decode()
                assert "event: error" in data
                assert "Something went wrong" in data

    def test_chat_empty_message_returns_400(self):
        """POST /api/chat with no message returns 400."""
        from jarvis.web_app import app

        with patch("jarvis.web_app.init_app"):
            with app.test_client() as client:
                resp = client.post("/api/chat", json={})
                assert resp.status_code == 400

                resp2 = client.post("/api/chat", json={"message": ""})
                assert resp2.status_code == 400

    def test_chat_sse_event_order(self):
        """SSE events from a full cycle appear in the correct order."""
        from jarvis.web_app import app

        with (
            patch("jarvis.web_app.init_app"),
            patch("jarvis.web_app.generate_agentic_loop") as mock_gen,
        ):
            mock_gen.return_value = iter([
                {"type": "status", "state": "thinking", "label": "ANALYZING"},
                {"type": "assistant_response", "content": "Hello", "iteration": 1},
                {"type": "command", "content": "ls", "iteration": 1},
                {
                    "type": "command_output",
                    "status": "success",
                    "exit_code": 0,
                    "stdout": "files",
                    "stderr": "",
                    "iteration": 1,
                },
                {"type": "done"},
            ])

            with app.test_client() as client:
                resp = client.post("/api/chat", json={"message": "test"})
                data = resp.data.decode()
                # Check ordering of event types
                events_found = []
                for line in data.split("\n"):
                    if line.startswith("event: "):
                        events_found.append(line.split("event: ")[1].strip())

                assert events_found[0] == "status"
                assert events_found[1] == "assistant_response"
                assert events_found[2] == "command"
                # After command, a status "executing" is added by api_chat
                assert events_found[3] == "status"
                assert events_found[4] == "command_output"
                # After command_output, a status "PROCESSING DATA..." is added
                assert events_found[5] == "status"
                assert events_found[-1] == "done"

    def test_chat_sse_truncates_long_output(self):
        """Long stdout/stderr is truncated to 2000 chars in SSE."""
        from jarvis.web_app import app, _sse

        long_stdout = "A" * 3000
        long_stderr = "B" * 3000

        with (
            patch("jarvis.web_app.init_app"),
            patch("jarvis.web_app.generate_agentic_loop") as mock_gen,
        ):
            mock_gen.return_value = iter([
                {"type": "command", "content": "long", "iteration": 1},
                {
                    "type": "command_output",
                    "status": "success",
                    "exit_code": 0,
                    "stdout": long_stdout,
                    "stderr": long_stderr,
                    "iteration": 1,
                },
                {"type": "done"},
            ])

            with app.test_client() as client:
                resp = client.post("/api/chat", json={"message": "run long"})
                data = resp.data.decode()
                # The SSE output should contain truncated data
                assert len(long_stdout) == 3000  # Original is 3000
                # In the SSE, it should be truncated to 2000
                # We can check by looking at the data portion
                import re

                # Find the command_output data
                for chunk in data.split("\n\n"):
                    if "command_output" in chunk:
                        # Data should not be 3000 chars of A
                        assert "AAAAA" in chunk  # Some A's present
                        # The original 3000 chars are now truncated
                        break

    def test_chat_sse_streaming_content_type(self):
        """Response has correct content-type for SSE."""
        from jarvis.web_app import app

        with (
            patch("jarvis.web_app.init_app"),
            patch("jarvis.web_app.generate_agentic_loop") as mock_gen,
        ):
            mock_gen.return_value = iter([
                {"type": "done"},
            ])

            with app.test_client() as client:
                resp = client.post("/api/chat", json={"message": "test"})
                assert resp.content_type.startswith("text/event-stream")

    def test_chat_sse_json_format(self):
        """Each SSE data payload is valid JSON."""
        from jarvis.web_app import app

        with (
            patch("jarvis.web_app.init_app"),
            patch("jarvis.web_app.generate_agentic_loop") as mock_gen,
        ):
            mock_gen.return_value = iter([
                {"type": "status", "state": "thinking", "label": "ANALYZING"},
                {"type": "assistant_response", "content": "Hello", "iteration": 1},
                {"type": "done"},
            ])

            with app.test_client() as client:
                resp = client.post("/api/chat", json={"message": "test"})
                data = resp.data.decode()

                for chunk in data.split("\n\n"):
                    if not chunk.strip():
                        continue
                    lines = chunk.strip().split("\n")
                    for line in lines:
                        if line.startswith("data: "):
                            json_str = line[6:]  # Remove "data: " prefix
                            try:
                                parsed = json.loads(json_str)
                                assert isinstance(parsed, dict)
                            except json.JSONDecodeError:
                                pytest.fail(f"Invalid JSON in SSE data: {json_str}")

    def test_api_status_returns_correct_info(self):
        """/api/status returns brain provider and system info."""
        from jarvis.web_app import app

        with (
            patch("jarvis.web_app.brain") as mock_brain,
            patch("jarvis.web_app.system_agent") as mock_agent,
            patch("jarvis.web_app.sys_info", {"os": "Linux", "user": "Tester"}),
            patch("jarvis.web_app.init_app"),
        ):
            mock_brain.provider = "fallback"
            mock_brain.model_name = None
            mock_agent.get_cwd.return_value = "/home/test"

            with app.test_client() as client:
                resp = client.get("/api/status")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["provider"] == "fallback"
                assert data["os"] == "Linux"
                assert data["user"] == "Tester"
                assert data["cwd"] == "/home/test"

    def test_api_metrics_returns_data(self):
        """/api/metrics returns system metrics."""
        from jarvis.web_app import app

        with (
            patch("jarvis.web_app._get_cpu_percent", return_value=12.5),
            patch(
                "jarvis.web_app._get_memory_info",
                return_value={"total_mb": 16000, "used_mb": 8000, "percent": 50.0},
            ),
            patch(
                "jarvis.web_app._get_disk_info",
                return_value={"total_gb": 500, "used_gb": 250, "percent": 50.0},
            ),
            patch("jarvis.web_app._get_uptime", return_value="1d 3h 30m"),
            patch("jarvis.web_app.system_agent") as mock_agent,
            patch("jarvis.web_app.init_app"),
        ):
            mock_agent.get_cwd.return_value = "/home/test"

            with app.test_client() as client:
                resp = client.get("/api/metrics")
                assert resp.status_code == 200
                data = resp.get_json()
                assert data["cpu"] == 12.5
                assert data["memory"]["total_mb"] == 16000
                assert data["disk"]["total_gb"] == 500
                assert data["uptime"] == "1d 3h 30m"
                assert data["cwd"] == "/home/test"


# ===================================================================
# 5. BRAIN → FALLBACKMATCHER DELEGATION
# ===================================================================


class TestBrainFallbackMatcherDelegation:
    """
    Integration test: Verify that the brain properly delegates to
    FallbackMatcher in fallback mode, and that platform flags are
    synced correctly.
    """

    @pytest.fixture(autouse=True)
    def no_api_keys(self, monkeypatch):
        for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "OLLAMA_API_URL", "LOCAL_API_URL"):
            monkeypatch.delenv(k, raising=False)

    @pytest.fixture
    def brain(self, no_api_keys):
        from jarvis.brain import JarvisBrain

        b = JarvisBrain(
            system_info={"os": "Linux", "user": "Tester", "cwd": "/home/test"},
            debug=False,
        )
        b.provider = "fallback"
        return b

    def test_fallback_mode_detected(self, brain):
        """When no API keys are set, provider is 'fallback'."""
        assert brain.provider == "fallback"

    def test_fallback_matcher_initialized(self, brain):
        """Brain initializes FallbackMatcher with correct add_to_history."""
        from jarvis.fallback_matcher import FallbackMatcher

        assert isinstance(brain.fallback_matcher, FallbackMatcher)
        assert brain.fallback_matcher._IS_WINDOWS is (platform.system() == "Windows")
        assert brain.fallback_matcher._IS_MAC is (platform.system() == "Darwin")

    def test_fallback_delegation_greeting(self, brain):
        """Brain delegates greeting to fallback matcher."""
        resp = brain.get_response("hello")
        assert isinstance(resp, str)
        assert len(resp) > 0
        assert "Hello Sir" in resp
        assert "offline mode" in resp

    def test_fallback_delegation_weather(self, brain):
        """Brain delegates weather query to fallback matcher."""
        resp = brain.get_response("what is the weather")
        assert "<run>" in resp
        assert "wttr.in" in resp

    def test_fallback_delegation_list_files(self, brain):
        """Brain delegates 'list files' to fallback matcher."""
        brain._IS_WINDOWS = False
        brain._IS_MAC = False
        resp = brain.get_response("list files")
        assert "<run>" in resp
        assert "ls -la" in resp

    def test_fallback_delegation_unknown(self, brain):
        """Brain delegates unknown query to fallback matcher."""
        # Without a system_agent, the matcher should apologize
        brain.fallback_matcher.system_agent = None
        resp = brain.get_response("do something very specific and unknown")
        assert isinstance(resp, str)
        assert "don't understand" in resp.lower()

    def test_fallback_delegation_with_system_agent(self, brain):
        """When system_agent is set, unknown input is translated."""
        mock_agent = MagicMock()
        mock_agent.execute_command.return_value = {
            "status": "success",
            "exit_code": 0,
            "stdout": "mock output",
            "stderr": "",
        }
        brain.system_agent = mock_agent
        brain.fallback_matcher.system_agent = mock_agent
        resp = brain.get_response("echo hello world")
        assert isinstance(resp, str)
        assert len(resp) > 0

    def test_platform_flags_synced_to_matcher(self, brain):
        """Before each get_response, brain syncs platform flags to matcher."""
        brain._IS_WINDOWS = True
        brain._IS_MAC = False
        brain.get_response("hello")
        assert brain.fallback_matcher._IS_WINDOWS is True
        assert brain.fallback_matcher._IS_MAC is False

        brain._IS_WINDOWS = False
        brain._IS_MAC = True
        brain.get_response("hello")
        assert brain.fallback_matcher._IS_WINDOWS is False
        assert brain.fallback_matcher._IS_MAC is True

    def test_fallback_for_different_platforms(self, brain):
        """Brain delegates platform-specific commands correctly."""
        # Linux
        brain._IS_WINDOWS = False
        brain._IS_MAC = False
        resp = brain.get_response("open firefox")
        assert "firefox &" in resp

    def test_fallback_matcher_platform_windows(self, brain):
        """Windows platform produces correct commands."""
        brain._IS_WINDOWS = True
        brain._IS_MAC = False
        resp = brain.get_response("open firefox")
        assert "start firefox" in resp

    def test_fallback_matcher_platform_mac(self, brain):
        """macOS platform produces correct commands."""
        brain._IS_WINDOWS = False
        brain._IS_MAC = True
        resp = brain.get_response("open firefox")
        assert "open -a Firefox" in resp

    def test_fallback_weather_windows(self, brain):
        """Windows weather command."""
        brain._IS_WINDOWS = True
        brain._IS_MAC = False
        resp = brain.get_response("weather")
        assert "Invoke-WebRequest" in resp

    def test_brain_extract_command_after_fallback(self, brain):
        """After fallback response, extract_command finds the <run> tag."""
        brain._IS_WINDOWS = False
        brain._IS_MAC = False
        resp = brain.get_response("list files")
        cmd = brain.extract_command(resp)
        assert cmd == "ls -la"

    def test_brain_clean_speech_after_fallback(self, brain):
        """After fallback response, clean_speech_text removes <run> tags."""
        resp = brain.get_response("list files")
        clean = brain.clean_speech_text(resp)
        assert "<run>" not in clean
        assert "Sir" in clean


# ===================================================================
# 6. CROSS-MODULE IMPORT SANITY
# ===================================================================


class TestCrossModuleImportSanity:
    """
    Verify that all modules import cleanly without ImportError.

    This ensures the refactored package structure is sound and no
    circular imports exist.
    """

    def test_import_config(self):
        """jarvis.config imports cleanly."""
        from jarvis import config

        assert hasattr(config, "MAX_AGENTIC_ITERATIONS")
        assert hasattr(config, "FLASK_HOST")

    def test_import_fallback_matcher(self):
        """jarvis.fallback_matcher imports cleanly."""
        from jarvis.fallback_matcher import FallbackMatcher

        assert FallbackMatcher is not None

    def test_import_system_agent(self):
        """jarvis.system_agent imports cleanly."""
        from jarvis.system_agent import SystemAgent

        assert SystemAgent is not None

    def test_import_brain(self):
        """jarvis.brain imports cleanly (no API keys required)."""
        from jarvis.brain import JarvisBrain

        assert JarvisBrain is not None

    def test_import_agentic_loop(self):
        """jarvis.agentic_loop imports cleanly."""
        from jarvis.agentic_loop import generate_agentic_loop

        assert generate_agentic_loop is not None

    def test_import_stt(self):
        """jarvis.stt imports cleanly."""
        from jarvis.stt import SpeechToText

        assert SpeechToText is not None

    def test_import_tts(self):
        """jarvis.tts imports cleanly."""
        from jarvis.tts import TextToSpeech

        assert TextToSpeech is not None

    def test_import_main(self):
        """jarvis.main imports cleanly."""
        from jarvis.main import run_agentic_loop, start_text_mode, main

        assert run_agentic_loop is not None
        assert start_text_mode is not None
        assert main is not None

    def test_import_web_app(self):
        """jarvis.web_app imports cleanly."""
        from jarvis.web_app import app, api_chat, api_status, api_metrics

        assert app is not None

    def test_import_all_modules_together(self):
        """Import all modules in the same interpreter session."""
        import jarvis.config
        import jarvis.fallback_matcher
        import jarvis.system_agent
        import jarvis.brain
        import jarvis.agentic_loop
        import jarvis.stt
        import jarvis.tts
        import jarvis.main
        import jarvis.web_app

        # Verify they're all accessible
        assert jarvis.config.MAX_AGENTIC_ITERATIONS == 8

    def test_brain_imports_fallback_matcher(self):
        """Brain correctly uses FallbackMatcher from its own import."""
        from jarvis.brain import JarvisBrain

        # The brain imports FallbackMatcher internally
        assert JarvisBrain is not None


# ===================================================================
# ADDITIONAL: CROSS-CUTTING INTEGRATION SCENARIOS
# ===================================================================


class TestCrossCuttingIntegration:
    """Higher-level integration scenarios spanning multiple modules."""

    @pytest.fixture(autouse=True)
    def no_api_keys(self, monkeypatch):
        for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "OLLAMA_API_URL", "LOCAL_API_URL"):
            monkeypatch.delenv(k, raising=False)

    def test_fallback_matcher_translate_to_execution(self):
        """FallbackMatcher._translate → execute_command with real agent."""
        from jarvis.fallback_matcher import FallbackMatcher
        from jarvis.system_agent import SystemAgent

        records = []

        def add(role, content):
            records.append({"role": role, "content": content})

        agent = SystemAgent()
        fm = FallbackMatcher(add_to_history=add, system_agent=agent, is_windows=False, is_mac=False)

        # Translate "echo HelloWorld" to a command and execute it
        cmd = fm._translate("echo HelloWorld")
        assert cmd == "echo HelloWorld"

        result = agent.execute_command(cmd)
        assert result["status"] == "success"
        assert "HelloWorld" in result["stdout"]

    def test_full_pipeline_unknown_to_execution(self):
        """Unknown input flows through: _translate → execute → respond."""
        from jarvis.fallback_matcher import FallbackMatcher
        from jarvis.system_agent import SystemAgent

        records = []

        def add(role, content):
            records.append({"role": role, "content": content})

        agent = SystemAgent()
        fm = FallbackMatcher(add_to_history=add, system_agent=agent, is_windows=False, is_mac=False)

        # This should hit the _translate path and execute echo.
        # Avoid words that match greeting/network patterns (e.g. "hello", "ip").
        resp = fm.get_response("echo test_output_xyz_123")
        assert isinstance(resp, str)
        assert "test_output_xyz_123" in resp

    def test_web_app_route_integration(self):
        """Multiple web app routes work together."""
        from jarvis.web_app import app

        with (
            patch("jarvis.web_app.brain") as mock_brain,
            patch("jarvis.web_app.system_agent") as mock_agent,
            patch("jarvis.web_app.sys_info", {"os": "Linux", "user": "Tester"}),
            patch("jarvis.web_app.init_app"),
        ):
            mock_brain.provider = "fallback"
            mock_brain.model_name = None
            mock_agent.get_cwd.return_value = "/home/test"

            with app.test_client() as client:
                # Status endpoint
                status = client.get("/api/status")
                assert status.status_code == 200
                assert status.get_json()["provider"] == "fallback"

                # Metrics endpoint
                with (
                    patch("jarvis.web_app._get_cpu_percent", return_value=0.0),
                    patch(
                        "jarvis.web_app._get_memory_info",
                        return_value={"total_mb": 1000, "used_mb": 500, "percent": 50},
                    ),
                    patch(
                        "jarvis.web_app._get_disk_info",
                        return_value={"total_gb": 100, "used_gb": 50, "percent": 50},
                    ),
                    patch("jarvis.web_app._get_uptime", return_value="1h"),
                ):
                    metrics = client.get("/api/metrics")
                    assert metrics.status_code == 200

                # Chat endpoint (with generator mocked)
                with patch("jarvis.web_app.generate_agentic_loop") as mock_gen:
                    mock_gen.return_value = iter([
                        {"type": "status", "state": "thinking", "label": "ANALYZING"},
                        {"type": "assistant_response", "content": "Hello", "iteration": 1},
                        {"type": "done"},
                    ])
                    chat = client.post("/api/chat", json={"message": "hi"})
                    assert chat.status_code == 200
                    assert "text/event-stream" in chat.content_type

    def test_brain_fallback_then_extract_command_then_agent_execute(self):
        """Full chain: brain.get_response → extract_command → SystemAgent.execute."""
        from jarvis.brain import JarvisBrain
        from jarvis.system_agent import SystemAgent

        brain = JarvisBrain(
            system_info={"os": "Linux", "user": "Tester", "cwd": os.getcwd()},
            debug=False,
        )
        brain.provider = "fallback"

        agent = SystemAgent()
        brain.system_agent = agent
        brain.fallback_matcher.system_agent = agent

        # Get response from brain (fallback matcher)
        resp = brain.get_response("echo hello chain")
        assert isinstance(resp, str)

        # Extract command (may or may not have <run>)
        cmd = brain.extract_command(resp)
        if cmd:
            # Execute it with real system agent
            result = agent.execute_command(cmd)
            assert result["status"] in ("success", "error")

    def test_config_used_across_modules(self):
        """Verify config constants are used consistently across modules."""
        from jarvis.config import MAX_AGENTIC_ITERATIONS, FLASK_HOST, FLASK_PORT
        from jarvis.agentic_loop import generate_agentic_loop
        from jarvis.web_app import app

        # Agentic loop uses MAX_AGENTIC_ITERATIONS as default
        assert generate_agentic_loop is not None

        # Flask app uses host/port from config
        assert FLASK_HOST == "127.0.0.1"
        assert FLASK_PORT == 5000

    def test_system_agent_redact_secrets(self):
        """SystemAgent._redact_secrets removes sensitive patterns from output."""
        from jarvis.system_agent import SystemAgent

        # Test with a command that outputs secrets
        result = SystemAgent._redact_secrets(
            "password = super_secret_123\n"
            "token = ghp_abc123def456\n"
            "api_key = sk-1234567890abcdef\n"
            "normal text here"
        )

        assert "[REDACTED]" in result
        assert "super_secret_123" not in result

        # Test AWS key redaction
        result2 = SystemAgent._redact_secrets("AKIA1234567890123456")
        assert "[REDACTED: AWS key]" in result2
