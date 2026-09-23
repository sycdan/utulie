@echo off
rem Runs the print relay in a visible console, with output -- for starting it
rem by hand, and for finding out why it is not running. The scheduled task
rem does not use this: it runs pythonw directly so there is no window, which
rem also means no output, which is what this is for.
rem
rem Pass a websocket URL to point it somewhere other than production.
cd /d "%~dp0"
set "URL=%~1"
if "%URL%"=="" set "URL=wss://utulie.wildharvesthomestead.com/labels/ws"
python -u relay_client.py "%URL%"
pause
