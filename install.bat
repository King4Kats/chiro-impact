@echo off
rem ==========================================================================
rem  Installation de Chiro Impact sur un PC Windows (a lancer une seule fois)
rem  Prerequis : Python 3.11 ou plus, et Node.js 20 ou plus (voir README.md)
rem ==========================================================================
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo [1/4] Verification de Python et Node...
where python >nul 2>nul || (echo   Python est introuvable : installe-le depuis https://www.python.org en cochant "Add python.exe to PATH". & goto :erreur)
where npm >nul 2>nul || (echo   Node.js est introuvable : installe la version LTS depuis https://nodejs.org & goto :erreur)

echo.
echo [2/4] Creation de l'environnement Python (backend\.venv)...
if not exist backend\.venv ( python -m venv backend\.venv || goto :erreur )

echo.
echo [3/4] Installation des modules Python (BatDetect2, PyTorch...) : plusieurs minutes...
backend\.venv\Scripts\python -m pip install --upgrade pip || goto :erreur
rem PyTorch version processeur : bien plus leger que la version carte graphique
backend\.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu || goto :erreur
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt || goto :erreur

echo.
echo [4/4] Construction de l'interface web...
pushd frontend
call npm ci --no-audit --no-fund || (popd & goto :erreur)
call npm run build || (popd & goto :erreur)
popd

echo.
echo Installation terminee. Lance start.bat pour demarrer Chiro Impact.
pause
exit /b 0

:erreur
echo.
echo *** L'installation a echoue. Lis le message ci-dessus, ou envoie-le a la personne qui maintient l'outil. ***
pause
exit /b 1
