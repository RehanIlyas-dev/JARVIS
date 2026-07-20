import subprocess
import os
import platform
import shutil
import re
from typing import Optional, List, Dict, Union


# ---------------------------------------------------------------------------
# Pre-compiled regexes for _redact_secrets — compiled once at import time.
# ---------------------------------------------------------------------------
_RE_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY( BLOCK)?-----.*?"
    r"-----END (RSA |EC |OPENSSH |PGP )?PRIVATE KEY( BLOCK)?-----",
    re.DOTALL,
)
_RE_PRIVATE_KEY_PARTIAL = re.compile(
    r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY( BLOCK)?-----.*",
    re.DOTALL,
)
_RE_AWS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_RE_SECRET_LINE = re.compile(
    r"(?i)(password|token|secret|api.?key)\s*[:=]\s*\S+",
)


# ---------------------------------------------------------------------------
# Commands that require explicit user confirmation before execution.
# The LLM may suggest these; we block them unless confirmed.
# ---------------------------------------------------------------------------
DANGEROUS_COMMANDS: List[str] = [
    "rm -rf", "rm -r", "rmdir",
    "shutdown", "reboot", "halt", "poweroff",
    "mkfs", "dd if=",
    ":(){ :|:& };:",   # fork bomb
    "> /dev/",
    "chmod -R 777 /",
    "chown -R",
    "passwd",
    "userdel", "usermod",
    "sudo rm", "sudo shutdown",
    # Windows dangerous commands
    "del /s", "format ", "rmdir /s", "rd /s",
    "Remove-Item -Recurse", "Format-Volume",
    "shutdown /s", "shutdown /r", "shutdown /f",
    "taskkill /f /im",
]

# Commands that should NEVER be allowed, no confirmation possible.
BLOCKED_COMMANDS: List[str] = [
    ":(){ :|:& };:",   # fork bomb
    "rm -rf /",
    "rm -rf /*",
    "mkfs /dev/sd",
    "> /dev/sda",
    # Windows blocked commands
    "format c:",
    "Format-Volume -DriveLetter C",
    "del /s /q C:\\",
]


class SystemAgent:
    def __init__(self) -> None:
        self.os_name: str = platform.system()
        if self.os_name == "Windows":
            self.shell: Optional[str] = shutil.which("powershell") or shutil.which("powershell.exe") or "powershell.exe"
        elif self.os_name == "Linux":
            self.shell = "/bin/bash"
        elif self.os_name == "Darwin":
            self.shell = "/bin/zsh"
        else:
            self.shell = None
        # Track cwd so "cd" commands are persistent across turns
        self._cwd: str = os.path.expanduser("~")

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def execute_command(self, command: str, timeout: int = 30) -> Dict[str, Union[str, int]]:
        """
        Execute a shell command safely, tracking cwd and blocking dangerous ops.
        Returns a dict with status, stdout, stderr, exit_code.
        """
        command = command.strip()

        # 1. Hard-block absolutely forbidden commands
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return {
                    "status": "blocked",
                    "stdout": "",
                    "stderr": f"Command blocked for safety: contains '{blocked}'.",
                    "exit_code": -1,
                }

        # 2. Warn about dangerous commands and require confirmation
        for danger in DANGEROUS_COMMANDS:
            if danger in command:
                print(f"\n[JARVIS SAFETY] WARNING: Dangerous command detected: '{command}'")
                auto_confirm = os.environ.get("JARVIS_CONFIRM_DANGEROUS", "").lower()
                if auto_confirm == "auto":
                    confirm = "YES"
                else:
                    try:
                        confirm = input("[JARVIS SAFETY] Type YES to confirm, or anything else to cancel: ").strip()
                    except EOFError:
                        confirm = ""
                if confirm != "YES":
                    return {
                        "status": "cancelled",
                        "stdout": "",
                        "stderr": "Command cancelled by safety check.",
                        "exit_code": -1,
                    }
                break  # Only ask once even if multiple matches

        # 3. Handle 'cd' specially so cwd persists across turns
        cd_new_dir = self._handle_cd(command)
        if cd_new_dir is not None:
            return cd_new_dir

        print(f"[JARVIS System] Executing: {command}")
        print(f"[JARVIS System] CWD: {self._cwd}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                executable=self.shell,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._cwd,
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            return_code = result.returncode

            # Truncate runaway output to avoid flooding the LLM context
            max_chars = 3000
            stdout_len = len(stdout)
            if stdout_len > max_chars:
                stdout = stdout[:max_chars] + f"\n... [Output truncated -- total {stdout_len} chars]"
            stderr_len = len(stderr)
            if stderr_len > max_chars:
                stderr = stderr[:max_chars] + f"\n... [Error truncated -- total {stderr_len} chars]"

            # Redact secrets / PII before handing output to the LLM
            stdout = self._redact_secrets(stdout)
            stderr = self._redact_secrets(stderr)

            return {
                "status": "success",
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": return_code,
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds.",
                "exit_code": -1,
            }
        except Exception as e:
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
            }

    def _handle_cd(self, command: str) -> Optional[Dict[str, Union[str, int]]]:
        """
        If the command is 'cd <path>', update self._cwd in-process and return a result dict.
        Returns None if this isn't a cd command (so normal execution continues).
        """
        stripped = command.strip()
        if not (stripped == "cd" or stripped.startswith("cd ") or stripped.startswith("cd\t")):
            return None

        # Parse the target path
        parts = stripped.split(None, 1)
        if len(parts) == 1:
            target = os.path.expanduser("~")
        else:
            target = os.path.expanduser(parts[1].strip())

        if not os.path.isabs(target):
            target = os.path.join(self._cwd, target)

        target = os.path.normpath(target)

        if os.path.isdir(target):
            self._cwd = target
            return {
                "status": "success",
                "stdout": f"Changed directory to: {target}",
                "stderr": "",
                "exit_code": 0,
            }
        else:
            return {
                "status": "error",
                "stdout": "",
                "stderr": f"cd: no such directory: {target}",
                "exit_code": 1,
            }

    # ------------------------------------------------------------------
    # Output sanitisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _redact_secrets(text: str) -> str:
        """Strip known secret patterns from command output before returning to the LLM."""
        if not text:
            return text

        # SSH/PGP private keys — full block (BEGIN...END)
        text = _RE_PRIVATE_KEY_BLOCK.sub("[REDACTED: private key]", text)
        # Partial key leak — BEGIN header with no matching END.
        text = _RE_PRIVATE_KEY_PARTIAL.sub("[REDACTED: private key]", text)

        # AWS access key IDs
        text = _RE_AWS_KEY.sub("[REDACTED: AWS key]", text)

        # Generic "password = ..." / "token = ..." / "secret = ..." style lines
        text = _RE_SECRET_LINE.sub(r"\1 = [REDACTED]", text)

        return text

    # ------------------------------------------------------------------
    # System info
    # ------------------------------------------------------------------

    def get_system_info(self) -> Dict[str, Union[str, int]]:
        """Return basic system telemetry used to populate the brain's context."""
        try:
            user = os.getlogin()
        except OSError:
            user = os.environ.get("USER", "sir")

        return {
            "os": self.os_name,
            "architecture": platform.architecture()[0],
            "machine": platform.machine(),
            "processor": platform.processor(),
            "user": user,
            "cwd": self._cwd,
        }

    def get_cwd(self) -> str:
        return self._cwd


# ------------------------------------------------------------------
# Test block (manual testing only)
# ------------------------------------------------------------------
