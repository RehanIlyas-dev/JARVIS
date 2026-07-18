# ---------------------------------------------------------------------------
# FallbackMatcher — offline command matching when no LLM API is available
#
# Extracted from jarvis/brain.py to keep the brain focused on LLM dispatch.
# ---------------------------------------------------------------------------

import re
from typing import Any, Callable, Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Pre-compiled regexes — compiled once at module load, not per-request.
# ---------------------------------------------------------------------------
_RE_SYSTEM_RESULT_STDOUT = re.compile(r"STDOUT:\n(.*?)\nSTDERR:", re.DOTALL)
_RE_SYSTEM_RESULT_STDERR = re.compile(r"STDERR:\n(.*?)\n\[/System Execution Result\]", re.DOTALL)
_RE_SYSTEM_RESULT_STATUS = re.compile(r"Status: (\w+)")
_RE_SYSTEM_RESULT_EXIT = re.compile(r"Exit Code: (-?\d+)")
_RE_SAFE_PATH = re.compile(r"[^\w.\-/~]")
_RE_SAFE_NAME = re.compile(r"[^\w.\-]")
_RE_SAFE_SHELL = re.compile(r"[^\w.\- ]")
_RE_SAFE_URL = re.compile(r"[^\w.\-/~:@]")
_RE_SEARCH_TERM = re.compile(r"[^\w.\-~*]")
_RE_SAFE_COMMIT = re.compile(r"[^\w]")
_RE_KILL_PROC = re.compile(
    r"(?:kill|stop|close|terminate)\s+(?:all\s+)?(\S+?)(?:\s+process(?:es)?)?$"
)
_RE_GIT_REMOTE_RENAME = re.compile(r"git\s+remote\s+rename\s+(\S+)\s+(\S+)")
_RE_REMOTE_RENAME_TO = re.compile(
    r"(?:rename|change(?:\s+the\s+name\s+of)?)\s+(?:remote\s+)?(\S+)\s+(?:to|into)\s+(\S+)"
)
_RE_REMOTE_RENAME_FROM = re.compile(
    r"(?:rename|change(?:\s+the\s+name\s+of)?)\s+(?:remote\s+)?(\S+)\s+from\s+(\S+)\s+to\s+(\S+)"
)
_RE_TRANSLATE_SEARCH = re.compile(r"(?:find|search for|locate|look for)\s+(?:file\s+)?(.+)")

# Pre-computed keyword tuples for faster matching.
# Stored as module-level constants to avoid re-creating generator expressions.
_KW_GREETING = ("hello", "hi ", "hey", "wake up", "good morning", "good evening")
_KW_WEATHER = ("weather", "forecast", "is it raining")
_KW_CREATE_FOLDER = ("create folder", "make directory", "new folder")
_KW_SEARCH = ("search", "find")
_KW_LISTING = ("list", "folder", "directory", "directories", "files", "what's in", "what is in")
_KW_NAV_HOME = ("go home", "go to home", "change to home")
_KW_NAV_DOWNLOADS = ("downloads folder", "go to downloads")
_KW_NAV_DOCUMENTS = ("documents folder", "go to documents")
_KW_NAV_DESKTOP = ("desktop folder", "go to desktop")
_KW_PWD = ("where am i", "current path", "working directory")
_KW_KILL = ("kill", "stop", "close", "terminate")
_KW_READ_FILE = ("read file", "show file", "cat file", "open file")
_KW_DELETE_FILE = ("delete file", "remove file")
_KW_TRANSLATE_LISTING = ("list", "files", "folder", "directory", "ls", "dir ", "show files", "contents", "what's in", "whats in", "open the folder", "open folder")
_KW_TRANSLATE_PROCESS = ("process", "running", "what's running", "whats running", "programs", "tasks")
_KW_TRANSLATE_TIME = ("time", "date", "what day", "what time")
_KW_TRANSLATE_RAW_COMMAND = ("dir", "ls", "cd", "start", "mkdir", "md", "del", "rm", "cat", "echo", "type", "powershell", "pwsh", "ps", "git", "python", "python3", "pip", "jarvis", "taskmgr", "open", "cmd", "explorer", "calc", "notepad", "code", "subl", "firefox", "chrome", "brave", "spotify", "slack", "discord", "telegram", "pycharm", "gedit", "kate", "xdg-open", "gnome", "konsole", "xterm", "amixer", "free", "df", "uname", "lscpu", "hostname", "date", "whoami", "id", "pkill", "taskkill", "curl", "wget", "net", "ipconfig", "ping", "invoke-", "get-", "set-", "new-", "select-", "where-")
# App-launching keyword groups for get_response
_KW_BROWSERS = ("firefox", "browser", "internet")
_KW_CHROME = ("chrome", "google chrome")
_KW_VSCODE = ("vscode", "vs code", "open code")
_KW_SYSTEM_UTILITY = ("terminal", "console")
_KW_FILE_MANAGER = ("file manager", "open files")
_KW_CALCULATOR = ("calculator", "calc")
_KW_TASK_MANAGER = ("system monitor", "task manager")
_KW_TEXT_EDITOR = ("notepad", "text editor", "gedit", "kate")
_KW_VOLUME_UP = ("volume up", "louder", "increase volume")
_KW_VOLUME_DOWN = ("volume down", "quieter", "decrease volume")
_KW_MUTE = ("mute", "unmute", "toggle sound")
_KW_LOCK = ("lock screen", "lock computer", "lock session")
_KW_TIME_DATE = ("time", "date", "what day", "what time")
_KW_MEMORY = ("memory", "ram", "how much memory")
_KW_DISK = ("disk", "storage", "space", "hard drive")
_KW_IP_NETWORK = ("ip", "network", "internet", "connection")
_KW_PROCESS = ("process", "running", "what's running", "programs")
_KW_SYSTEM_INFO = ("system info", "system information", "computer info", "machine")
_KW_WHOAMI = ("who am i", "whoami", "my user")
_KW_SCREENSHOT = ("screenshot", "screen capture")
_KW_HELP = ("what can you do", "help", "capabilities")
_KW_THANKS = ("thank", "thanks")
_KW_SHUTDOWN = ("shut down", "shutdown", "bye", "goodbye")
_KW_TEMPERATURE = ("temperature", "cpu temp", "how hot")
_KW_BATTERY = ("battery", "charge", "power status")
_KW_SOUND = ("sound status", "audio devices")
_KW_RESOLUTION = ("resolution", "screen size")
_KW_PING = ("ping", "check internet", "online test")
_KW_SPOTIFY = ("spotify", "music")


