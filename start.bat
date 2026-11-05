@echo off
rem ==========================================================================
rem  Demarre Chiro Impact puis ouvre http://localhost:8000 dans le navigateur.
rem  Pour arreter : fermer cette fenetre (ou Ctrl+C).
rem ==========================================================================
rem
rem  Script batch Windows a double-cliquer chaque fois qu'on veut utiliser l'appli.
rem  Il lance le serveur Python, qui sert a la fois l'API et l'interface web
rem  construite par install.bat. Travaille avec : install.bat, backend/app/main.py.
rem
rem  Lignes suivantes : console en UTF-8, puis on se place dans le dossier du projet.
chcp 65001 >nul
cd /d "%~dp0"

rem  Garde-fou : si le Python du venv n'existe pas, install.bat n'a jamais ete lance.
rem  On le dit, on attend une touche, et on quitte avec le code 1, qui signifie echec.
if not exist backend\.venv\Scripts\python.exe (
  echo Chiro Impact n'est pas installe : lance d'abord install.bat
  pause
  exit /b 1
)

rem Ouvre le navigateur quelques secondes apres le demarrage du serveur
rem  start ouvre une deuxieme fenetre de commande qui attend 6 secondes puis ouvre
rem  l'adresse dans le navigateur par defaut. Pendant ce temps, cette fenetre-ci
rem  continue et demarre le serveur : les deux se font en parallele.
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8000"

echo Chiro Impact demarre sur http://localhost:8000  (fermer cette fenetre pour l'arreter)
rem  Demarrage du serveur web uvicorn, avec le Python du venv.
rem  app.main:app designe l'objet app du fichier backend/app/main.py.
rem  --host 127.0.0.1 : le serveur n'est joignable que depuis ce PC, pas depuis le reseau.
rem  Cette commande ne rend la main que quand le serveur s'arrete.
backend\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
pause
