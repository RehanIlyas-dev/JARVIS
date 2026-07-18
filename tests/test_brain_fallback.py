#!/usr/bin/env python3
"""
Comprehensive JARVIS Brain Fallback Test Suite.

Tests the offline fallback command matcher across all three supported platforms
(Linux, macOS, Windows) by monkey-patching _IS_WINDOWS and _IS_MAC.

Usage:
    pytest tests/test_brain_fallback.py -v
    python tests/test_brain_fallback.py   (direct run)
"""

import os
import sys
import re
import types

# Ensure jarvis is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jarvis.brain import JarvisBrain


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

class BrainHarness:
    """Wraps JarvisBrain in fallback mode and allows platform simulation."""

    def __init__(self):
        # Create a brain with no API keys so it falls back to fallback mode
        self._saved_env = {}
        for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "OLLAMA_API_URL", "LOCAL_API_URL"):
            self._saved_env[k] = os.environ.pop(k, None)
        self.brain = JarvisBrain(
            system_info={"os": "Linux", "user": "TestUser", "cwd": "/home/test"},
            debug=False,
        )
        self._restore_env()

    def _restore_env(self):
        for k, v in self._saved_env.items():
            if v is not None:
                os.environ[k] = v

    def set_platform(self, platform_name: str):
        """Set the simulated platform: 'linux', 'macos', or 'windows'."""
        if platform_name == "linux":
            self.brain._IS_WINDOWS = False
            self.brain._IS_MAC = False
        elif platform_name == "macos":
            self.brain._IS_WINDOWS = False
            self.brain._IS_MAC = True
        elif platform_name == "windows":
            self.brain._IS_WINDOWS = True
            self.brain._IS_MAC = False
        else:
            raise ValueError(f"Unknown platform: {platform_name}")
        # Force provider to fallback
        self.brain.provider = "fallback"

    def get(self, query: str) -> str:
        """Send a query to the fallback brain and return the response."""
        return self.brain.get_response(query)

    def reset_history(self):
        """Clear conversation history between tests."""
        self.brain.conversation_history = []


# ---------------------------------------------------------------------------
# Test data: queries organized by category with expected platform assertions
# ---------------------------------------------------------------------------

def _query(name, query, platform_checks):
    """
    Build a test case dict.
    platform_checks: dict mapping 'linux'/'macos'/'windows' to a list of
                     strings that must appear in the response for that platform.
    """
    return {"name": name, "query": query, "platform_checks": platform_checks}


