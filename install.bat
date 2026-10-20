@echo off
rem AutoMailCAT - one-time setup on Windows: checks Python and installs the packages for the current user.
rem   install.bat              install
rem   install.bat /autostart   install and start AutoMailCAT with Windows
setlocal
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (
  echo Python 3.10 sau mai nou este necesar / Python 3.10 or newer is required: https://www.python.org/downloads/
  echo Bifeaza "Add python.exe to PATH" la instalare / Tick "Add python.exe to PATH" when installing.
  pause & exit /b 1
)
echo Instalez componentele (Outlook, iconita din tray) pentru utilizatorul curent...
echo Installing the packages (Outlook, tray icon) for the current user...
%PY% -m pip install --user --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo Instalarea nu a reusit. Verifica conexiunea la internet sau cere ajutor IT.
  echo Installation failed. Check the internet connection or ask IT.
  pause & exit /b 1
)
if /i "%~1"=="/autostart" (
  > "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AutoMailCAT.cmd" echo @echo off
  >> "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AutoMailCAT.cmd" echo cd /d "%~dp0"
  >> "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AutoMailCAT.cmd" echo call start.bat --tray
  echo AutoMailCAT va porni odata cu Windows / AutoMailCAT will start with Windows.
)
echo.
echo Gata. Porneste AutoMailCAT cu start.bat (sau start-demo.bat pentru o proba fara Outlook).
echo Done. Start AutoMailCAT with start.bat (or start-demo.bat to try it without Outlook).
pause