class FallbackMatcher:
    """
    Best-effort offline command matcher for when no LLM provider is configured.

    Matches natural-language requests against a large set of known intents
    (file operations, git commands, system controls, app launching, etc.)
    and emits either a spoken response or a ``<run>...</run>`` command.

    Platform-awareness (Windows / macOS / Linux) is handled via instance
    flags that can be toggled for testing.
    """

    def __init__(
        self,
        add_to_history: Callable[[str, str], None],
        system_agent: Any = None,
        is_windows: bool = False,
        is_mac: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        add_to_history : callable
            A function ``(role: str, content: str) -> None`` used to record
            the user message and the generated response in conversation history.
        system_agent : SystemAgent or None
            When provided, unknown input may be translated to a raw command
            and executed immediately (see ``_translate``).
        is_windows : bool
        is_mac : bool
            Platform flags — should be set to match the current OS.
        """
        self._add_to_history: Callable[[str, str], None] = add_to_history
        self.system_agent: Any = system_agent
        self._IS_WINDOWS: bool = is_windows
        self._IS_MAC: bool = is_mac

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_response(self, user_message: str) -> str:
        """
        Main entry point.  Returns a spoken response string, possibly
        containing a ``<run>`` command tag.
        """
        msg_lower: str = user_message.lower().strip()
        # Local references for speed (hundreds of checks per call)
        _IS_WINDOWS: bool = self._IS_WINDOWS
        _IS_MAC: bool = self._IS_MAC

        def respond(text: str) -> str:
            self._add_to_history("user", user_message)
            self._add_to_history("assistant", text)
            return text

        # If this is a system execution result being fed back, just summarise it
        # and stop — do NOT try to match commands against the result output.
        if "[system execution result]" in msg_lower:
            stdout_match = _RE_SYSTEM_RESULT_STDOUT.search(user_message)
            stderr_match = _RE_SYSTEM_RESULT_STDERR.search(user_message)
            status_match = _RE_SYSTEM_RESULT_STATUS.search(user_message)
            exit_code_match = _RE_SYSTEM_RESULT_EXIT.search(user_message)

            stdout = stdout_match.group(1).strip() if stdout_match else ""
            stderr = stderr_match.group(1).strip() if stderr_match else ""
            status = status_match.group(1) if status_match else "unknown"
            exit_code = int(exit_code_match.group(1)) if exit_code_match else 0

            if status == "success" and exit_code == 0 and stdout:
                return respond(stdout)
            elif stderr or (status == "success" and exit_code != 0):
                error_text = stderr or f"Command exited with code {exit_code}"
                return respond(f"Command completed with an error: {error_text}")
            else:
                return respond("Command completed, Sir.")

        if any(w in msg_lower for w in _KW_GREETING):
            return respond("Hello Sir! I am JARVIS, currently in offline mode. I can still run basic commands for you. What would you like me to do?")

        # --- Weather ---
        if any(w in msg_lower for w in _KW_WEATHER):
            if _IS_WINDOWS:
                return respond("Checking the weather forecast, Sir. <run>(Invoke-WebRequest -Uri 'https://wttr.in?format=3' -UseBasicParsing).Content</run>")
            return respond("Checking the weather forecast, Sir. <run>curl -s wttr.in?format=3 || curl -s wttr.in</run>")

        # --- Create Folder (checked before generic listing so "create folder X" isn't caught by "folder") ---
        if any(w in msg_lower for w in _KW_CREATE_FOLDER):
            raw = msg_lower
            for phrase in ["create folder", "make directory", "create a folder", "new folder"]:
                raw = raw.replace(phrase, "")
            folder_name = _RE_SAFE_NAME.sub("_", raw.strip().replace("called", "").replace("named", "").strip()).strip("_")
            if folder_name:
                if _IS_WINDOWS:
                    return respond(f"Creating folder {folder_name}, Sir. <run>mkdir {folder_name}</run>")
                return respond(f"Creating folder {folder_name}, Sir. <run>mkdir -p {folder_name}; echo 'Created {folder_name}'</run>")
            else:
                return respond("What would you like to name the folder, Sir?")

        # --- Search (checked before generic listing so "search for python files" isn't caught by "files") ---
        if any(w in msg_lower for w in _KW_SEARCH):
            search_term = msg_lower.replace("search", "").replace("find", "").replace("for", "").strip()
            # Sanitize for shell safety: keep spaces (for multi-word searches) but remove shell metacharacters
            search_term = _RE_SAFE_SHELL.sub("", search_term).strip()
            if search_term:
                if _IS_WINDOWS:
                    return respond(f"Searching for {search_term}, Sir. <run>Get-ChildItem -Recurse -Filter '*{search_term}*' -ErrorAction SilentlyContinue | Select-Object FullName</run>")
                return respond(f"Searching for {search_term}, Sir. <run>find . -iname '*{search_term}*' -maxdepth 3 2>/dev/null</run>")
            else:
                return respond("What would you like me to search for, Sir?")

        # --- Directory Listings and Paths ---
        if any(w in msg_lower for w in _KW_LISTING):
            if _IS_WINDOWS:
                cmd = "Get-ChildItem -Force"
            else:
                cmd = "ls -la"
            return respond(f"Right away Sir. <run>{cmd}</run>")

        if any(w in msg_lower for w in _KW_PWD):
            if _IS_WINDOWS:
                return respond("Checking our current working path, Sir. <run>cd</run>")
            return respond("Checking our current working path, Sir. <run>pwd</run>")

        # --- Directory Navigation ---
        if any(w in msg_lower for w in _KW_NAV_HOME):
            if _IS_WINDOWS:
                return respond("Navigating to your home directory, Sir. <run>cd $env:USERPROFILE</run>")
            return respond("Navigating to your home directory, Sir. <run>cd ~</run>")

        if any(w in msg_lower for w in _KW_NAV_DOWNLOADS):
            if _IS_WINDOWS:
                return respond("Navigating to Downloads, Sir. <run>cd $env:USERPROFILE\\Downloads</run>")
            return respond("Navigating to Downloads, Sir. <run>cd ~/Downloads</run>")

        if any(w in msg_lower for w in _KW_NAV_DOCUMENTS):
            if _IS_WINDOWS:
                return respond("Navigating to Documents, Sir. <run>cd $env:USERPROFILE\\Documents</run>")
            return respond("Navigating to Documents, Sir. <run>cd ~/Documents</run>")

        if any(w in msg_lower for w in _KW_NAV_DESKTOP):
            if _IS_WINDOWS:
                return respond("Navigating to Desktop, Sir. <run>cd $env:USERPROFILE\\Desktop</run>")
            return respond("Navigating to Desktop, Sir. <run>cd ~/Desktop</run>")

        # --- File Actions ---
        if any(w in msg_lower for w in _KW_READ_FILE):
            raw = msg_lower
            for phrase in ["read file", "show file", "cat file", "open file", "read", "show"]:
                raw = raw.replace(phrase, "")
            file_name = raw.strip()
            # Sanitize path to prevent arbitrary shell injection
            file_name = _RE_SAFE_PATH.sub("", file_name)
            if file_name:
                if _IS_WINDOWS:
                    return respond(f"Reading file {file_name}, Sir. <run>type {file_name}</run>")
                return respond(f"Reading file {file_name}, Sir. <run>cat {file_name}</run>")
            else:
                return respond("Which file would you like me to read, Sir?")

        if any(w in msg_lower for w in _KW_DELETE_FILE):
            raw = msg_lower
            for phrase in ["delete file", "remove file", "delete", "remove"]:
                raw = raw.replace(phrase, "")
            file_name = raw.strip()
            file_name = _RE_SAFE_PATH.sub("", file_name)
            if file_name:
                if _IS_WINDOWS:
                    return respond(f"Removing file {file_name} with confirmation prompt, Sir. <run>del {file_name}</run>")
                return respond(f"Removing file {file_name} with confirmation prompt, Sir. <run>rm -i {file_name}</run>")
            else:
                return respond("Which file would you like me to delete, Sir?")

        # --- Kill / Stop Processes ---
        if any(w in msg_lower for w in _KW_KILL):
            proc_match = _RE_KILL_PROC.search(msg_lower)
            if proc_match:
                proc_name = proc_match.group(1)
                if _IS_WINDOWS:
                    return respond(
                        f"Killing {proc_name} processes, Sir. "
                        f"<run>taskkill /F /IM {proc_name}.exe</run>"
                    )
                return respond(
                    f"Killing {proc_name} processes, Sir. "
                    f"<run>pkill -f {proc_name}</run>"
                )
            else:
                if _IS_WINDOWS:
                    return respond("Kill what, Sir? Usage: kill chrome / kill notepad")
                return respond("Kill what, Sir? Usage: kill chrome / kill firefox")

        # --- Launching Web Browsers ---
        if any(w in msg_lower for w in _KW_BROWSERS):
            if _IS_WINDOWS:
                return respond("Launching Firefox in the background, Sir. <run>start firefox</run>")
            elif _IS_MAC:
                return respond("Launching Firefox, Sir. <run>open -a Firefox</run>")
            return respond("Launching Firefox in the background, Sir. <run>firefox &</run>")

        if any(w in msg_lower for w in _KW_CHROME):
            if _IS_WINDOWS:
                return respond("Launching Google Chrome, Sir. <run>start chrome</run>")
            elif _IS_MAC:
                return respond("Launching Google Chrome, Sir. <run>open -a 'Google Chrome'</run>")
            return respond("Launching Google Chrome, Sir. <run>google-chrome & || google-chrome-stable &</run>")

        if "brave" in msg_lower:
            if _IS_WINDOWS:
                return respond("Launching Brave Browser, Sir. <run>start brave</run>")
            elif _IS_MAC:
                return respond("Launching Brave Browser, Sir. <run>open -a 'Brave Browser'</run>")
            return respond("Launching Brave Browser, Sir. <run>brave-browser &</run>")

        # --- Launching Code Editors ---
        if any(w in msg_lower for w in _KW_VSCODE):
            if _IS_WINDOWS:
                return respond("Opening Visual Studio Code, Sir. <run>start code</run>")
            elif _IS_MAC:
                return respond("Opening Visual Studio Code, Sir. <run>open -a 'Visual Studio Code' .</run>")
            return respond("Opening Visual Studio Code, Sir. <run>code . &</run>")

        if "sublime" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening Sublime Text, Sir. <run>start subl</run>")
            elif _IS_MAC:
                return respond("Opening Sublime Text, Sir. <run>open -a 'Sublime Text'</run>")
            return respond("Opening Sublime Text, Sir. <run>subl &</run>")

        if "pycharm" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening PyCharm, Sir. <run>start pycharm</run>")
            elif _IS_MAC:
                return respond("Opening PyCharm, Sir. <run>open -a PyCharm</run>")
            return respond("Opening PyCharm, Sir. <run>pycharm &</run>")

        if "slack" in msg_lower:
            if _IS_WINDOWS:
                return respond("Launching Slack, Sir. <run>start slack</run>")
            elif _IS_MAC:
                return respond("Launching Slack, Sir. <run>open -a Slack</run>")
            return respond("Launching Slack, Sir. <run>slack &</run>")

        if "discord" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening Discord, Sir. <run>start discord</run>")
            elif _IS_MAC:
                return respond("Opening Discord, Sir. <run>open -a Discord</run>")
            return respond("Opening Discord, Sir. <run>discord &</run>")

        if "telegram" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening Telegram, Sir. <run>start telegram</run>")
            elif _IS_MAC:
                return respond("Opening Telegram, Sir. <run>open -a Telegram</run>")
            return respond("Opening Telegram, Sir. <run>telegram-desktop &</run>")

        if any(w in msg_lower for w in _KW_SPOTIFY):
            if _IS_WINDOWS:
                return respond("Opening Spotify, Sir. <run>start spotify</run>")
            elif _IS_MAC:
                return respond("Opening Spotify, Sir. <run>open -a Spotify</run>")
            return respond("Opening Spotify, Sir. <run>spotify &</run>")

        # --- Launching System Utilities ---
        if any(w in msg_lower for w in _KW_SYSTEM_UTILITY):
            if _IS_WINDOWS:
                return respond("Opening a terminal window, Sir. <run>powershell -NoExit</run>")
            elif _IS_MAC:
                return respond("Opening a terminal window, Sir. <run>open -a Terminal</run>")
            return respond("Opening a terminal window, Sir. <run>gnome-terminal & || konsole & || xterm &</run>")

        if any(w in msg_lower for w in _KW_FILE_MANAGER):
            if _IS_WINDOWS:
                return respond("Opening the file manager, Sir. <run>explorer .</run>")
            elif _IS_MAC:
                return respond("Opening the file manager, Sir. <run>open .</run>")
            return respond("Opening the file manager, Sir. <run>xdg-open . &</run>")

        if any(w in msg_lower for w in _KW_CALCULATOR):
            if _IS_WINDOWS:
                return respond("Opening the calculator, Sir. <run>calc</run>")
            elif _IS_MAC:
                return respond("Opening the calculator, Sir. <run>open -a Calculator</run>")
            return respond("Opening the calculator, Sir. <run>gnome-calculator & || kcalc &</run>")

        if any(w in msg_lower for w in _KW_TASK_MANAGER):
            if _IS_WINDOWS:
                return respond("Opening Task Manager, Sir. <run>taskmgr</run>")
            elif _IS_MAC:
                return respond("Opening Activity Monitor, Sir. <run>open -a 'Activity Monitor'</run>")
            return respond("Opening System Monitor, Sir. <run>gnome-system-monitor &</run>")

        if any(w in msg_lower for w in _KW_TEXT_EDITOR):
            if _IS_WINDOWS:
                return respond("Opening Notepad, Sir. <run>notepad</run>")
            elif _IS_MAC:
                return respond("Opening TextEdit, Sir. <run>open -a TextEdit</run>")
            return respond("Opening the text editor, Sir. <run>gedit & || kate & || mousepad &</run>")

        # --- Git Operations ---
        if any(w in msg_lower for w in ["git init", "init repo", "initialize repo"]):
            return respond("Initializing a new Git repository, Sir. <run>git init</run>")

        if any(w in msg_lower for w in ["git clone", "clone repo", "clone repository"]):
            raw = msg_lower.replace("git clone", "").replace("clone repo", "").replace("clone repository", "").strip()
            url = _RE_SAFE_URL.sub("", raw)
            if url:
                return respond(f"Cloning repository {url}, Sir. <run>git clone {url}</run>")
            else:
                return respond("I need a repository URL to clone. Please provide the URL, Sir.")

        # --- Staging ---
        if any(w in msg_lower for w in ["git add all", "stage all", "add everything", "stage everything"]):
            return respond("Staging all changes, Sir. <run>git add .</run>")

        if any(w in msg_lower for w in ["git add", "stage file", "stage"]):
            raw = msg_lower
            for phrase in ["git add", "stage file", "stage"]:
                raw = raw.replace(phrase, "")
            filename = _RE_SAFE_PATH.sub("", raw.strip())
            if filename:
                return respond(f"Staging {filename}, Sir. <run>git add {filename}</run>")
            else:
                return respond("Which file should I stage, Sir?")

        if any(w in msg_lower for w in ["git reset", "unstage"]):
            raw = msg_lower
            for phrase in ["git reset", "unstage"]:
                raw = raw.replace(phrase, "")
            filename = _RE_SAFE_PATH.sub("", raw.strip())
            if filename:
                return respond(f"Unstaging {filename}, Sir. <run>git reset HEAD {filename}</run>")
            else:
                return respond("Unstaging all files, Sir. <run>git reset HEAD</run>")

        if any(w in msg_lower for w in ["git rm", "remove file from git", "git delete file"]):
            raw = msg_lower
            for phrase in ["git rm", "remove file from git", "git delete file", "remove", "delete"]:
                raw = raw.replace(phrase, "")
            filename = _RE_SAFE_PATH.sub("", raw.strip())
            if filename:
                return respond(f"Removing {filename} from Git, Sir. <run>git rm {filename}</run>")
            else:
                return respond("Which file should I remove, Sir?")

        if any(w in msg_lower for w in ["git mv", "move file", "rename file"]):
            raw = msg_lower
            for phrase in ["git mv", "move file", "rename file", "move", "rename"]:
                raw = raw.replace(phrase, "")
            parts = raw.split()
            if len(parts) >= 2:
                return respond(f"Moving {parts[0]} to {parts[1]}, Sir. <run>git mv {parts[0]} {parts[1]}</run>")
            else:
                return respond("Please provide source and destination, Sir.")

        # --- Committing ---
        if any(w in msg_lower for w in ["git commit", "commit changes", "commit all"]):
            if "amend" in msg_lower:
                return respond("Amending last commit, Sir. <run>git commit --amend --no-edit</run>")
            raw = msg_lower
            for phrase in ["git commit", "commit changes", "commit all", "commit"]:
                raw = raw.replace(phrase, "")
            msg = raw.strip().strip("'\"")
            if msg:
                return respond(f"Committing with message: {msg}, Sir. <run>git commit -m '{msg}'</run>")
            else:
                return respond("Committing staged changes, Sir. <run>git commit -m 'Update from JARVIS'</run>")

        if any(w in msg_lower for w in ["git amend", "amend commit", "amend last commit"]):
            return respond("Amending last commit, Sir. <run>git commit --amend --no-edit</run>")

        # --- Branching ---
        if any(w in msg_lower for w in ["git branch", "git branches", "list branches"]):
            return respond("Listing branches, Sir. <run>git branch -a</run>")

        if any(w in msg_lower for w in ["create branch", "new branch", "git branch create"]):
            raw = msg_lower
            for phrase in ["create branch", "new branch", "git branch create", "create", "branch"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Creating branch {branch}, Sir. <run>git checkout -b {branch}</run>")
            else:
                return respond("What should I name the branch, Sir?")

        if any(w in msg_lower for w in ["delete branch", "remove branch", "git branch delete"]):
            raw = msg_lower
            for phrase in ["delete branch", "remove branch", "git branch delete", "delete", "remove"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Deleting branch {branch}, Sir. <run>git branch -d {branch}</run>")
            else:
                return respond("Which branch should I delete, Sir?")

        if any(w in msg_lower for w in ["git checkout", "switch branch", "checkout branch"]):
            raw = msg_lower
            for phrase in ["git checkout", "switch branch", "checkout branch", "switch to", "checkout"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Switching to {branch}, Sir. <run>git checkout {branch}</run>")
            else:
                return respond("Which branch should I switch to, Sir?")

        if any(w in msg_lower for w in ["git switch", "switch to branch"]):
            raw = msg_lower
            for phrase in ["git switch", "switch to branch", "switch to"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Switching to {branch}, Sir. <run>git switch {branch}</run>")
            else:
                return respond("Which branch should I switch to, Sir?")

        if any(w in msg_lower for w in ["git merge", "merge branch"]):
            raw = msg_lower
            for phrase in ["git merge", "merge branch", "merge"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Merging {branch} into current branch, Sir. <run>git merge {branch}</run>")
            else:
                return respond("Which branch should I merge, Sir?")

        # --- Remote ---
        if any(w in msg_lower for w in ["rename remote", "change remote name", "remote rename", "change the name of remote", "change name of remote", "change the name of"]):
            # Handle "git remote rename X Y" specifically
            git_rename_match = re.search(r"git\s+remote\s+rename\s+(\S+)\s+(\S+)", msg_lower)
            if git_rename_match:
                old_name, new_name = git_rename_match.group(1), git_rename_match.group(2)
                return respond(f"Renaming remote {old_name} to {new_name}, Sir. <run>git remote rename {old_name} {new_name}</run>")

            # Try regex: "rename X to Y", "change X to Y", "change the name of X to Y"
            rename_match = re.search(
                r"(?:rename|change(?:\s+the\s+name\s+of)?)\s+(?:remote\s+)?(\S+)\s+(?:to|into)\s+(\S+)",
                msg_lower
            )
            if not rename_match:
                # Try "from X to Y" pattern: "change the name of origin from JARVIS to origin"
                from_to_match = re.search(
                    r"(?:rename|change(?:\s+the\s+name\s+of)?)\s+(?:remote\s+)?(\S+)\s+from\s+(\S+)\s+to\s+(\S+)",
                    msg_lower
                )
                if from_to_match:
                    old_name, new_name = from_to_match.group(2), from_to_match.group(3)
                    return respond(f"Renaming remote {old_name} to {new_name}, Sir. <run>git remote rename {old_name} {new_name}</run>")

            if rename_match:
                old_name, new_name = rename_match.group(1), rename_match.group(2)
                return respond(f"Renaming remote {old_name} to {new_name}, Sir. <run>git remote rename {old_name} {new_name}</run>")

            # Fallback: try to extract from remaining words
            raw = msg_lower
            for phrase in ["rename remote", "change remote name", "remote rename", "rename", "change the name of remote", "change name of remote", "change the name of"]:
                raw = raw.replace(phrase, "")
            raw = raw.replace("to", " ").replace("from", " ").strip()
            parts = raw.split()
            if len(parts) >= 2:
                old_name, new_name = parts[0], parts[1]
                return respond(f"Renaming remote {old_name} to {new_name}, Sir. <run>git remote rename {old_name} {new_name}</run>")
            elif len(parts) == 1:
                return respond(f"What should I rename {parts[0]} to, Sir?")
            else:
                return respond("Which remote should I rename and to what name, Sir?")

        if any(w in msg_lower for w in ["remove remote", "delete remote", "git remote remove"]):
            raw = msg_lower
            for phrase in ["remove remote", "delete remote", "git remote remove", "remove", "delete"]:
                raw = raw.replace(phrase, "")
            name = _RE_SAFE_PATH.sub("", raw.strip())
            if name:
                return respond(f"Removing remote {name}, Sir. <run>git remote remove {name}</run>")
            else:
                return respond("Which remote should I remove, Sir?")

        if any(w in msg_lower for w in ["add remote", "git remote add"]):
            raw = msg_lower
            for phrase in ["add remote", "git remote add", "add"]:
                raw = raw.replace(phrase, "")
            parts = raw.split()
            if len(parts) >= 2:
                return respond(f"Adding remote {parts[0]}, Sir. <run>git remote add {parts[0]} {parts[1]}</run>")
            elif len(parts) == 1:
                return respond(f"What is the URL for remote {parts[0]}, Sir?")
            else:
                return respond("Please provide remote name and URL, Sir.")

        if any(w in msg_lower for w in ["git remote", "git remotes", "list remotes"]):
            return respond("Listing remote repositories, Sir. <run>git remote -v</run>")

        # --- Fetching & Pulling ---
        if any(w in msg_lower for w in ["git fetch", "fetch changes", "fetch remote"]):
            return respond("Fetching from remotes, Sir. <run>git fetch --all</run>")

        if any(w in msg_lower for w in ["git pull", "pull changes", "sync repo", "pull latest"]):
            return respond("Pulling latest changes, Sir. <run>git pull</run>")

        # --- Pushing ---
        if any(w in msg_lower for w in ["git push force", "force push", "force push changes"]):
            return respond("Force pushing, Sir. <run>git push --force-with-lease</run>")

        if any(w in msg_lower for w in ["git push", "push changes", "push to remote"]):
            return respond("Pushing to remote, Sir. <run>git push</run>")

        if any(w in msg_lower for w in ["git push all", "push all branches"]):
            return respond("Pushing all branches, Sir. <run>git push --all</run>")

        if any(w in msg_lower for w in ["git push tags", "push tags"]):
            return respond("Pushing all tags, Sir. <run>git push --tags</run>")

        # --- Stashing ---
        if any(w in msg_lower for w in ["git stash", "stash changes"]):
            return respond("Stashing current changes, Sir. <run>git stash</run>")

        if any(w in msg_lower for w in ["git stash pop", "unstash", "restore stash"]):
            return respond("Restoring stashed changes, Sir. <run>git stash pop</run>")

        if any(w in msg_lower for w in ["git stash list", "list stashes", "show stashes"]):
            return respond("Listing stashes, Sir. <run>git stash list</run>")

        if any(w in msg_lower for w in ["git stash drop", "drop stash"]):
            return respond("Dropping latest stash, Sir. <run>git stash drop</run>")

        if any(w in msg_lower for w in ["git stash clear", "clear stashes"]):
            return respond("Clearing all stashes, Sir. <run>git stash clear</run>")

        if any(w in msg_lower for w in ["git stash show", "show stash"]):
            return respond("Showing stash changes, Sir. <run>git stash show -p</run>")

        # --- Inspecting ---
        if any(w in msg_lower for w in ["git log", "recent commits", "commit history"]):
            return respond("Fetching recent commits, Sir. <run>git log -n 10 --oneline</run>")

        if any(w in msg_lower for w in ["git log graph", "log graph", "commit graph"]):
            return respond("Showing commit graph, Sir. <run>git log --oneline --graph --all</run>")

        if any(w in msg_lower for w in ["git log author", "commits by", "who committed"]):
            return respond("Showing commits by author, Sir. <run>git shortlog -sn</run>")

        if any(w in msg_lower for w in ["git diff", "show changes", "what changed"]):
            return respond("Showing uncommitted changes, Sir. <run>git diff</run>")

        if any(w in msg_lower for w in ["git diff staged", "show staged changes"]):
            return respond("Showing staged changes, Sir. <run>git diff --staged</run>")

        if any(w in msg_lower for w in ["git diff branch", "diff between branches"]):
            raw = msg_lower
            for phrase in ["git diff branch", "diff between branches", "diff"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Diffing current branch against {branch}, Sir. <run>git diff {branch}</run>")
            else:
                return respond("Which branch should I compare against, Sir?")

        if any(w in msg_lower for w in ["git show", "show commit", "show last commit"]):
            return respond("Showing last commit details, Sir. <run>git show --stat</run>")

        if any(w in msg_lower for w in ["git blame", "who wrote", "who changed", "who modified"]):
            raw = msg_lower
            for phrase in ["git blame", "who wrote", "who changed", "who modified"]:
                raw = raw.replace(phrase, "")
            filename = _RE_SAFE_PATH.sub("", raw.strip())
            if filename:
                return respond(f"Showing blame for {filename}, Sir. <run>git blame {filename}</run>")
            else:
                return respond("Showing blame for all files, Sir. <run>git blame . | head -30</run>")

        if any(w in msg_lower for w in ["git shortlog", "contributors", "who contributed"]):
            return respond("Showing contributor summary, Sir. <run>git shortlog -sn</run>")

        if any(w in msg_lower for w in ["git reflog", "recent activity", "git activity"]):
            return respond("Showing recent activity, Sir. <run>git reflog -n 10</run>")

        # --- Tagging ---
        if any(w in msg_lower for w in ["git tag", "list tags", "show tags"]):
            return respond("Listing tags, Sir. <run>git tag</run>")

        if any(w in msg_lower for w in ["create tag", "git tag create", "new tag"]):
            raw = msg_lower
            for phrase in ["create tag", "git tag create", "new tag", "create"]:
                raw = raw.replace(phrase, "")
            tag = _RE_SAFE_PATH.sub("", raw.strip())
            if tag:
                return respond(f"Creating tag {tag}, Sir. <run>git tag {tag}</run>")
            else:
                return respond("What should I name the tag, Sir?")

        if any(w in msg_lower for w in ["delete tag", "remove tag"]):
            raw = msg_lower
            for phrase in ["delete tag", "remove tag", "delete", "remove"]:
                raw = raw.replace(phrase, "")
            tag = _RE_SAFE_PATH.sub("", raw.strip())
            if tag:
                return respond(f"Deleting tag {tag}, Sir. <run>git tag -d {tag}</run>")
            else:
                return respond("Which tag should I delete, Sir?")

        # --- Undoing ---
        if any(w in msg_lower for w in ["git revert", "revert commit"]):
            return respond("Reverting last commit, Sir. <run>git revert HEAD</run>")

        if any(w in msg_lower for w in ["git restore", "discard changes"]):
            return respond("Discarding uncommitted changes, Sir. <run>git restore .</run>")

        if any(w in msg_lower for w in ["git restore file", "discard file"]):
            raw = msg_lower
            for phrase in ["git restore file", "discard file", "restore", "discard"]:
                raw = raw.replace(phrase, "")
            filename = _RE_SAFE_PATH.sub("", raw.strip())
            if filename:
                return respond(f"Discarding changes to {filename}, Sir. <run>git restore {filename}</run>")
            else:
                return respond("Which file should I restore, Sir?")

        if any(w in msg_lower for w in ["git reset hard", "hard reset", "reset everything"]):
            return respond("Hard resetting to last commit, Sir. <run>git reset --hard HEAD</run>")

        if any(w in msg_lower for w in ["git reset soft", "soft reset"]):
            return respond("Soft resetting to last commit, Sir. <run>git reset --soft HEAD</run>")

        # --- Cleaning ---
        if any(w in msg_lower for w in ["git clean", "remove untracked", "clean repo"]):
            return respond("Removing untracked files, Sir. <run>git clean -fd</run>")

        if any(w in msg_lower for w in ["git gc", "garbage collect", "optimize repo"]):
            return respond("Running garbage collection, Sir. <run>git gc</run>")

        # --- Config ---
        if any(w in msg_lower for w in ["git config", "show config", "git settings"]):
            return respond("Showing Git configuration, Sir. <run>git config --list</run>")

        if any(w in msg_lower for w in ["set user name", "git config name", "set git name"]):
            raw = msg_lower
            for phrase in ["set user name", "git config name", "set git name", "set", "name"]:
                raw = raw.replace(phrase, "")
            name = raw.replace("user", "").strip().strip("'\"")
            if name:
                return respond(f"Setting Git user name to {name}, Sir. <run>git config user.name '{name}'</run>")
            else:
                return respond("What name should I set, Sir?")

        if any(w in msg_lower for w in ["set user email", "git config email", "set git email"]):
            raw = msg_lower
            for phrase in ["set user email", "git config email", "set git email", "set", "email"]:
                raw = raw.replace(phrase, "")
            email = raw.replace("user", "").strip().strip("'\"")
            if email:
                return respond(f"Setting Git user email to {email}, Sir. <run>git config user.email '{email}'</run>")
            else:
                return respond("What email should I set, Sir?")

        # --- Branch Management ---
        if any(w in msg_lower for w in ["rename branch", "git branch rename", "git branch move"]):
            raw = msg_lower
            for phrase in ["rename branch", "git branch rename", "git branch move", "rename", "branch"]:
                raw = raw.replace(phrase, "")
            raw = raw.replace("to", " ").replace("from", " ").strip()
            parts = raw.split()
            if len(parts) >= 2:
                return respond(f"Renaming branch {parts[0]} to {parts[1]}, Sir. <run>git branch -m {parts[0]} {parts[1]}</run>")
            elif len(parts) == 1:
                return respond(f"What should I rename {parts[0]} to, Sir?")
            else:
                return respond("Which branch should I rename and to what name, Sir?")

        if any(w in msg_lower for w in ["force delete branch", "delete branch force"]):
            raw = msg_lower
            for phrase in ["force delete branch", "delete branch force", "force", "delete", "branch"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Force deleting branch {branch}, Sir. <run>git branch -D {branch}</run>")
            else:
                return respond("Which branch should I force delete, Sir?")

        if any(w in msg_lower for w in ["current branch", "which branch", "what branch"]):
            return respond("Showing current branch, Sir. <run>git branch --show-current</run>")

        # --- Advanced Staging ---
        if any(w in msg_lower for w in ["git add patch", "stage partially", "interactive stage"]):
            return respond("Interactive staging is not available in text mode. Please use 'git add -p' directly, Sir.")

        # --- Stash Advanced ---
        if any(w in msg_lower for w in ["git stash apply", "apply stash"]):
            return respond("Applying latest stash, Sir. <run>git stash apply</run>")

        if any(w in msg_lower for w in ["git stash branch", "stash to branch"]):
            raw = msg_lower
            for phrase in ["git stash branch", "stash to branch", "stash", "branch"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Creating branch {branch} from stash, Sir. <run>git stash branch {branch}</run>")
            else:
                return respond("What should I name the branch, Sir?")

        # --- Log Advanced ---
        if any(w in msg_lower for w in ["git log stat", "log with stats", "detailed log"]):
            return respond("Showing detailed log, Sir. <run>git log --stat -n 5</run>")

        if any(w in msg_lower for w in ["git log author", "commits by author", "who committed"]):
            raw = msg_lower
            for phrase in ["git log author", "commits by author", "who committed", "author", "by"]:
                raw = raw.replace(phrase, "")
            author = raw.strip().strip("'\"")
            if author:
                return respond(f"Showing commits by {author}, Sir. <run>git log --author='{author}' --oneline -n 10</run>")
            else:
                return respond("Showing contributor summary, Sir. <run>git shortlog -sn</run>")

        if any(w in msg_lower for w in ["git log since", "commits since", "changes since"]):
            raw = msg_lower
            for phrase in ["git log since", "commits since", "changes since", "since"]:
                raw = raw.replace(phrase, "")
            since = raw.strip()
            if since:
                return respond(f"Showing commits since {since}, Sir. <run>git log --since='{since}' --oneline</run>")
            else:
                return respond("Since when should I show commits, Sir?")

        if any(w in msg_lower for w in ["git log message", "search commits", "find commit"]):
            raw = msg_lower
            for phrase in ["git log message", "search commits", "find commit", "search", "find"]:
                raw = raw.replace(phrase, "")
            keyword = raw.strip().strip("'\"")
            if keyword:
                return respond(f"Searching commits for '{keyword}', Sir. <run>git log --grep='{keyword}' --oneline</run>")
            else:
                return respond("What should I search for in commits, Sir?")

        # --- Diff Advanced ---
        if any(w in msg_lower for w in ["git diff stat", "diff summary", "changes summary"]):
            return respond("Showing diff summary, Sir. <run>git diff --stat</run>")

        if any(w in msg_lower for w in ["git diff name", "changed files", "list changed files"]):
            return respond("Showing changed files, Sir. <run>git diff --name-only</run>")

        if any(w in msg_lower for w in ["git diff head", "diff against head"]):
            return respond("Diffing against HEAD, Sir. <run>git diff HEAD</run>")

        # --- Show Advanced ---
        if any(w in msg_lower for w in ["git show stat", "show commit stats"]):
            return respond("Showing commit with stats, Sir. <run>git show --stat</run>")

        if any(w in msg_lower for w in ["git show file", "show file at commit"]):
            raw = msg_lower
            for phrase in ["git show file", "show file at commit", "show", "file"]:
                raw = raw.replace(phrase, "")
            parts = raw.split()
            if len(parts) >= 2:
                return respond(f"Showing {parts[0]} at commit {parts[1]}, Sir. <run>git show {parts[1]}:{parts[0]}</run>")
            elif len(parts) == 1:
                return respond(f"At which commit should I show {parts[0]}, Sir?")
            else:
                return respond("Please provide file name and commit, Sir.")

        # --- Undoing Advanced ---
        if any(w in msg_lower for w in ["git revert commit", "revert specific commit"]):
            raw = msg_lower
            for phrase in ["git revert commit", "revert specific commit", "revert"]:
                raw = raw.replace(phrase, "")
            commit = _RE_SAFE_COMMIT.sub("", raw.strip())
            if commit:
                return respond(f"Reverting commit {commit}, Sir. <run>git revert {commit}</run>")
            else:
                return respond("Which commit should I revert, Sir?")

        if any(w in msg_lower for w in ["git reset commit", "reset to commit"]):
            raw = msg_lower
            for phrase in ["git reset commit", "reset to commit", "reset"]:
                raw = raw.replace(phrase, "")
            commit = _RE_SAFE_COMMIT.sub("", raw.strip())
            if commit:
                return respond(f"Resetting to commit {commit}, Sir. <run>git reset --hard {commit}</run>")
            else:
                return respond("Which commit should I reset to, Sir?")

        if any(w in msg_lower for w in ["undo last commit", "undo commit"]):
            if "soft" in msg_lower:
                return respond("Undoing last commit (keeping changes), Sir. <run>git reset --soft HEAD~1</run>")
            elif "hard" in msg_lower:
                return respond("Undoing last commit (discarding changes), Sir. <run>git reset --hard HEAD~1</run>")
            else:
                return respond("Undoing last commit (keeping changes), Sir. <run>git reset --soft HEAD~1</run>")

        # --- Cherry-pick ---
        if any(w in msg_lower for w in ["git cherry-pick", "cherry pick", "apply commit"]):
            raw = msg_lower
            for phrase in ["git cherry-pick", "cherry pick", "apply commit", "cherry-pick"]:
                raw = raw.replace(phrase, "")
            commit = _RE_SAFE_COMMIT.sub("", raw.strip())
            if commit:
                return respond(f"Cherry-picking commit {commit}, Sir. <run>git cherry-pick {commit}</run>")
            else:
                return respond("Which commit should I cherry-pick, Sir?")

        # --- Rebase ---
        if any(w in msg_lower for w in ["git rebase", "rebase branch"]):
            raw = msg_lower
            for phrase in ["git rebase", "rebase branch", "rebase"]:
                raw = raw.replace(phrase, "")
            branch = _RE_SAFE_PATH.sub("", raw.strip())
            if branch:
                return respond(f"Rebasing onto {branch}, Sir. <run>git rebase {branch}</run>")
            else:
                return respond("Rebasing onto current upstream, Sir. <run>git rebase</run>")

        if any(w in msg_lower for w in ["git rebase abort", "abort rebase"]):
            return respond("Aborting rebase, Sir. <run>git rebase --abort</run>")

        if any(w in msg_lower for w in ["git rebase continue", "continue rebase"]):
            return respond("Continuing rebase, Sir. <run>git rebase --continue</run>")

        # --- Submodule ---
        if any(w in msg_lower for w in ["git submodule", "list submodules"]):
            return respond("Listing submodules, Sir. <run>git submodule status</run>")

        if any(w in msg_lower for w in ["git submodule update", "update submodules"]):
            return respond("Updating submodules, Sir. <run>git submodule update --init --recursive</run>")

        if any(w in msg_lower for w in ["git submodule init", "init submodules"]):
            return respond("Initializing submodules, Sir. <run>git submodule init</run>")

        # --- Describe ---
        if any(w in msg_lower for w in ["git describe", "describe commit", "current version tag"]):
            return respond("Describing current commit, Sir. <run>git describe --tags</run>")

        # --- Verify ---
        if any(w in msg_lower for w in ["git verify", "verify commit", "check integrity"]):
            return respond("Verifying repository integrity, Sir. <run>git fsck</run>")

        # --- Count ---
        if any(w in msg_lower for w in ["git count", "count commits", "how many commits"]):
            return respond("Counting commits, Sir. <run>git rev-list --count HEAD</run>")

        # --- Docker Operations ---
        if any(w in msg_lower for w in ["docker containers", "docker running", "docker status"]):
            return respond("Listing Docker containers, Sir. <run>docker ps -a</run>")

        if "docker images" in msg_lower:
            return respond("Listing Docker images, Sir. <run>docker images</run>")

        # --- Basic Telemetry & Hardware Control ---
        if any(w in msg_lower for w in _KW_TEMPERATURE):
            if _IS_WINDOWS:
                return respond("Checking CPU temperature, Sir. <run>Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace 'root/wmi' | Select -ExpandProperty CurrentTemperature</run>")
            elif _IS_MAC:
                return respond("Checking CPU temperature, Sir. <run>pmset -g therm</run>")
            return respond("Checking CPU temperature, Sir. <run>sensors | grep -i temp || cat /sys/class/thermal/thermal_zone*/temp</run>")

        if any(w in msg_lower for w in _KW_BATTERY):
            if _IS_WINDOWS:
                return respond("Checking battery status, Sir. <run>Get-CimInstance -ClassName Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus</run>")
            elif _IS_MAC:
                return respond("Checking battery status, Sir. <run>pmset -g batt</run>")
            return respond("Checking battery status, Sir. <run>upower -i $(upower -e | grep 'BAT') | grep -E 'state|to full|percentage' || acpi -b || cat /sys/class/power_supply/BAT*/capacity</run>")

        if any(w in msg_lower for w in _KW_SOUND):
            if _IS_WINDOWS:
                return respond("Listing audio devices, Sir. <run>Get-CimInstance -ClassName Win32_SoundDevice | Select-Object Name, Status</run>")
            elif _IS_MAC:
                return respond("Listing audio devices, Sir. <run>system_profiler SPAudioDataType</run>")
            return respond("Listing audio devices, Sir. <run>aplay -l; arecord -l</run>")

        if any(w in msg_lower for w in _KW_RESOLUTION):
            if _IS_WINDOWS:
                return respond("Fetching display resolution, Sir. <run>Get-CimInstance -ClassName Win32_VideoController | Select-Object CurrentHorizontalResolution, CurrentVerticalResolution</run>")
            elif _IS_MAC:
                return respond("Fetching display resolution, Sir. <run>system_profiler SPDisplaysDataType | grep Resolution</run>")
            return respond("Fetching display resolution, Sir. <run>xrandr | grep '*' || xrandr</run>")

        if any(w in msg_lower for w in _KW_PING):
            if _IS_WINDOWS:
                return respond("Pinging test servers to verify connectivity, Sir. <run>ping -n 3 google.com</run>")
            return respond("Pinging test servers to verify connectivity, Sir. <run>ping -c 3 google.com</run>")

        # --- System Controls & Volume ---
        if any(w in msg_lower for w in _KW_LOCK):
            if _IS_WINDOWS:
                return respond("Locking the screen, Sir. <run>rundll32.exe user32.dll,LockWorkStation</run>")
            elif _IS_MAC:
                return respond("Locking the screen, Sir. <run>pmset displaysleepnow</run>")
            return respond("Locking the screen, Sir. <run>xdg-screensaver lock || gnome-screensaver-command -l || dbus-send --type=method_call --dest=org.gnome.ScreenSaver /org/gnome/ScreenSaver org.gnome.ScreenSaver.Lock</run>")

        if any(w in msg_lower for w in _KW_MUTE):
            if _IS_WINDOWS:
                return respond("Toggling master volume mute status, Sir. <run>$wsh = New-Object -ComObject WScript.Shell; $wsh.SendKeys([char]173)</run>")
            elif _IS_MAC:
                return respond("Toggling mute status, Sir. <run>osascript -e 'set volume with output muted'</run>")
            return respond("Toggling master volume mute status, Sir. <run>amixer sset Master toggle</run>")

        if any(w in msg_lower for w in _KW_VOLUME_UP):
            if _IS_WINDOWS:
                return respond("Increasing volume, Sir. <run>$wsh = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $wsh.SendKeys([char]175) }</run>")
            elif _IS_MAC:
                return respond("Increasing volume, Sir. <run>osascript -e 'set volume output volume ((output volume of (get volume settings)) + 10)'</run>")
            return respond("Increasing volume, Sir. <run>amixer sset Master 10%+</run>")

        if any(w in msg_lower for w in _KW_VOLUME_DOWN):
            if _IS_WINDOWS:
                return respond("Adjusting volume, Sir. <run>$wsh = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $wsh.SendKeys([char]174) }</run>")
            elif _IS_MAC:
                return respond("Decreasing volume, Sir. <run>osascript -e 'set volume output volume ((output volume of (get volume settings)) - 10)'</run>")
            return respond("Adjusting volume, Sir. <run>amixer sset Master 10%-</run>")

        if any(w in msg_lower for w in _KW_TIME_DATE):
            if _IS_WINDOWS:
                return respond("Let me check the time for you, Sir. <run>Get-Date -Format 'yyyy-MM-dd HH:mm:ss dddd'</run>")
            return respond("Let me check the time for you, Sir. <run>date</run>")

        if any(w in msg_lower for w in _KW_MEMORY):
            if _IS_WINDOWS:
                return respond("Checking memory usage now, Sir. <run>Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory | Format-List</run>")
            elif _IS_MAC:
                return respond("Checking memory usage now, Sir. <run>vm_stat</run>")
            return respond("Checking memory usage now, Sir. <run>free -h</run>")

        if any(w in msg_lower for w in _KW_DISK):
            if _IS_WINDOWS:
                return respond("Checking disk space, Sir. <run>Get-CimInstance -ClassName Win32_LogicalDisk | Select-Object DeviceID, @{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}}, @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,1)}} | Format-Table -AutoSize</run>")
            return respond("Checking disk space, Sir. <run>df -h</run>")

        if any(w in msg_lower for w in _KW_IP_NETWORK):
            if _IS_WINDOWS:
                return respond("Checking your network details, Sir. <run>ipconfig | findstr /i \"IPv4 Gateway\"</run>")
            elif _IS_MAC:
                return respond("Checking your network details, Sir. <run>ifconfig | grep 'inet ' | grep -v 127.0.0.1 | awk '{print $2}'</run>")
            return respond("Checking your network details, Sir. <run>hostname -I; ip route | grep default</run>")

        if any(w in msg_lower for w in _KW_PROCESS):
            if _IS_WINDOWS:
                return respond("Let me see what is currently running, Sir. <run>Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,1)}} | Format-Table -AutoSize</run>")
            elif _IS_MAC:
                return respond("Let me see what is currently running, Sir. <run>ps aux | sort -nr -k 4 | head -15</run>")
            return respond("Let me see what is currently running, Sir. <run>ps aux --sort=-%mem | head -15</run>")

        if any(w in msg_lower for w in _KW_SYSTEM_INFO):
            if _IS_WINDOWS:
                return respond("Pulling system information, Sir. <run>Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture | Format-List; Get-CimInstance -ClassName Win32_Processor | Select-Object Name | Format-List</run>")
            elif _IS_MAC:
                return respond("Pulling system information, Sir. <run>uname -a; sysctl -n machdep.cpu.brand_string</run>")
            return respond("Pulling system information, Sir. <run>uname -a; lscpu | grep \'Model name\'</run>")

        if any(w in msg_lower for w in _KW_WHOAMI):
            if _IS_WINDOWS:
                return respond("Identifying you, Sir. <run>Write-Host 'User:' $env:USERNAME; Write-Host 'Domain:' $env:USERDOMAIN; Write-Host 'PC:' $env:COMPUTERNAME</run>")
            return respond("Identifying you, Sir. <run>whoami; id</run>")

        if any(w in msg_lower for w in _KW_SCREENSHOT):
            if _IS_WINDOWS:
                return respond("Taking a screenshot, Sir. <run>Add-Type -AssemblyName System.Windows.Forms; $bmp = New-Object System.Drawing.Bitmap([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width, [System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen(0, 0, 0, 0, $bmp.Size); $path = Join-Path $env:USERPROFILE 'jarvis_screenshot.png'; $bmp.Save($path); Write-Host 'Saved.'</run>")
            elif _IS_MAC:
                return respond("Taking a screenshot, Sir. <run>screencapture ~/jarvis_screenshot.png; echo 'Saved.'</run>")
            return respond("Taking a screenshot, Sir. <run>gnome-screenshot -f ~/jarvis_screenshot.png; echo 'Saved.'</run>")

        if any(w in msg_lower for w in _KW_HELP):
            return respond(
                "I can list directories, search for files, open applications (Firefox, Chrome, VS Code, Slack, etc.), "
                "check system stats (RAM, disk, CPU temp, battery), query Git/Docker status, take screenshots, "
                "adjust volume, and check weather. Just ask, Sir."
            )

        if any(w in msg_lower for w in _KW_THANKS):
            return respond("Always at your service, Sir.")

        if any(w in msg_lower for w in _KW_SHUTDOWN):
            return respond("Shutting down. Goodbye Sir.")

        # Unknown input — translate natural language to a real command and
        # execute it directly so the user gets a spoken result (Option B).
        # Only do this if a system_agent is wired in; otherwise fall
        # back to the old wrap-and-let-the-loop-handle-it behaviour.
        if self.system_agent is not None:
            translated = self._translate(user_message)
            # Guard: refuse to blindly run something that looks dangerous.
            if translated and not self._command_is_dangerous(translated):
                res = self.system_agent.execute_command(translated)
                if res.get("status") == "success":
                    out = (res.get("stdout") or "").strip()
                    if out:
                        return respond(out)
                    err = (res.get("stderr") or "").strip()
                    if err:
                        return respond(f"Command finished with an error: {err}")
                    return respond("Command finished, Sir.")
                err = (res.get("stderr") or "").strip()
                if err:
                    return respond(f"I could not run that, Sir: {err}")
                return respond("I could not run that, Sir.")

        # No system_agent available (offline mode): inform the user instead
        # of blindly wrapping unknown input as a shell command.
        return respond(
            "I'm sorry Sir, I don't understand that request while in offline mode. "
            "I can check the time, list files, open applications, check system stats, and more. "
            "Please try again with a specific request."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _translate(self, user_message: str) -> str:
        """Best-effort natural-language -> shell command for offline mode.

        Returns a command string, or ``""`` if we cannot safely guess one.
        """
        m = user_message.lower().strip()
        if not m:
            return ""

        # Directory / file listing
        if any(w in m for w in _KW_TRANSLATE_LISTING):
            if self._IS_WINDOWS:
                return "Get-ChildItem -Force"
            return "ls -la"
        if "current directory" in m or "where am i" in m or "pwd" in m:
            if self._IS_WINDOWS:
                return "Get-Location"
            return "pwd"
        if "home" in m and ("folder" in m or "files" in m or "list" in m):
            if self._IS_WINDOWS:
                return "Get-ChildItem -Path $env:USERPROFILE -Force"
            return "ls -la ~"

        # Process listing
        if any(w in m for w in _KW_TRANSLATE_PROCESS):
            if self._IS_WINDOWS:
                return "Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name,CPU,WorkingSet64 | Format-Table -AutoSize"
            elif self._IS_MAC:
                return "ps aux | sort -nr -k 4 | head -15"
            return "ps aux --sort=-%mem | head -15"

        # Search for a file / pattern
        search_match = _RE_TRANSLATE_SEARCH.search(m)
        if search_match:
            term = search_match.group(1).strip().strip("'\"")
            term = _RE_SEARCH_TERM.sub("", term)
            if term:
                if self._IS_WINDOWS:
                    return f"Get-ChildItem -Recurse -Filter '*{term}*' -ErrorAction SilentlyContinue | Select-Object FullName"
                return f"find . -iname '*{term}*'"

        # Time / date
        if any(w in m for w in _KW_TRANSLATE_TIME):
            if self._IS_WINDOWS:
                return "Get-Date -Format 'yyyy-MM-dd HH:mm:ss dddd'"
            return "date"

        # Weather is not available offline
        if "weather" in m or "temperature outside" in m:
            return ""

        # Anything that already looks like a real command -> pass through
        if any(m.startswith(v) or m == v.strip() for v in _KW_TRANSLATE_RAW_COMMAND):
            return user_message.strip()

        return ""

    @staticmethod
    def _command_is_dangerous(command: str) -> bool:
        """Refuse to blindly execute commands that could harm the system."""
        c = command.lower().strip()
        for blocked in ("rm -rf /", "rm -rf /*", "format c:", "del /s /q",
                          "shutdown", "reboot", "halt", "poweroff",
                          "mkfs", "dd if=", "chmod -R 777 /",
                          "rd /s /q", "rmdir /s",
                          "remove-item -recurse", "format-volume",
                          "del /f /s"):
            if blocked in c:
                return True
        return False
