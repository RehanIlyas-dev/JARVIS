$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$ScriptDir\venv\Scripts\python.exe" -m jarvis.web_app $args
