@echo off
REM Stop any python process running src.main or src.web from this repo.
setlocal enabledelayedexpansion

set KILLED=0

REM Use wmic to find python processes whose command line mentions src.main or src.web.
for /f "skip=1 tokens=1" %%P in ('wmic process where "Name='python.exe' and (CommandLine like '%%src.main%%' or CommandLine like '%%src.web%%')" get ProcessId 2^>nul') do (
    if not "%%P"=="" (
        taskkill /PID %%P /F >nul 2>&1
        if !errorlevel! EQU 0 (
            echo Killed PID %%P
            set /a KILLED+=1
        )
    )
)

if !KILLED! EQU 0 (
    echo No running bot processes found.
) else (
    echo Stopped !KILLED! process(es).
)

pause
endlocal
