@echo off
call "%~dp0venv\Scripts\activate.bat"
python -m jarvis.main %*
