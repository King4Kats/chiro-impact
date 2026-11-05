@echo off
rem ==========================================================================
rem  Demarre Chiro Impact puis ouvre http://localhost:8000 dans le navigateur.
rem  Pour arreter : fermer cette fenetre (ou Ctrl+C).
rem ==========================================================================
chcp 65001 >nul
cd /d "%~dp0"

if not exist backend\.venv\Scripts\python.exe (
  echo Chiro Impact n'est pas installe : lance d'abord install.bat
  pause
  exit /b 1
)

rem Ouvre le navigateur quelques secondes apres le demarrage du serveur
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8000"

echo Chiro Impact demarre sur http://localhost:8000  (fermer cette fenetre pour l'arreter)
backend\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
pause
