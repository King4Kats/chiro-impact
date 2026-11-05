@echo off
rem ==========================================================================
rem  Installation de Chiro Impact sur un PC Windows (a lancer une seule fois)
rem  Prerequis : Python 3.11 ou plus, et Node.js 20 ou plus (voir README.md)
rem ==========================================================================
rem
rem  Ce fichier est un script batch Windows : une liste de commandes cmd.exe
rem  executees de haut en bas quand on double-clique dessus.
rem  Il prepare tout ce dont start.bat a besoin : un environnement Python
rem  avec le serveur, et l'interface web deja construite dans frontend/dist.
rem  Travaille avec : start.bat, backend/requirements.txt, frontend/package.json.
rem
rem  Tout en haut, echo off cache les commandes pour n'afficher que les messages.
rem  chcp 65001 passe la console en UTF-8, pour les caracteres accentues.
rem  cd /d suivi du dossier du script : on se place dans le dossier du projet,
rem  quel que soit l'endroit d'ou le script a ete lance.
chcp 65001 >nul
cd /d "%~dp0"

echo.
rem  Etape 1 : where cherche un programme dans le PATH, la liste des dossiers
rem  ou Windows cherche les commandes. Le double trait vertical veut dire :
rem  si la commande de gauche echoue, executer celle de droite.
rem  Ici : afficher comment installer l'outil manquant, puis sauter a :erreur.
echo [1/4] Verification de Python et Node...
where python >nul 2>nul || (echo   Python est introuvable : installe-le depuis https://www.python.org en cochant "Add python.exe to PATH". & goto :erreur)
where npm >nul 2>nul || (echo   Node.js est introuvable : installe la version LTS depuis https://nodejs.org & goto :erreur)

echo.
rem  Etape 2 : un environnement virtuel Python, ou venv, est un dossier qui contient
rem  sa propre copie de Python et ses propres modules. Les modules du projet
rem  y sont installes sans toucher au Python du reste de l'ordinateur.
rem  On ne le cree que s'il n'existe pas deja, pour pouvoir relancer l'installation.
echo [2/4] Creation de l'environnement Python (backend\.venv)...
if not exist backend\.venv ( python -m venv backend\.venv || goto :erreur )

echo.
rem  Etape 3 : on appelle le Python DU venv, donc pip installe dans le venv.
rem  D'abord pip lui-meme a jour, puis PyTorch, puis la liste de requirements.txt.
echo [3/4] Installation des modules Python (BatDetect2, PyTorch...) : plusieurs minutes...
backend\.venv\Scripts\python -m pip install --upgrade pip || goto :erreur
rem PyTorch version processeur : bien plus leger que la version carte graphique
backend\.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cpu || goto :erreur
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt || goto :erreur

echo.
rem  Etape 4 : pushd entre dans frontend et popd revient au dossier de depart.
rem  npm ci installe exactement les versions de package-lock.json.
rem  npm run build lance Vite, qui produit frontend/dist, servi ensuite par le serveur Python.
rem  call est obligatoire devant npm : npm est lui-meme un script batch, et sans call
rem  le script courant s'arreterait apres lui.
rem  En cas d'echec, on fait popd avant de sauter a :erreur.
echo [4/4] Construction de l'interface web...
pushd frontend
call npm ci --no-audit --no-fund || (popd & goto :erreur)
call npm run build || (popd & goto :erreur)
popd

echo.
rem  Tout s'est bien passe : message final, pause pour laisser le temps de lire,
rem  puis exit /b 0 quitte le script avec le code 0, qui signifie succes.
echo Installation terminee. Lance start.bat pour demarrer Chiro Impact.
pause
exit /b 0

rem  Etiquette :erreur, cible de tous les goto :erreur ci-dessus.
rem  On garde la fenetre ouverte pour lire le message, et on sort avec le code 1, qui signifie echec.
:erreur
echo.
echo *** L'installation a echoue. Lis le message ci-dessus, ou envoie-le a la personne qui maintient l'outil. ***
pause
exit /b 1
