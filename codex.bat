@echo off
cd /d F:\Code\moon-bridge
title Codex Launcher

if "%1"=="" (
    echo.
    echo  Usage: codex.bat ^<model^> [project-dir]
    echo.
    echo  Models:
    echo    1  - DeepSeek V4 Flash     (moonbridge)
    echo    2  - Gemini 2.5 Flash      (gemini-flash)
    echo    3  - Gemini 3.5 Flash      (gemini-35flash)
    echo    4  - Gemini 3.1 Flash Lite (gemini-31flash-lite)
    echo.
    set /p "M=Select model [1-4]: "
) else (
    set "M=%1"
)

if "%M%"=="1" set "ROUTE=moonbridge"
if "%M%"=="2" set "ROUTE=gemini-flash"
if "%M%"=="3" set "ROUTE=gemini-35flash"
if "%M%"=="4" set "ROUTE=gemini-31flash-lite"
if "%ROUTE%"=="" set "ROUTE=moonbridge"

REM Update Codex config to use the selected model
powershell -ExecutionPolicy Bypass -Command "& '.\init-codex.ps1' -Model '%ROUTE%'" 2>nul

REM Determine project directory
if "%2"=="" ( set "PROJECT=%cd%" ) else ( set "PROJECT=%2" )

set CODEX_HOME=%USERPROFILE%\.codex
set NO_PROXY=127.0.0.1,localhost
echo.
echo  Starting Codex with model: %ROUTE%
echo  Project: %PROJECT%
echo.
call "%USERPROFILE%\AppData\Roaming\npm\codex.cmd" --cd "%PROJECT%"
