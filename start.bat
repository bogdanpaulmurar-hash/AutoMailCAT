@echo off
rem Start AutoMailCAT without a console window; it appears as an icon next to the clock.
rem Extra options are passed on, e.g. start.bat --tray or start.bat --action sweep
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw -3 automailcat.py %*) || (start "" pythonw automailcat.py %*)
