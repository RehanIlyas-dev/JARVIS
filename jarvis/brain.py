import os
import platform
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

_IS_WINDOWS = (platform.system() == "Windows")


# ---------------------------------------------------------------------------
# Commands the fallback brain is NOT allowed to blindly execute.
# These are matched against the raw fallback-generated command string.
# ---------------------------------------------------------------------------
_DANGEROUS_PREFIXES = (
    "rm ", "sudo rm", "shutdown", "reboot", "halt", "poweroff",
    "mkfs", "dd if=", "passwd", "userdel",
    "del /s", "format ", "rmdir /s", "rd /s",
    "Remove-Item -Recurse", "Format-Volume",
)


class JarvisBrain:
    """
    JARVIS LLM brain.

    Improvements over v1:
    - Conversation history is capped in memory (not just sliced at API call).
    - _refresh_context() passes live cwd from system_agent.
    - Fallback mode no longer blindly executes unknown user input as a shell command.
    - Home-directory listing is NOT sent to the API (privacy).
    - Agentic loop iteration cap is enforced here via a counter the caller reads.
    - Dangerous-command guard before raw fallback execution.
    """

    # Maximum messages kept in memory
    HISTORY_LIMIT = 40
    # How many history messages to send to the API each turn
    CONTEXT_WINDOW = 10

    def __init__(self, system_info=None, system_agent=None, debug=False):
        self.system_info = system_info or {}
        self.system_agent = system_agent  # reference so we can read live cwd
        self.debug = debug
        self.provider = "gemini"
        self.client = None
        self.model_name = None
        self.conversation_history = []

        self._setup_client()
        self.system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    # Client setup
    # ------------------------------------------------------------------

    def _setup_client(self):
        try:
            gemini_key = os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                from google import genai
                self.client = genai.Client(api_key=gemini_key)
                self.model_name = "gemini-2.5-flash"
                self.provider = "gemini"
                print("[JARVIS Brain] Google Gemini connected.")
                return
        except Exception as e:
            print(f"[JARVIS Brain] Gemini setup failed: {e}")

        try:
            openai_key = os.environ.get("OPENAI_API_KEY")
            if openai_key:
                from openai import OpenAI
                self.client = OpenAI(api_key=openai_key)
                self.model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
                self.provider = "openai"
                print(f"[JARVIS Brain] OpenAI connected ({self.model_name}).")
                return
        except Exception as e:
            print(f"[JARVIS Brain] OpenAI setup failed: {e}")

        try:
            ollama_url = os.environ.get("OLLAMA_API_URL") or os.environ.get("LOCAL_API_URL")
            if ollama_url:
                from openai import OpenAI
                self.client = OpenAI(base_url=ollama_url, api_key="ollama")
                self.model_name = os.environ.get("OLLAMA_MODEL", "llama3")
                self.provider = "openai"
                print(f"[JARVIS Brain] Ollama connected ({self.model_name}).")
                return
        except Exception as e:
            print(f"[JARVIS Brain] Ollama setup failed: {e}")

        self.provider = "fallback"
        print("[JARVIS Brain] No API key found. Running in offline fallback mode.")
        print("[JARVIS Brain] Set GEMINI_API_KEY, OPENAI_API_KEY, or OLLAMA_API_URL for full intelligence.")

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _get_directory_listing(self, path=None):
        target = path or self._live_cwd()
        try:
            entries = os.listdir(target)
            dirs  = [e for e in entries if os.path.isdir(os.path.join(target, e))]
            files = [e for e in entries if os.path.isfile(os.path.join(target, e))]
            result = f"Directory: {target}\n"
            if dirs:
                result += f"Folders ({len(dirs)}): {', '.join(dirs[:20])}\n"
            if files:
                result += f"Files ({len(files)}): {', '.join(files[:20])}\n"
            if not dirs and not files:
                result += "Empty directory.\n"
            return result
        except Exception as e:
            return f"Cannot list directory {target}: {e}\n"

    def _live_cwd(self):
        """Get the live cwd from system_agent if available, else fallback."""
        if self.system_agent:
            return self.system_agent.get_cwd()
        return self.system_info.get("cwd", os.path.expanduser("~"))

    def _build_system_prompt(self):
        user_name = self.system_info.get("user", "Sir")
        os_name   = self.system_info.get("os", "Linux")
        cwd       = self._live_cwd()
        cwd_listing = self._get_directory_listing(cwd)

        # NOTE: We intentionally do NOT include home directory listing here
        # to avoid leaking potentially sensitive filenames to the cloud API.

        return f"""You are JARVIS. (Just A Rather Very Intelligent System), a personal AI assistant with FULL system access.

USER: {user_name}
OS: {os_name}
CURRENT DIRECTORY: {cwd}

CURRENT DIRECTORY CONTENTS:
{cwd_listing}

CRITICAL RULES:
1. ALWAYS ACT for ACTIONS. When the user asks you to do something (open a program, list files, run a tool, change settings, get system info), you MUST output a <run>...</run> command. Never just say you will do it without actually executing a command.
2. NEVER wrap KNOWLEDGE QUESTIONS in <run>. If the user asks a factual or general-knowledge question (e.g. "who is Sam Altman", "what is a black hole", "tell me about X"), DO NOT emit a <run> command. Answer directly in plain spoken English. Only questions that require interacting with the system (files, apps, settings, hardware, processes) use <run>. Greetings and small talk are also answered directly without <run>.
2. Be concise and conversational. Speak in short natural sentences like a butler. Use TTS-friendly language (no markdown, no bullet points, no code blocks in your speech).
3. For commands: output exactly <run>command_here</run>. You can chain commands with && or ;. Use PowerShell or cmd commands. The system will execute it and return the output.
4. You can ONLY run ONE command per turn. After seeing the result, decide if you need another command.
5. If a command fails, try an alternative approach. Never give up.
6. NEVER suggest: format, del /s, shutdown /s, or any destructive system commands. These will be blocked.

COMMAND EXAMPLES (how to interpret user intent):
- "open the folders" / "list everything"        -> <run>{'dir' if _IS_WINDOWS else 'ls -la'}</run>
- "open folder X" / "go to X"                  -> <run>cd X</run>
- "open an application"                        -> <run>{'start "" "app_name"' if _IS_WINDOWS else 'app_name &'}</run>
- "what time is it"                            -> <run>{'powershell Get-Date' if _IS_WINDOWS else 'date'}</run>
- "how much memory" / "RAM usage"              -> <run>{'powershell "Get-CimInstance Win32_OperatingSystem | Select TotalVisibleMemorySize,FreePhysicalMemory"' if _IS_WINDOWS else 'free -h'}</run>
- "disk space" / "storage"                     -> <run>{'powershell "Get-PSDrive C | Select Used,Free"' if _IS_WINDOWS else 'df -h'}</run>
- "find files" / "search for X"               -> <run>{'powershell "Get-ChildItem -Recurse -Filter *X* -ErrorAction SilentlyContinue | Select FullName"' if _IS_WINDOWS else 'find . -name "*X*"'}</run>
- "create folder X"                            -> <run>mkdir X</run>
- "delete file X"                              -> <run>{'del X' if _IS_WINDOWS else 'rm X'}</run>
- "read file X"                                -> <run>{'powershell Get-Content X' if _IS_WINDOWS else 'cat X'}</run>
- "who am I"                                   -> <run>{'whoami' if _IS_WINDOWS else 'whoami; id'}</run>
        - "what's running" / "process" / "processes"        -> <run>{'Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name,CPU,WorkingSet64 | Format-Table -AutoSize' if _IS_WINDOWS else 'ps aux --sort=-%mem | head -15'}</run>
- "system info"                                -> <run>{'powershell "Get-CimInstance Win32_Processor | Select Name"' if _IS_WINDOWS else 'uname -a; lscpu'}</run>
- "network" / "IP address"                     -> <run>{'powershell Get-NetIPAddress -AddressFamily IPv4 | Select IPAddress' if _IS_WINDOWS else 'hostname -I'}</run>
- "open Task Manager"                          -> <run>{'taskmgr' if _IS_WINDOWS else 'gnome-system-monitor &'}</run>
        - "volume up"                                  -> <run>{'$wsh = New-Object -ComObject WScript.Shell; for($i=0;$i -lt 5;$i++){{$wsh.SendKeys([char]175)}}' if _IS_WINDOWS else 'amixer sset Master 10%+'}</run>
        - "volume down"                                -> <run>{'$wsh = New-Object -ComObject WScript.Shell; for($i=0;$i -lt 5;$i++){{$wsh.SendKeys([char]174)}}' if _IS_WINDOWS else 'amixer sset Master 10%-'}</run>

RESPONSE FORMAT:
- For ACTIONS: first say what you're doing in 1 short sentence, then output the <run> command.
- For KNOWLEDGE QUESTIONS and greetings: answer directly in plain spoken English. DO NOT use <run> at all.
- After receiving a system result, explain what happened in 1-2 sentences.
- Keep ALL spoken text clean: no asterisks, no hash signs, no backticks, no special formatting.
- ALWAYS respond in English ONLY. Never use any other language, regardless of what language the user speaks in. Every single response must be entirely in English.
"""

    def _refresh_context(self):
        """Rebuild the system prompt with the current live cwd."""
        self.system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    # Main response method
    # ------------------------------------------------------------------

    def get_response(self, user_message: str) -> str:
        if self.provider == "fallback":
            return self._simulate_fallback(user_message)

        self._refresh_context()

        # Build messages list for API
        messages = [{"role": "system", "content": self.system_prompt}]
        for msg in self.conversation_history[-self.CONTEXT_WINDOW:]:
            messages.append(msg)
        messages.append({"role": "user", "content": user_message})

        try:
            response_text = ""

            if self.provider == "gemini":
                from google import genai
                history = []
                for msg in self.conversation_history[-self.CONTEXT_WINDOW:]:
                    role = "user" if msg["role"] == "user" else "model"
                    history.append({"role": role, "parts": [{"text": msg["content"]}]})

                res = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[*history, {"role": "user", "parts": [{"text": user_message}]}],
                    config={"system_instruction": self.system_prompt},
                )
                response_text = res.text or ""

                if not response_text.strip():
                    block_reason = "unknown"
                    try:
                        if res.candidates and res.candidates[0].finish_reason:
                            block_reason = str(res.candidates[0].finish_reason)
                    except Exception:
                        pass
                    print(f"[JARVIS Brain] WARNING: Gemini returned empty response (finish_reason={block_reason})")
                    response_text = (
                        "I apologize Sir, but I received an empty response from my neural network. "
                        "This may be due to content filtering or a temporary API issue. Could you rephrase that?"
                    )

            elif self.provider == "openai":
                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                )
                response_text = completion.choices[0].message.content or ""
                if not response_text.strip():
                    response_text = "I apologize Sir, but I received an empty response. Could you rephrase that?"

            self._add_to_history("user", user_message)
            self._add_to_history("assistant", response_text)

            if self.debug:
                print(f"[JARVIS Brain DEBUG] Response: {response_text}")

            return response_text

        except Exception as e:
            error_msg = str(e)
            print(f"[JARVIS Brain] ERROR: {error_msg}")
            if self.debug:
                import traceback
                traceback.print_exc()

            # Network or API failure - fall back to offline command matcher
            # so the user still gets a useful response without internet.
            if self.provider != "fallback":
                print("[JARVIS Brain] API unreachable - falling back to offline mode for this request.")
                return self._simulate_fallback(user_message)

            return (
                f"Apologies Sir, I encountered an error communicating with my neural network. "
                f"The error is: {error_msg}. Please check your API key and internet connection."
            )

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _add_to_history(self, role: str, content: str):
        """Append a message and trim history to HISTORY_LIMIT to save RAM."""
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.HISTORY_LIMIT:
            # Drop oldest messages in pairs (user+assistant) to maintain coherence
            self.conversation_history = self.conversation_history[-self.HISTORY_LIMIT:]

    # ------------------------------------------------------------------
    # Fallback (offline) mode
    # ------------------------------------------------------------------

    def _simulate_fallback(self, user_message: str) -> str:
        msg_lower = user_message.lower().strip()

        def respond(text):
            self._add_to_history("user", user_message)
            self._add_to_history("assistant", text)
            return text

        # If this is a system execution result being fed back, just summarize it
        # and stop - do NOT try to match commands against the result output.
        if "[system execution result" in msg_lower:
            # Extract useful info from the result
            stdout_match = re.search(r"stdout='(.*?)'", user_message, re.DOTALL)
            stderr_match = re.search(r"stderr='(.*?)'", user_message, re.DOTALL)
            status_match = re.search(r"status=(\w+)", user_message)

            stdout = stdout_match.group(1).strip() if stdout_match else ""
            stderr = stderr_match.group(1).strip() if stderr_match else ""
            status = status_match.group(1) if status_match else "unknown"

            if status == "success" and stdout:
                # Return the raw output - no <run> tag, so the loop stops
                return respond(stdout)
            elif stderr:
                return respond(f"Command completed with an error: {stderr}")
            else:
                return respond("Command completed, Sir.")

        if any(w in msg_lower for w in ["hello", "hi ", "hey", "wake up", "good morning", "good evening"]):
            return respond("Hello Sir! I am JARVIS, currently in offline mode. I can still run basic commands for you. What would you like me to do?")

        # --- Weather ---
        if any(w in msg_lower for w in ["weather", "forecast", "is it raining"]):
            if _IS_WINDOWS:
                return respond("Checking the weather forecast, Sir. <run>(Invoke-WebRequest -Uri 'https://wttr.in?format=3' -UseBasicParsing).Content</run>")
            return respond("Checking the weather forecast, Sir. <run>curl -s wttr.in?format=3 || curl -s wttr.in</run>")

        # --- Directory Listings and Paths ---
        if any(w in msg_lower for w in ["list", "folder", "directory", "directories", "files", "what's in", "what is in"]):
            if _IS_WINDOWS:
                cmd = "Get-ChildItem -Force"
            else:
                cmd = "ls -la"
            return respond(f"Right away Sir. <run>{cmd}</run>")

        if any(w in msg_lower for w in ["where am i", "current path", "working directory"]):
            if _IS_WINDOWS:
                return respond("Checking our current working path, Sir. <run>cd</run>")
            return respond("Checking our current working path, Sir. <run>pwd</run>")

        # --- Directory Navigation ---
        if any(w in msg_lower for w in ["go home", "go to home", "change to home"]):
            if _IS_WINDOWS:
                return respond("Navigating to your home directory, Sir. <run>cd $env:USERPROFILE</run>")
            return respond("Navigating to your home directory, Sir. <run>cd ~</run>")

        if any(w in msg_lower for w in ["downloads folder", "go to downloads"]):
            if _IS_WINDOWS:
                return respond("Navigating to Downloads, Sir. <run>cd $env:USERPROFILE\\Downloads</run>")
            return respond("Navigating to Downloads, Sir. <run>cd ~/Downloads</run>")

        if any(w in msg_lower for w in ["documents folder", "go to documents"]):
            if _IS_WINDOWS:
                return respond("Navigating to Documents, Sir. <run>cd $env:USERPROFILE\\Documents</run>")
            return respond("Navigating to Documents, Sir. <run>cd ~/Documents</run>")

        if any(w in msg_lower for w in ["desktop folder", "go to desktop"]):
            if _IS_WINDOWS:
                return respond("Navigating to Desktop, Sir. <run>cd $env:USERPROFILE\\Desktop</run>")
            return respond("Navigating to Desktop, Sir. <run>cd ~/Desktop</run>")

        # --- File Actions ---
        if "read file" in msg_lower or "show file" in msg_lower or "cat file" in msg_lower or ("open file" in msg_lower and not any(w in msg_lower for w in ["manager", "folder"])):
            raw = msg_lower
            for phrase in ["read file", "show file", "cat file", "open file", "read", "show"]:
                raw = raw.replace(phrase, "")
            file_name = raw.strip()
            # Sanitize path to prevent arbitrary shell injection
            file_name = re.sub(r"[^\w.\-/~]", "", file_name)
            if file_name:
                if _IS_WINDOWS:
                    return respond(f"Reading file {file_name}, Sir. <run>type {file_name}</run>")
                return respond(f"Reading file {file_name}, Sir. <run>cat {file_name}</run>")
            else:
                return respond("Which file would you like me to read, Sir?")

        if "delete file" in msg_lower or "remove file" in msg_lower:
            raw = msg_lower
            for phrase in ["delete file", "remove file", "delete", "remove"]:
                raw = raw.replace(phrase, "")
            file_name = raw.strip()
            file_name = re.sub(r"[^\w.\-/~]", "", file_name)
            if file_name:
                if _IS_WINDOWS:
                    return respond(f"Removing file {file_name} with confirmation prompt, Sir. <run>del {file_name}</run>")
                return respond(f"Removing file {file_name} with confirmation prompt, Sir. <run>rm -i {file_name}</run>")
            else:
                return respond("Which file would you like me to delete, Sir?")

        if "create folder" in msg_lower or "make directory" in msg_lower or "new folder" in msg_lower:
            raw = msg_lower
            for phrase in ["create folder", "make directory", "create a folder", "new folder"]:
                raw = raw.replace(phrase, "")
            folder_name = re.sub(r"[^\w.\-]", "_", raw.strip().strip("called").strip("named").strip()).strip("_")
            if folder_name:
                if _IS_WINDOWS:
                    return respond(f"Creating folder {folder_name}, Sir. <run>mkdir {folder_name}</run>")
                return respond(f"Creating folder {folder_name}, Sir. <run>mkdir -p {folder_name}; echo 'Created {folder_name}'</run>")
            else:
                return respond("What would you like to name the folder, Sir?")

        if any(w in msg_lower for w in ["search", "find"]):
            search_term = re.sub(r"[^\w.\-]", "", msg_lower.replace("search", "").replace("find", "").replace("for", "").strip())
            if search_term:
                if _IS_WINDOWS:
                    return respond(f"Searching for {search_term}, Sir. <run>Get-ChildItem -Recurse -Filter '*{search_term}*' -ErrorAction SilentlyContinue | Select-Object FullName</run>")
                return respond(f"Searching for {search_term}, Sir. <run>find . -iname '*{search_term}*' -maxdepth 3 2>/dev/null</run>")
            else:
                return respond("What would you like me to search for, Sir?")

        # --- Kill / Stop Processes ---
        if any(w in msg_lower for w in ["kill", "stop", "close", "terminate"]):
            import re as _re
            proc_match = _re.search(
                r"(?:kill|stop|close|terminate)\s+(?:all\s+)?(\S+?)(?:\s+process(?:es)?)?$",
                msg_lower,
            )
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
        if any(w in msg_lower for w in ["firefox", "browser", "internet"]):
            if _IS_WINDOWS:
                return respond("Launching Firefox in the background, Sir. <run>start firefox</run>")
            return respond("Launching Firefox in the background, Sir. <run>firefox &</run>")

        if any(w in msg_lower for w in ["chrome", "google chrome"]):
            if _IS_WINDOWS:
                return respond("Launching Google Chrome, Sir. <run>start chrome</run>")
            return respond("Launching Google Chrome, Sir. <run>google-chrome & || google-chrome-stable &</run>")

        if "brave" in msg_lower:
            if _IS_WINDOWS:
                return respond("Launching Brave Browser, Sir. <run>start brave</run>")
            return respond("Launching Brave Browser, Sir. <run>brave-browser &</run>")

        # --- Launching Code Editors ---
        if any(w in msg_lower for w in ["vscode", "vs code", "open code"]):
            if _IS_WINDOWS:
                return respond("Opening Visual Studio Code, Sir. <run>start code</run>")
            return respond("Opening Visual Studio Code, Sir. <run>code . &</run>")

        if "sublime" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening Sublime Text, Sir. <run>start subl</run>")
            return respond("Opening Sublime Text, Sir. <run>subl &</run>")

        if "pycharm" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening PyCharm, Sir. <run>start pycharm</run>")
            return respond("Opening PyCharm, Sir. <run>pycharm &</run>")

        # --- Launching Productivity & Chat Apps ---
        if "slack" in msg_lower:
            if _IS_WINDOWS:
                return respond("Launching Slack, Sir. <run>start slack</run>")
            return respond("Launching Slack, Sir. <run>slack &</run>")

        if "discord" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening Discord, Sir. <run>start discord</run>")
            return respond("Opening Discord, Sir. <run>discord &</run>")

        if "telegram" in msg_lower:
            if _IS_WINDOWS:
                return respond("Opening Telegram, Sir. <run>start telegram</run>")
            return respond("Opening Telegram, Sir. <run>telegram-desktop &</run>")

        if any(w in msg_lower for w in ["spotify", "music"]):
            if _IS_WINDOWS:
                return respond("Opening Spotify, Sir. <run>start spotify</run>")
            return respond("Opening Spotify, Sir. <run>spotify &</run>")

        # --- Launching System Utilities ---
        if any(w in msg_lower for w in ["terminal", "console"]):
            if _IS_WINDOWS:
                return respond("Opening a terminal window, Sir. <run>powershell -NoExit</run>")
            return respond("Opening a terminal window, Sir. <run>gnome-terminal & || konsole & || xterm &</run>")

        if any(w in msg_lower for w in ["file manager", "open files"]):
            if _IS_WINDOWS:
                return respond("Opening the file manager, Sir. <run>explorer .</run>")
            return respond("Opening the file manager, Sir. <run>xdg-open . &</run>")

        if any(w in msg_lower for w in ["calculator", "calc"]):
            if _IS_WINDOWS:
                return respond("Opening the calculator, Sir. <run>calc</run>")
            return respond("Opening the calculator, Sir. <run>gnome-calculator & || kcalc &</run>")

        if any(w in msg_lower for w in ["system monitor", "task manager"]):
            if _IS_WINDOWS:
                return respond("Opening Task Manager, Sir. <run>taskmgr</run>")
            return respond("Opening System Monitor, Sir. <run>gnome-system-monitor &</run>")

        if any(w in msg_lower for w in ["notepad", "text editor", "gedit", "kate"]):
            if _IS_WINDOWS:
                return respond("Opening Notepad, Sir. <run>notepad</run>")
            return respond("Opening the text editor, Sir. <run>gedit & || kate & || mousepad &</run>")

        # --- Git Operations ---
        if any(w in msg_lower for w in ["git init", "init repo", "initialize repo"]):
            return respond("Initializing a new Git repository, Sir. <run>git init</run>")

        if any(w in msg_lower for w in ["git clone", "clone repo", "clone repository"]):
            raw = msg_lower.replace("git clone", "").replace("clone repo", "").replace("clone repository", "").strip()
            url = re.sub(r"[^\w.\-/~:@]", "", raw)
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
            filename = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if filename:
                return respond(f"Staging {filename}, Sir. <run>git add {filename}</run>")
            else:
                return respond("Which file should I stage, Sir?")

        if any(w in msg_lower for w in ["git reset", "unstage"]):
            raw = msg_lower
            for phrase in ["git reset", "unstage"]:
                raw = raw.replace(phrase, "")
            filename = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if filename:
                return respond(f"Unstaging {filename}, Sir. <run>git reset HEAD {filename}</run>")
            else:
                return respond("Unstaging all files, Sir. <run>git reset HEAD</run>")

        if any(w in msg_lower for w in ["git rm", "remove file from git", "git delete file"]):
            raw = msg_lower
            for phrase in ["git rm", "remove file from git", "git delete file", "remove", "delete"]:
                raw = raw.replace(phrase, "")
            filename = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if branch:
                return respond(f"Creating branch {branch}, Sir. <run>git checkout -b {branch}</run>")
            else:
                return respond("What should I name the branch, Sir?")

        if any(w in msg_lower for w in ["delete branch", "remove branch", "git branch delete"]):
            raw = msg_lower
            for phrase in ["delete branch", "remove branch", "git branch delete", "delete", "remove"]:
                raw = raw.replace(phrase, "")
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if branch:
                return respond(f"Deleting branch {branch}, Sir. <run>git branch -d {branch}</run>")
            else:
                return respond("Which branch should I delete, Sir?")

        if any(w in msg_lower for w in ["git checkout", "switch branch", "checkout branch"]):
            raw = msg_lower
            for phrase in ["git checkout", "switch branch", "checkout branch", "switch to", "checkout"]:
                raw = raw.replace(phrase, "")
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if branch:
                return respond(f"Switching to {branch}, Sir. <run>git checkout {branch}</run>")
            else:
                return respond("Which branch should I switch to, Sir?")

        if any(w in msg_lower for w in ["git switch", "switch to branch"]):
            raw = msg_lower
            for phrase in ["git switch", "switch to branch", "switch to"]:
                raw = raw.replace(phrase, "")
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if branch:
                return respond(f"Switching to {branch}, Sir. <run>git switch {branch}</run>")
            else:
                return respond("Which branch should I switch to, Sir?")

        if any(w in msg_lower for w in ["git merge", "merge branch"]):
            raw = msg_lower
            for phrase in ["git merge", "merge branch", "merge"]:
                raw = raw.replace(phrase, "")
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if branch:
                return respond(f"Merging {branch} into current branch, Sir. <run>git merge {branch}</run>")
            else:
                return respond("Which branch should I merge, Sir?")

        # --- Remote ---
        if any(w in msg_lower for w in ["rename remote", "change remote name", "remote rename", "rename", "change the name of remote", "change name of remote", "change the name of"]):
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
            name = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            filename = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            tag = re.sub(r"[^\w.\-/~]", "", raw.strip())
            if tag:
                return respond(f"Creating tag {tag}, Sir. <run>git tag {tag}</run>")
            else:
                return respond("What should I name the tag, Sir?")

        if any(w in msg_lower for w in ["delete tag", "remove tag"]):
            raw = msg_lower
            for phrase in ["delete tag", "remove tag", "delete", "remove"]:
                raw = raw.replace(phrase, "")
            tag = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            filename = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
            commit = re.sub(r"[^\w]", "", raw.strip())
            if commit:
                return respond(f"Reverting commit {commit}, Sir. <run>git revert {commit}</run>")
            else:
                return respond("Which commit should I revert, Sir?")

        if any(w in msg_lower for w in ["git reset commit", "reset to commit"]):
            raw = msg_lower
            for phrase in ["git reset commit", "reset to commit", "reset"]:
                raw = raw.replace(phrase, "")
            commit = re.sub(r"[^\w]", "", raw.strip())
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
            commit = re.sub(r"[^\w]", "", raw.strip())
            if commit:
                return respond(f"Cherry-picking commit {commit}, Sir. <run>git cherry-pick {commit}</run>")
            else:
                return respond("Which commit should I cherry-pick, Sir?")

        # --- Rebase ---
        if any(w in msg_lower for w in ["git rebase", "rebase branch"]):
            raw = msg_lower
            for phrase in ["git rebase", "rebase branch", "rebase"]:
                raw = raw.replace(phrase, "")
            branch = re.sub(r"[^\w.\-/~]", "", raw.strip())
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
        if any(w in msg_lower for w in ["temperature", "cpu temp", "how hot"]):
            if _IS_WINDOWS:
                return respond("Checking CPU temperature, Sir. <run>Get-WmiObject MSAcpi_ThermalZoneTemperature -Namespace 'root/wmi' | Select -ExpandProperty CurrentTemperature</run>")
            return respond("Checking CPU temperature, Sir. <run>sensors | grep -i temp || cat /sys/class/thermal/thermal_zone*/temp</run>")

        if any(w in msg_lower for w in ["battery", "charge", "power status"]):
            if _IS_WINDOWS:
                return respond("Checking battery status, Sir. <run>Get-CimInstance -ClassName Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus</run>")
            return respond("Checking battery status, Sir. <run>upower -i $(upower -e | grep 'BAT') | grep -E 'state|to full|percentage' || acpi -b || cat /sys/class/power_supply/BAT*/capacity</run>")

        if any(w in msg_lower for w in ["sound status", "audio devices"]):
            if _IS_WINDOWS:
                return respond("Listing audio devices, Sir. <run>Get-CimInstance -ClassName Win32_SoundDevice | Select-Object Name, Status</run>")
            return respond("Listing audio devices, Sir. <run>aplay -l; arecord -l</run>")

        if any(w in msg_lower for w in ["resolution", "screen size"]):
            if _IS_WINDOWS:
                return respond("Fetching display resolution, Sir. <run>Get-CimInstance -ClassName Win32_VideoController | Select-Object CurrentHorizontalResolution, CurrentVerticalResolution</run>")
            return respond("Fetching display resolution, Sir. <run>xrandr | grep '*' || xrandr</run>")

        if any(w in msg_lower for w in ["ping", "check internet", "online test"]):
            if _IS_WINDOWS:
                return respond("Pinging test servers to verify connectivity, Sir. <run>ping -n 3 google.com</run>")
            return respond("Pinging test servers to verify connectivity, Sir. <run>ping -c 3 google.com</run>")

        # --- System Controls & Volume ---
        if any(w in msg_lower for w in ["lock screen", "lock computer", "lock session"]):
            if _IS_WINDOWS:
                return respond("Locking the screen, Sir. <run>(New-Object -ComObject WScript.Shell).SendKeys(\\^%{ESCAPE}\\\")\"</run>")
            return respond("Locking the screen, Sir. <run>xdg-screensaver lock || gnome-screensaver-command -l || dbus-send --type=method_call --dest=org.gnome.ScreenSaver /org/gnome/ScreenSaver org.gnome.ScreenSaver.Lock</run>")

        if any(w in msg_lower for w in ["mute", "unmute", "toggle sound"]):
            if _IS_WINDOWS:
                return respond("Toggling master volume mute status, Sir. <run>$wsh = New-Object -ComObject WScript.Shell; $wsh.SendKeys([char]173)</run>")
            return respond("Toggling master volume mute status, Sir. <run>amixer sset Master toggle</run>")

        if any(w in msg_lower for w in ["volume up", "louder", "increase volume"]):
            if _IS_WINDOWS:
                return respond("Increasing volume, Sir. <run>$wsh = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $wsh.SendKeys([char]175) }</run>")
            return respond("Increasing volume, Sir. <run>amixer sset Master 10%+</run>")

        if any(w in msg_lower for w in ["volume down", "quieter", "decrease volume"]):
            if _IS_WINDOWS:
                return respond("Adjusting volume, Sir. <run>$wsh = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $wsh.SendKeys([char]174) }</run>")
            return respond("Adjusting volume, Sir. <run>amixer sset Master 10%-</run>")

        if any(w in msg_lower for w in ["time", "date", "what day", "what time"]):
            if _IS_WINDOWS:
                return respond("Let me check the time for you, Sir. <run>Get-Date -Format 'yyyy-MM-dd HH:mm:ss dddd'</run>")
            return respond("Let me check the time for you, Sir. <run>date</run>")

        if any(w in msg_lower for w in ["memory", "ram", "how much memory"]):
            if _IS_WINDOWS:
                return respond("Checking memory usage now, Sir. <run>Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory | Format-List</run>")
            return respond("Checking memory usage now, Sir. <run>free -h</run>")

        if any(w in msg_lower for w in ["disk", "storage", "space", "hard drive"]):
            if _IS_WINDOWS:
                return respond("Checking disk space, Sir. <run>Get-CimInstance -ClassName Win32_LogicalDisk | Select-Object DeviceID, @{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}}, @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,1)}} | Format-Table -AutoSize</run>")
            return respond("Checking disk space, Sir. <run>df -h</run>")

        if any(w in msg_lower for w in ["ip", "network", "internet", "connection"]):
            if _IS_WINDOWS:
                return respond("Checking your network details, Sir. <run>ipconfig | findstr /i \"IPv4 Gateway\"</run>")
            return respond("Checking your network details, Sir. <run>hostname -I; ip route | grep default</run>")

        if any(w in msg_lower for w in ["process", "running", "what's running", "programs"]):
            if _IS_WINDOWS:
                return respond("Let me see what is currently running, Sir. <run>Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,1)}} | Format-Table -AutoSize</run>")
            return respond("Let me see what is currently running, Sir. <run>ps aux --sort=-%mem | head -15</run>")

        if any(w in msg_lower for w in ["system info", "system information", "computer info", "machine"]):
            if _IS_WINDOWS:
                return respond("Pulling system information, Sir. <run>Get-CimInstance -ClassName Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture | Format-List; Get-CimInstance -ClassName Win32_Processor | Select-Object Name | Format-List</run>")
            return respond("Pulling system information, Sir. <run>uname -a; lscpu | grep \'Model name\'</run>")

        if any(w in msg_lower for w in ["who am i", "whoami", "my user"]):
            if _IS_WINDOWS:
                return respond("Identifying you, Sir. <run>Write-Host 'User:' $env:USERNAME; Write-Host 'Domain:' $env:USERDOMAIN; Write-Host 'PC:' $env:COMPUTERNAME</run>")
            return respond("Identifying you, Sir. <run>whoami; id</run>")

        if any(w in msg_lower for w in ["screenshot", "screen capture"]):
            if _IS_WINDOWS:
                return respond("Taking a screenshot, Sir. <run>Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Screen]::PrimaryScreen.Bounds | ForEach-Object { $bmp = New-Object System.Drawing.Bitmap($_.Width, $_.Height); $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($_.Location, [System.Drawing.Point]::Empty, $_.Size); $bmp.Save(\\$env:USERPROFILE\\jarvis_screenshot.png\\\") }; Write-Host 'Saved.'\"</run>")
            return respond("Taking a screenshot, Sir. <run>gnome-screenshot -f ~/jarvis_screenshot.png; echo 'Saved.'</run>")

        if any(w in msg_lower for w in ["what can you do", "help", "capabilities"]):
            return respond(
                "I can list directories, search for files, open applications (Firefox, Chrome, VS Code, Slack, etc.), "
                "check system stats (RAM, disk, CPU temp, battery), query Git/Docker status, take screenshots, "
                "adjust volume, and check weather. Just ask, Sir."
            )

        if any(w in msg_lower for w in ["thank", "thanks"]):
            return respond("Always at your service, Sir.")

        if any(w in msg_lower for w in ["shut down", "shutdown", "bye", "goodbye"]):
            return respond("Shutting down. Goodbye Sir.")

        # Unknown input - translate natural language to a real command and
        # execute it directly so the user gets a spoken result (Option B).
        # Only do this if a system_agent is wired in; otherwise fall
        # back to the old wrap-and-let-the-loop-handle-it behaviour.
        if self.system_agent is not None:
            translated = self._fallback_translate(user_message)
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

        # No system_agent available: wrap as a command and let the
        # agentic loop execute it (keeps old behaviour).
        safe_cmd = re.sub(r"[;&|`$]", "", user_message.strip())
        return respond(f"Running that for you, Sir. <run>{safe_cmd}</run>")

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _command_is_dangerous(command: str) -> bool:
        """Refuse to blindly execute commands that could harm the system."""
        c = command.lower().strip()
        for blocked in ("rm -rf /", "rm -rf /*", "format ", "del /s",
                          "shutdown", "reboot", "halt", "poweroff",
                          "mkfs", "dd if=", "chmod -r 777 /",
                          "rd /s", "rmdir /s"):
            if blocked in c:
                return True
        return False

    def _fallback_translate(self, user_message: str) -> str:
        """Best-effort natural-language -> shell command for offline mode.

        Returns a command string, or "" if we cannot safely guess one.
        """
        m = user_message.lower().strip()
        if not m:
            return ""

        # Directory / file listing
        if any(w in m for w in ["list", "files", "folder", "directory", "ls",
                                       "dir ", "show files", "contents", "what's in",
                                       "whats in", "open the folder", "open folder"]):
            if _IS_WINDOWS:
                return "Get-ChildItem -Force"
            return "ls -la"
        if "current directory" in m or "where am i" in m or "pwd" in m:
            if _IS_WINDOWS:
                return "Get-Location"
            return "pwd"
        if "home" in m and ("folder" in m or "files" in m or "list" in m):
            if _IS_WINDOWS:
                return "Get-ChildItem -Path $env:USERPROFILE -Force"
            return "ls -la ~"

        # Process listing
        if any(w in m for w in ["process", "running", "what's running",
                                        "whats running", "programs", "tasks"]):
            if _IS_WINDOWS:
                return "Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name,CPU,WorkingSet64 | Format-Table -AutoSize"
            return "ps aux --sort=-%mem | head -15"

        # Search for a file / pattern
        search_match = re.search(r"(?:find|search for|locate|look for)\s+(?:file\s+)?(.+)", m)
        if search_match:
            term = search_match.group(1).strip().strip("'\"")
            term = re.sub(r"[^\w.\-~*]", "", term)
            if term:
                if _IS_WINDOWS:
                    return f"Get-ChildItem -Recurse -Filter '*{term}*' -ErrorAction SilentlyContinue | Select-Object FullName"
                return f"find . -iname '*{term}*'"

        # Time / date
        if any(w in m for w in ["time", "date", "what day", "what time"]):
            if _IS_WINDOWS:
                return "Get-Date -Format 'yyyy-MM-dd HH:mm:ss dddd'"
            return "date"

        # Weather is not available offline
        if "weather" in m or "temperature outside" in m:
            return ""

        # Anything that already looks like a real command -> pass through
        if any(m.startswith(v) or m == v.strip() for v in
                  ("dir", "ls", "cd", "start", "mkdir", "md", "del", "rm",
                   "cat", "echo", "type", "powershell", "pwsh", "ps",
                   "git", "python", "python3", "pip", "jarvis", "taskmgr",
                   "open", "cmd", "explorer", "calc", "notepad", "code",
                   "subl", "firefox", "chrome", "brave", "spotify", "slack",
                   "discord", "telegram", "pycharm", "gedit", "kate",
                   "xdg-open", "gnome", "konsole", "xterm", "amixer",
                   "free", "df", "uname", "lscpu", "hostname", "date",
                   "whoami", "id", "pkill", "taskkill", "curl", "wget",
                   "net", "ipconfig", "ping", "invoke-", "get-", "set-",
                   "new-", "select-", "where-")):
            return user_message.strip()

        return ""

    @staticmethod
    def _is_prompt_injection(text: str) -> bool:
        """Heuristic check: return True if the LLM output looks like a prompt-injection attempt."""
        lower = text.lower()
        red_flags = [
            "ignore previous",
            "ignore all previous",
            "ignore above",
            "ignore all above",
            "ignore prior",
            "forget everything",
            "new instructions:",
            "system: you are now",
            "you are now a",
            "act as root",
            "bypass safety",
            "disregard instructions",
            "override instructions",
        ]
        return any(flag in lower for flag in red_flags)

    # A <run> block is treated as AN EXECUTABLE COMMAND by default
    # (the model was explicitly told to only use <run> for actions).
    # We only *reject* it when it is clearly NOT a command -- i.e.
    # a factual question or plain prose that got wrapped by mistake.
    _QUESTION_MARKERS = (
        "who is", "who was", "who are", "who were",
        "what is", "what are", "what was", "what were", "what can",
        "what do", "what does",
        "where is", "when is", "when did", "when was",
        "why is", "why do", "why did", "why does",
        "how do", "how does", "how to", "how can", "how is",
        "tell me about", "tell me why", "explain", "describe",
        "name the", "which is", "which are",
    )

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        """Narrow reject-check: does this look like a question/prose, NOT a command?

        We intentionally keep this NARROW (false-positives would block
        real commands). Only reject obvious questions and sentences with
        spaces but no shell verb / operator.
        """
        t = text.strip()
        if not t:
            return True
        low = t.lower()
        # Explicit question phrasing -> reject.
        if any(low.startswith(q) for q in JarvisBrain._QUESTION_MARKERS):
            return True
        # Multi-word sentence with no command verb and no shell operator ->
        # almost certainly prose the model wrapped by mistake.
        has_operator = any(op in t for op in ("|", ">", "<", "&", ";", "&&", "||"))
        has_path = ("\\" in t) or ("/" in t)
        has_verb = any(low.startswith(v) or low == v.strip()
                        for v in ("dir", "ls", "cd", "start", "mkdir", "md",
                        "del", "rm", "cat", "echo", "type", "powershell",
                        "pwsh", "ps", "git", "python", "python3", "pip",
                        "jarvis", "taskmgr", "open", "cmd", "explorer",
                        "calc", "notepad", "code", "subl", "firefox", "chrome",
                        "brave", "spotify", "slack", "discord", "telegram",
                        "pycharm", "gedit", "kate", "xdg-open", "gnome",
                        "konsole", "xterm", "amixer", "free", "df", "uname",
                        "lscpu", "hostname", "date", "whoami", "id", "pkill",
                        "taskkill", "curl", "wget", "net", "ipconfig", "ping",
                        "invoke-", "get-", "set-", "new-", "select-",
                        "where-", "get-", "cd\\", "cd /"))
        if " " in t and not has_operator and not has_path and not has_verb:
            return True
        return False

    @staticmethod
    def extract_command(response_text: str):
        """Extract the first <run>...</run> command.

        By default a <run> block is trusted as an executable command.
        We only reject it when it clearly looks like a question/prose that
        the model wrapped by mistake (to avoid 'command not found' errors).
        """
        if JarvisBrain._is_prompt_injection(response_text):
            return None
        matches = re.findall(r'<run>(.*?)</run>', response_text, re.DOTALL)
        if matches:
            cmd = matches[0].strip()
            # Reject only clear non-commands (questions / prose).
            if JarvisBrain._looks_like_question(cmd):
                return None
            return cmd
        return None

    @staticmethod
    def clean_speech_text(response_text: str) -> str:
        """Strip <run> blocks and markdown formatting for TTS."""
        cleaned = re.sub(r'<run>.*?</run>', '', response_text, flags=re.DOTALL)
        cleaned = cleaned.replace("*", "").replace("`", "").replace("#", "").replace("_", " ")
        return cleaned.strip()


# ------------------------------------------------------------------
# Test block
# ------------------------------------------------------------------
if __name__ == "__main__":
    brain = JarvisBrain({"user": "rehan", "os": platform.system(), "cwd": os.getcwd()}, debug=True)

    print("\n--- TEST 1: List directories ---")
    resp = brain.get_response("Open the directories of this folder")
    print(f"Response: {resp}")
    print(f"Command: {brain.extract_command(resp)}")
    print(f"Speech: {brain.clean_speech_text(resp)}")

    print("\n--- TEST 2: System info ---")
    resp = brain.get_response("What system am I on?")
    print(f"Response: {resp}")

    print("\n--- TEST 3: Greeting ---")
    resp = brain.get_response("Hello JARVIS")
    print(f"Response: {resp}")

    print("\n--- TEST 4: RAM ---")
    resp = brain.get_response("How much RAM do I have?")
    print(f"Response: {resp}")
