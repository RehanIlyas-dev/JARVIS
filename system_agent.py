import subprocess
import os
import platform
import shlex


# ---------------------------------------------------------------------------
# Commands that require explicit user confirmation before execution.
# The LLM may suggest these; we block them unless confirmed.
# ---------------------------------------------------------------------------
DANGEROUS_COMMANDS = [
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
]

# Commands that should NEVER be allowed, no confirmation possible.
BLOCKED_COMMANDS = [
    ":(){ :|:& };:",   # fork bomb
    "rm -rf /",
    "rm -rf /*",
    "mkfs /dev/sd",
    "> /dev/sda",
]


class SystemAgent:
    def __init__(self):
        self.os_name = platform.system()
        self.shell = "/bin/bash" if self.os_name == "Linux" else None
        # Track cwd so "cd" commands are persistent across turns
        self._cwd = os.path.expanduser("~")

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def execute_command(self, command: str, timeout: int = 30) -> dict:
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
                print(f"\n[JARVIS SAFETY] ⚠️  Dangerous command detected: '{command}'")
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
            if len(stdout) > max_chars:
                stdout = stdout[:max_chars] + f"\n... [Output truncated — total {len(result.stdout)} chars]"
            if len(stderr) > max_chars:
                stderr = stderr[:max_chars] + f"\n... [Error truncated — total {len(result.stderr)} chars]"

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

    def _handle_cd(self, command: str):
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
    # System info
    # ------------------------------------------------------------------

    def get_system_info(self) -> dict:
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
# Test block
# ------------------------------------------------------------------
if __name__ == "__main__":
    agent = SystemAgent()
    print("System Info:")
    for k, v in agent.get_system_info().items():
        print(f"  {k}: {v}")

    print("\nTesting simple command execution...")
    res = agent.execute_command("echo 'Hello from JARVIS shell!' && uname -a")
    print(f"Status: {res['status']}")
    print(f"Exit Code: {res['exit_code']}")
    print(f"Stdout:\n{res['stdout']}")

    print("\nTesting cd command...")
    res = agent.execute_command("cd /tmp")
    print(f"CWD after cd: {agent.get_cwd()}")
