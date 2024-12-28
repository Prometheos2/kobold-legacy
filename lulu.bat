@echo off
:start
cls
echo Booting up
uv run kobold.py --no-dev
goto :start
