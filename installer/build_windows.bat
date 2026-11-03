@echo off
REM ============================================================================
REM  VeloPOS - ONE-CLICK BUILD for customers.   Double-click this file on YOUR Windows PC.
REM  It checks everything, asks for what is missing, and makes:  installer\Output\VeloPOS_Setup.exe
REM ============================================================================
setlocal EnableDelayedExpansion
set SRC=%~dp0..
set BUILD=%TEMP%\velopos_build
title VeloPOS - build for customers

echo.
echo [1/5] Checking Python ...
python --version >nul 2>nul
if errorlevel 1 (
  echo   Python was NOT found. Install Python 3.11 or newer from https://www.python.org/downloads/
  echo   IMPORTANT: tick "Add python.exe to PATH" on the first screen, then run this file again.
  goto fail
)

echo [2/5] Installing / updating the build tools (first time takes a few minutes) ...
python -m pip install --quiet --upgrade nuitka -r "%SRC%\requirements.txt"
if errorlevel 1 ( echo   pip failed - check the internet connection and try again. & goto fail )

echo [3/5] Checking your licence public key ...
if not exist "%SRC%\velopos\_pubkey.py" (
  echo.
  echo   velopos\_pubkey.py is missing. It is NOT in the zip on purpose - it is YOUR key file from the first time you ran keygen.
  echo   Open File Explorer, find your OLD VeloPOS folder, and DRAG it into this window, then press Enter.
  set "OLD="
  set /p OLD=  Old folder: 
  set "OLD=!OLD:"=!"
  if not exist "!OLD!\velopos\_pubkey.py" (
    echo   Could not find _pubkey.py inside that folder ^(it should be in its velopos subfolder^). Nothing was copied.
    goto fail
  )
  copy /y "!OLD!\velopos\_pubkey.py" "%SRC%\velopos\_pubkey.py" >nul
  echo   Copied. OK.
)

echo [4/5] Building the program (this takes 10-20 minutes, please wait) ...
if exist "%BUILD%" rmdir /s /q "%BUILD%"
mkdir "%BUILD%"
REM Copy ONLY what customers may receive: no tools\, no tests\, no private key, no cloud\.
robocopy "%SRC%" "%BUILD%" /E /XD tools tests installer cloud .git __pycache__ /XF *.pem *.csv admin_key.txt >nul
if exist "%BUILD%\tools" ( echo ERROR: tools folder leaked into build & goto fail )
dir /s /b "%BUILD%\*.pem" 2>nul | findstr . >nul && ( echo ERROR: a .pem file is in the build & goto fail )
if not exist "%BUILD%\velopos\_pubkey.py" ( echo ERROR: velopos\_pubkey.py missing & goto fail )
pushd "%BUILD%"
set EXTRA=
if exist "%BUILD%\qr_codes" set EXTRA=%EXTRA% --include-data-dir=qr_codes=qr_codes
if exist "%BUILD%\branding" set EXTRA=%EXTRA% --include-data-dir=branding=branding
if exist "%BUILD%\branding\app_icon.ico" set EXTRA=%EXTRA% --windows-icon-from-ico=branding\app_icon.ico
python -m nuitka --standalone --assume-yes-for-downloads --windows-disable-console --enable-plugin=tk-inter --include-package=velopos %EXTRA% --output-filename=VeloPOS.exe --company-name="VeloPOS" --product-name="VeloPOS" --file-version=7.2.0.0 --product-version=7.2.0.0 run.py
if errorlevel 1 ( echo Nuitka build failed. & popd & goto fail )
popd

echo [5/5] Making the installer ...
set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo   Inno Setup 6 was NOT found. Install it free from https://jrsoftware.org/isdl.php then run this file again.
  echo   ^(The program itself is already built in: %BUILD%\run.dist^)
  goto fail
)
"%ISCC%" /DBuildDir="%BUILD%\run.dist" /DOutDir="%SRC%\installer\Output" "%SRC%\installer\velopos.iss"
if errorlevel 1 ( echo Installer step failed. & goto fail )

echo.
echo ============================================================================
echo  DONE.  Your installer is here:   %SRC%\installer\Output\VeloPOS_Setup.exe
echo  Give THAT file to customers.  (Sign it if you have a certificate - see README_INSTALLER.txt)
echo ============================================================================
explorer "%SRC%\installer\Output"
pause
exit /b 0

:fail
echo.
echo  *** The build stopped. Read the message above, fix it, and run this file again. ***
pause
exit /b 1
