@echo off
REM VeloPOS Admin helper - double-click. DEVELOPER ONLY, never give this folder to customers.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw velopos_admin.py & exit /b 0)
where python >nul 2>nul && (python velopos_admin.py & exit /b 0)
echo Python was not found. Install Python 3 from python.org (tick "Add to PATH"), then try again.
pause
