@echo off
REM =================================================================
REM =           Potree Point Cloud Viewer Launcher                  =
REM =      (for environments that require activation scripts)       =
REM =================================================================

ECHO.
ECHO This script will activate the Pydro environment, start a local
ECHO web server, and open the Potree viewer in your browser.
ECHO.
ECHO This command window must remain open while you are viewing the data.
ECHO To stop the server, simply close this window.
ECHO.

REM --- Activate the Pydro Python Environment ---
ECHO Activating Pydro environment...
call C:\Pydro24\Scripts\activate.bat Pydro3_11

REM --- Change directory to the location of this .bat file ---
REM This ensures the web server serves the correct folder.
cd /d "%~dp0"

REM --- Start a local web server and open the browser ---
ECHO Starting local web server...
start http://localhost:8000/shipwreck_small_23_custom.html
python -m http.server

ECHO.
ECHO Server has been stopped.
pause
