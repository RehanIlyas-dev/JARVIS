import json
import os
import sys
import time

import psutil
from flask import Flask, request, Response, render_template, jsonify

from .system_agent import SystemAgent
from .brain import JarvisBrain

MAX_AGENTIC_ITERATIONS = 8

app = Flask(__name__)

# Lazy initialization placeholders so we can import without initializing hardware / brain immediately
system_agent = None
sys_info = None
brain = None


def init_app():
    global system_agent, sys_info, brain
    if system_agent is None:
        system_agent = SystemAgent()
        sys_info = system_agent.get_system_info()
        brain = JarvisBrain(system_info=sys_info, system_agent=system_agent)

def _get_cpu_percent():
    try:
        return psutil.cpu_percent(interval=0.1)
    except Exception:
        return 0.0


def _get_memory_info():
    try:
        mem = psutil.virtual_memory()
        return {
            "total_mb": round(mem.total / (1024 * 1024)),
            "used_mb": round(mem.used / (1024 * 1024)),
            "percent": round(mem.percent, 1),
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "percent": 0}


def _get_disk_info():
    try:
        usage = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
        return {
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "used_gb": round(usage.used / (1024 ** 3), 1),
            "percent": round(usage.percent, 1),
        }
    except Exception:
        return {"total_gb": 0, "used_gb": 0, "percent": 0}


def _get_uptime():
    try:
        secs = time.time() - psutil.boot_time()
        days = int(secs // 86400)
        hours = int((secs % 86400) // 3600)
        mins = int((secs % 3600) // 60)
        if days:
            return f"{days}d {hours}h {mins}m"
        return f"{hours}h {mins}m"
    except Exception:
        return "-"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "provider": brain.provider,
        "model": brain.model_name,
        "os": sys_info.get("os"),
        "user": sys_info.get("user"),
        "cwd": system_agent.get_cwd(),
    })


@app.route("/api/metrics")
def api_metrics():
    return jsonify({
        "cpu": _get_cpu_percent(),
        "memory": _get_memory_info(),
        "disk": _get_disk_info(),
        "uptime": _get_uptime(),
        "cwd": system_agent.get_cwd(),
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True)
    if not data or not data.get("message", "").strip():
        return jsonify({"error": "Message is required"}), 400

    user_message = data["message"].strip()

    def event_stream():
        try:
            yield _sse("status", {"state": "thinking", "label": "ANALYZING QUERY..."})
            current_message = user_message

            for iteration in range(1, MAX_AGENTIC_ITERATIONS + 1):
                response = brain.get_response(current_message)
                cmd_to_run = brain.extract_command(response)
                speech_text = brain.clean_speech_text(response)

                if speech_text:
                    yield _sse("assistant_response", {
                        "content": speech_text,
                        "iteration": iteration,
                    })

                if cmd_to_run:
                    yield _sse("command", {
                        "content": cmd_to_run,
                        "iteration": iteration,
                    })
                    yield _sse("status", {
                        "state": "executing",
                        "label": f"EXECUTING: {cmd_to_run}",
                    })

                    exec_result = system_agent.execute_command(cmd_to_run)

                    yield _sse("command_output", {
                        "status": exec_result["status"],
                        "exit_code": exec_result["exit_code"],
                        "stdout": exec_result["stdout"][:2000],
                        "stderr": exec_result["stderr"][:2000],
                        "iteration": iteration,
                    })

                    result_formatted = (
                        f"[System Execution Result: status={exec_result['status']}, "
                        f"exit_code={exec_result['exit_code']}, "
                        f"stdout='{exec_result['stdout']}', "
                        f"stderr='{exec_result['stderr']}']\n"
                        f"Current working directory is now: {system_agent.get_cwd()}"
                    )
                    current_message = result_formatted
                    yield _sse("status", {"state": "thinking", "label": "PROCESSING DATA..."})
                else:
                    break

            yield _sse("done", {})

        except Exception as e:
            yield _sse("error", {"content": str(e)})

    return Response(event_stream(), mimetype="text/event-stream")


def _sse(event_type, data):
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@app.route("/api/tts", methods=["POST"])
def api_tts():
    data = request.get_json(silent=True)
    if not data or not data.get("text", "").strip():
        return Response(b"", status=400)
    text = data["text"].strip()

    async def _generate():
        import edge_tts
        communicate = edge_tts.Communicate(
            text,
            voice="en-GB-RyanNeural",
            rate="+5%",
            pitch="-5Hz",
        )
        chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    import asyncio
    audio_data = asyncio.run(_generate())
    return Response(audio_data, mimetype="audio/mpeg")


@app.before_request
def before_request():
    init_app()


def main():
    init_app()
    _get_cpu_percent()  # prime the cpu counter
    print(f"\n  +--------------------------------------+")
    print(f"  |     J.A.R.V.I.S.  WEB INTERFACE      |")
    print(f"  +--------------------------------------+")
    print(f"  |  Provider : {brain.provider:<24s}|")
    print(f"  |  Model    : {(brain.model_name or 'N/A'):<24s}|")
    print(f"  |  URL      : http://127.0.0.1:5000    |")
    print(f"  +--------------------------------------+\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