TEST_CASES = [
    # ==================== APP LAUNCHING ====================
    _query(
        "Launch Firefox",
        "open firefox",
        {
            "linux":   ["<run>firefox &</run>"],
            "macos":   ["<run>open -a Firefox</run>"],
            "windows": ["<run>start firefox</run>"],
        },
    ),
    _query(
        "Launch Chrome",
        "open google chrome",
        {
            "linux":   ["<run>google-chrome"],
            "macos":   ["<run>open -a 'Google Chrome'</run>"],
            "windows": ["<run>start chrome</run>"],
        },
    ),
    _query(
        "Launch VSCode",
        "open vscode",
        {
            "linux":   ["<run>code . &</run>"],
            "macos":   ["<run>open -a 'Visual Studio Code' .</run>"],
            "windows": ["<run>start code</run>"],
        },
    ),
    _query(
        "Launch terminal",
        "open terminal",
        {
            "linux":   ["<run>gnome-terminal"],
            "macos":   ["<run>open -a Terminal</run>"],
            "windows": ["<run>powershell -NoExit</run>"],
        },
    ),
    _query(
        "Launch calculator",
        "open calculator",
        {
            "linux":   ["<run>gnome-calculator"],
            "macos":   ["<run>open -a Calculator</run>"],
            "windows": ["<run>calc</run>"],
        },
    ),
    _query(
        "Launch Slack",
        "open slack",
        {
            "linux":   ["<run>slack &</run>"],
            "macos":   ["<run>open -a Slack</run>"],
            "windows": ["<run>start slack</run>"],
        },
    ),
    _query(
        "Launch Spotify",
        "play music on spotify",
        {
            "linux":   ["<run>spotify &</run>"],
            "macos":   ["<run>open -a Spotify</run>"],
            "windows": ["<run>start spotify</run>"],
        },
    ),

    # ==================== SYSTEM INFO ====================
    _query(
        "Memory info",
        "how much memory do I have",
        {
            "linux":   ["<run>free -h</run>"],
            "macos":   ["<run>vm_stat</run>"],
            "windows": ["<run>Get-CimInstance", "Win32_OperatingSystem"],
        },
    ),
    _query(
        "Disk space",
        "check disk space",
        {
            "linux":   ["<run>df -h</run>"],
            "macos":   ["<run>df -h</run>"],
            "windows": ["Win32_LogicalDisk"],
        },
    ),
    _query(
        "Process list",
        "what processes are running",
        {
            "linux":   ["<run>ps aux"],
            "macos":   ["<run>ps aux"],
            "windows": ["<run>Get-Process"],
        },
    ),
    _query(
        "Who am I",
        "who am i",
        {
            "linux":   ["<run>whoami"],
            "macos":   ["<run>whoami"],
            "windows": ["$env:USERNAME", "Write-Host"],
        },
    ),
    _query(
        "System info",
        "system info",
        {
            "linux":   ["<run>uname -a"],
            "macos":   ["<run>uname -a"],
            "windows": ["<run>Get-CimInstance", "Win32_OperatingSystem", "Win32_Processor"],
        },
    ),

    # ==================== FILE OPERATIONS ====================
    _query(
        "List files",
        "list files in current directory",
        {
            "linux":   ["<run>ls -la</run>"],
            "macos":   ["<run>ls -la</run>"],
            "windows": ["<run>Get-ChildItem -Force</run>"],
        },
    ),
    _query(
        "Create folder",
        "create folder test_folder",
        {
            "linux":   ["<run>mkdir -p"],
            "macos":   ["<run>mkdir -p"],
            "windows": ["<run>mkdir"],
        },
    ),
    _query(
        "Search files",
        "search for python files",
        {
            "linux":   ["<run>find . -iname"],
            "macos":   ["<run>find . -iname"],
            "windows": ["<run>Get-ChildItem -Recurse -Filter"],
        },
    ),

    # ==================== SYSTEM CONTROLS ====================
    _query(
        "Volume up",
        "turn volume up",
        {
            "linux":   ["<run>amixer sset Master 10%+</run>"],
            "macos":   ["<run>osascript", "set volume output volume"],
            "windows": ["SendKeys", "175"],
        },
    ),
    _query(
        "Volume down",
        "turn volume down",
        {
            "linux":   ["<run>amixer sset Master 10%-</run>"],
            "macos":   ["<run>osascript", "set volume output volume"],
            "windows": ["SendKeys", "174"],
        },
    ),
    _query(
        "Task manager",
        "open task manager",
        {
            "linux":   ["<run>gnome-system-monitor"],
            "macos":   ["<run>open -a 'Activity Monitor'</run>"],
            "windows": ["<run>taskmgr</run>"],
        },
    ),

    # ==================== NETWORK ====================
    _query(
        "IP address",
        "what is my ip address",
        {
            "linux":   ["<run>hostname -I", "ip route"],
            "macos":   ["<run>ifconfig", "inet "],
            "windows": ["<run>ipconfig", "IPv4"],
        },
    ),

    # ==================== BATTERY & TEMPERATURE ====================
    _query(
        "Battery status",
        "what is my battery status",
        {
            "linux":   ["<run>upower", "acpi", "BAT"],
            "macos":   ["<run>pmset -g batt</run>"],
            "windows": ["Win32_Battery"],
        },
    ),
    _query(
        "Temperature",
        "what is the cpu temperature",
        {
            "linux":   ["<run>sensors", "thermal_zone"],
            "macos":   ["<run>pmset -g therm</run>"],
            "windows": ["MSAcpi_ThermalZoneTemperature"],
        },
    ),

    # ==================== SYSTEM CONTROLS (additional) ====================
    _query(
        "Lock screen",
        "lock screen",
        {
            "linux":   ["<run>xdg-screensaver lock", "gnome-screensaver"],
            "macos":   ["<run>pmset displaysleepnow</run>"],
            "windows": ["<run>rundll32.exe user32.dll,LockWorkStation</run>"],
        },
    ),
    _query(
        "Screenshot",
        "take a screenshot",
        {
            "linux":   ["<run>gnome-screenshot"],
            "macos":   ["<run>screencapture"],
            "windows": ["<run>Add-Type", "System.Windows.Forms", "Bitmap"],
        },
    ),
    _query(
        "Mute",
        "mute volume",
        {
            "linux":   ["<run>amixer sset Master toggle</run>"],
            "macos":   ["<run>osascript", "set volume with output muted"],
            "windows": ["SendKeys", "173"],
        },
    ),

    # ==================== NETWORK / PING ====================
    _query(
        "Ping",
        "ping google",
        {
            "linux":   ["<run>ping -c 3 google.com</run>"],
            "macos":   ["<run>ping -c 3 google.com</run>"],
            "windows": ["<run>ping -n 3 google.com</run>"],
        },
    ),

    # ==================== TIME & DATE ====================
    _query(
        "Time",
        "what time is it",
        {
            "linux":   ["<run>date</run>"],
            "macos":   ["<run>date</run>"],
            "windows": ["<run>Get-Date -Format"],
        },
    ),

    # ==================== KNOWLEDGE QUESTIONS (no <run> tag) ====================
    _query(
        "Who is Sam Altman (knowledge)",
        "who is Sam Altman",
        {
            "linux":   [],   # No <run> expected - knowledge question
            "macos":   [],
            "windows": [],
        },
    ),
    _query(
        "Greeting",
        "hello",
        {
            "linux":   ["Hello Sir"],
            "macos":   ["Hello Sir"],
            "windows": ["Hello Sir"],
        },
    ),
    _query(
        "Help",
        "what can you do",
        {
            "linux":   ["I can list directories", "open applications"],
            "macos":   ["I can list directories", "open applications"],
            "windows": ["I can list directories", "open applications"],
        },
    ),
    _query(
        "Thank you",
        "thank you",
        {
            "linux":   ["Always at your service"],
            "macos":   ["Always at your service"],
            "windows": ["Always at your service"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Run tests
# ---------------------------------------------------------------------------

def run_all_tests():
    """Run all test cases and return (passed, failed, details)."""
    harness = BrainHarness()
    passed = 0
    failed = 0
    details = []

    for platform_name in ("linux", "macos", "windows"):
        platform_label = platform_name.upper()
        harness.set_platform(platform_name)

        for tc in TEST_CASES:
            name = tc["name"]
            query = tc["query"]
            checks = tc["platform_checks"].get(platform_name, [])

            try:
                harness.reset_history()
                response = harness.get(query)

                # For knowledge questions: ensure NO <run> tag
                if not checks:
                    if "<run>" in response:
                        msg = (f"[{platform_label}] {name}: Expected NO <run> tag but found one. "
                               f"Response: {response[:200]}")
                        print(f"  FAIL: {msg}")
                        failed += 1
                        details.append({"test": name, "platform": platform_name, "status": "FAIL", "reason": msg})
                    else:
                        print(f"  PASS: [{platform_label}] {name}")
                        passed += 1
                        details.append({"test": name, "platform": platform_name, "status": "PASS"})
                    continue

                # For command queries: verify ALL expected strings are present
                all_found = True
                missing = []
                for expected in checks:
                    if expected not in response:
                        all_found = False
                        missing.append(expected)

                if all_found:
                    print(f"  PASS: [{platform_label}] {name}")
                    passed += 1
                    details.append({"test": name, "platform": platform_name, "status": "PASS"})
                else:
                    msg = (f"[{platform_label}] {name}: Missing expected patterns: {missing}. "
                           f"Response: {response[:300]}")
                    print(f"  FAIL: {msg}")
                    failed += 1
                    details.append({"test": name, "platform": platform_name, "status": "FAIL", "reason": msg})

            except Exception as e:
                import traceback
                msg = f"[{platform_label}] {name}: EXCEPTION: {e}\n{traceback.format_exc()}"
                print(f"  FAIL: {msg}")
                failed += 1
                details.append({"test": name, "platform": platform_name, "status": "ERROR", "reason": str(e)})

    return passed, failed, details


def print_report(passed, failed, details):
    total = passed + failed
    print(f"\n{'='*60}")
    print(f"  CROSS-PLATFORM TEST REPORT")
    print(f"{'='*60}")
    print(f"  Total tests : {total}")
    print(f"  Passed      : {passed}")
    print(f"  Failed      : {failed}")
    print(f"  Pass rate   : {passed/total*100:.1f}%")

    # Group failures by platform
    failures = [d for d in details if d["status"] != "PASS"]
    if failures:
        print(f"\n  FAILURES:")
        for f in failures:
            print(f"    [{f['platform']}] {f['test']}: {f.get('reason', '')}")

    return failed == 0


# ---------------------------------------------------------------------------
# pytest-compatible entry point
# ---------------------------------------------------------------------------

def test_all_platforms():
    """Single pytest test that runs all queries across all three platforms."""
    passed, failed, details = run_all_tests()
    # Print a summary on failure so the CI log is informative
    if failed:
        print_report(passed, failed, details)
    assert failed == 0, f"{failed} cross-platform test(s) failed"


if __name__ == "__main__":
    passed, failed, details = run_all_tests()
    success = print_report(passed, failed, details)
    sys.exit(0 if success else 1)
