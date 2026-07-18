import asyncio
import json
import os
import time
import threading
from typing import Any, Dict, Generator, Optional

import psutil
from flask import Flask, request, Response, render_template, jsonify

from .config import MAX_AGENTIC_ITERATIONS, FLASK_HOST, FLASK_PORT
from .system_agent import SystemAgent
from .brain import JarvisBrain
from .agentic_loop import generate_agentic_loop

# Hot-path local references (avoids global lookups in tight loops)
_json_dumps = json.dumps

app: Flask = Flask(__name__)

# Lazy initialization placeholders so we can import without initializing hardware / brain immediately
system_agent: Optional[SystemAgent] = None
sys_info: Optional[Dict[str, Any]] = None
brain: Optional[JarvisBrain] = None
_init_lock: threading.Lock = threading.Lock()


def init_app() -> None:
    global system_agent, sys_info, brain
    if system_agent is not None:
        return
    with _init_lock:
        # Double-check after acquiring lock
        if system_agent is None:
            system_agent = SystemAgent()
            sys_info = system_agent.get_system_info()
            brain = JarvisBrain(system_info=sys_info, system_agent=system_agent)

def _get_cpu_percent() -> float:
    try:
        return psutil.cpu_percent(interval=0.1)
    except Exception:
        return 0.0


def _get_memory_info() -> Dict[str, float]:
    try:
        mem = psutil.virtual_memory()
        return {
            "total_mb": round(mem.total / (1024 * 1024)),
            "used_mb": round(mem.used / (1024 * 1024)),
            "percent": round(mem.percent, 1),
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "percent": 0}


def _get_disk_info() -> Dict[str, float]:
    try:
        usage = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
        return {
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "used_gb": round(usage.used / (1024 ** 3), 1),
            "percent": round(usage.percent, 1),
        }
    except Exception:
        return {"total_gb": 0, "used_gb": 0, "percent": 0}


def _get_uptime() -> str:
    try:
        secs: float = time.time() - psutil.boot_time()
        days: int = int(secs // 86400)
        hours: int = int((secs % 86400) // 3600)
        mins: int = int((secs % 3600) // 60)
        if days:
            return f"{days}d {hours}h {mins}m"
        return f"{hours}h {mins}m"
    except Exception:
        return "-"


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/status")
def api_status() -> Response:
    return jsonify({
        "provider": brain.provider,
        "model": brain.model_name,
        "os": sys_info.get("os"),
        "user": sys_info.get("user"),
        "cwd": system_agent.get_cwd(),
    })


@app.route("/api/metrics")
def api_metrics() -> Response:
    return jsonify({
        "cpu": _get_cpu_percent(),
        "memory": _get_memory_info(),
        "disk": _get_disk_info(),
        "uptime": _get_uptime(),
        "cwd": system_agent.get_cwd(),
    })


@app.route("/api/chat", methods=["POST"])
def api_chat() -> Response:
    data = request.get_json(silent=True)
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "Message is required"}), 400

    user_message: str = data["message"].strip()

    def event_stream() -> Generator[str, None, None]:
        try:
            for event in generate_agentic_loop(brain, system_agent, user_message):
                if event["type"] == "status":
                    yield _sse("status", {
                        "state": event["state"],
                        "label": event["label"],
                    })
                elif event["type"] == "assistant_response":
                    yield _sse("assistant_response", {
                        "content": event["content"],
                        "iteration": event["iteration"],
                    })
                elif event["type"] == "command":
                    yield _sse("command", {
                        "content": event["content"],
                        "iteration": event["iteration"],
                    })
                    yield _sse("status", {
                        "state": "executing",
                        "label": f"EXECUTING: {event['content']}",
                    })
                elif event["type"] == "command_output":
                    yield _sse("command_output", {
                        "status": event["status"],
                        "exit_code": event["exit_code"],
                        "stdout": event["stdout"][:2000],
                        "stderr": event["stderr"][:2000],
                        "iteration": event["iteration"],
                    })
                    yield _sse("status", {
                        "state": "thinking",
                        "label": "PROCESSING DATA...",
                    })
                elif event["type"] == "done":
                    yield _sse("done", {})
                elif event["type"] == "error":
                    yield _sse("error", {"content": event["content"]})

        except Exception as e:
            yield _sse("error", {"content": str(e)})

    return Response(event_stream(), mimetype="text/event-stream")


def _sse(event_type: str, data: Dict[str, Any]) -> str:
    # Use local _json_dumps to avoid repeated module attribute lookup
    return f"event: {event_type}\ndata: {_json_dumps(data)}\n\n"


@app.route("/api/tts", methods=["POST"])
def api_tts() -> Response:
    data = request.get_json(silent=True)
    if not data or not data.get("text", "").strip():
        return Response(b"", status=400)
    text: str = data["text"].strip()

    async def _generate() -> bytes:
        import edge_tts
        communicate = edge_tts.Communicate(
            text,
            voice="en-GB-RyanNeural",
            rate="+5%",
            pitch="-5Hz",
        )
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    audio_data: bytes = asyncio.run(_generate())
    return Response(audio_data, mimetype="audio/mpeg")


@app.before_request
def before_request() -> None:
    init_app()


def main() -> None:
    init_app()
    _get_cpu_percent()  # prime the cpu counter
    print(f"\n  +--------------------------------------+")
    print(f"  |     J.A.R.V.I.S.  WEB INTERFACE      |")
    print(f"  +--------------------------------------+")
    print(f"  |  Provider : {brain.provider:<24s}|")
    print(f"  |  Model    : {(brain.model_name or 'N/A'):<24s}|")
    print(f"  |  URL      : http://127.0.0.1:5000    |")
    print(f"  +--------------------------------------+\n")
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
