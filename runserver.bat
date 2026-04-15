@echo off
setlocal

cd /d "%~dp0"

if exist ".health\Scripts\python.exe" (
    set "PYTHON_EXE=.health\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_EXE=py"
    ) else (
        set "PYTHON_EXE=python"
    )
)

echo Starting Django development server on http://127.0.0.1:8000/
"%PYTHON_EXE%" manage.py runserver_nodb 127.0.0.1:8000 --skip-checks

if errorlevel 1 (
    echo.
    echo Server failed to start.
    echo Check that dependencies are installed and your .env values are valid.
    echo If pages need the database, verify your Supabase/Postgres connection.
    pause
)

endlocal
