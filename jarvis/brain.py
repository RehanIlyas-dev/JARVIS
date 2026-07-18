import os
import platform
import re
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from .config import CONTEXT_WINDOW, HISTORY_LIMIT
from .fallback_matcher import FallbackMatcher

# Pre-compiled regexes for hot-path text processing
_RE_RUN_BLOCK = re.compile(r'<run>(.*?)</run>', re.DOTALL)
_RE_STRIP_RUN = re.compile(r'<run>.*?</run>', re.DOTALL)

_IS_WINDOWS: bool = (platform.system() == "Windows")
_IS_MAC: bool = (platform.system() == "Darwin")


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
    HISTORY_LIMIT: int = HISTORY_LIMIT
    # How many history messages to send to the API each turn
    CONTEXT_WINDOW: int = CONTEXT_WINDOW

    def __init__(
        self,
        system_info: Optional[Dict[str, Any]] = None,
        system_agent: Any = None,
        debug: bool = False,
    ) -> None:
        self.system_info: Dict[str, Any] = system_info or {}
        self.system_agent: Any = system_agent  # reference so we can read live cwd
        self.debug: bool = debug
        self.provider: str = "gemini"
        self.client: Any = None
        self.model_name: Optional[str] = None
        self.conversation_history: List[Dict[str, str]] = []
        self._history_lock: threading.Lock = threading.Lock()
        # Platform flags as instance attributes for testability / overriding
        self._IS_WINDOWS: bool = _IS_WINDOWS
        self._IS_MAC: bool = _IS_MAC

        self._setup_client()
        self.system_prompt: str = self._build_system_prompt()

        # Offline fallback command matcher
        self.fallback_matcher: FallbackMatcher = FallbackMatcher(
            add_to_history=self._add_to_history,
            system_agent=self.system_agent,
            is_windows=self._IS_WINDOWS,
            is_mac=self._IS_MAC,
        )

    # ------------------------------------------------------------------
    # Client setup
    # ------------------------------------------------------------------

    def _setup_client(self) -> None:
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

    def _get_directory_listing(self, path: Optional[str] = None) -> str:
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

    def _live_cwd(self) -> str:
        """Get the live cwd from system_agent if available, else fallback."""
        if self.system_agent:
            return self.system_agent.get_cwd()
        return self.system_info.get("cwd", os.path.expanduser("~"))

    def _build_system_prompt(self) -> str:
        user_name = self.system_info.get("user", "Sir")
        os_name   = self.system_info.get("os", "Linux")
        cwd       = self._live_cwd()
        cwd_listing = self._get_directory_listing(cwd)
        # Use instance platform flags so tests can override them
        _IS_WINDOWS = self._IS_WINDOWS
        _IS_MAC = self._IS_MAC

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

    def _refresh_context(self) -> None:
        """Rebuild the system prompt with the current live cwd."""
        self.system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    # Main response method
    # ------------------------------------------------------------------

    def get_response(self, user_message: str) -> str:
        # Sync platform flags to the fallback matcher (tests toggle them at runtime)
        self.fallback_matcher._IS_WINDOWS = self._IS_WINDOWS
        self.fallback_matcher._IS_MAC = self._IS_MAC

        if self.provider == "fallback":
            return self.fallback_matcher.get_response(user_message)

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
                return self.fallback_matcher.get_response(user_message)

            return (
                f"Apologies Sir, I encountered an error communicating with my neural network. "
                f"The error is: {error_msg}. Please check your API key and internet connection."
            )

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _add_to_history(self, role: str, content: str) -> None:
        """Append a message and trim history to HISTORY_LIMIT to save RAM."""
        with self._history_lock:
            self.conversation_history.append({"role": role, "content": content})
            if len(self.conversation_history) > self.HISTORY_LIMIT:
                # Drop oldest messages in pairs (user+assistant) to maintain coherence
                self.conversation_history = self.conversation_history[-self.HISTORY_LIMIT:]

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
                        "where-", "cd\\", "cd /"))
        if " " in t and not has_operator and not has_path and not has_verb:
            return True
        return False

    @staticmethod
    def extract_command(response_text: str) -> Optional[str]:
        """Extract the first <run>...</run> command.

        By default a <run> block is trusted as an executable command.
        We only reject it when it clearly looks like a question/prose that
        the model wrapped by mistake (to avoid 'command not found' errors).
        """
        if JarvisBrain._is_prompt_injection(response_text):
            return None
        matches = _RE_RUN_BLOCK.findall(response_text)
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
        cleaned = _RE_STRIP_RUN.sub('', response_text)
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
