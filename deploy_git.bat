@echo off
setlocal enableextensions enabledelayedexpansion

REM Aller dans le dossier du script
cd /d "%~dp0"

REM Détecter la branche courante
for /f %%b in ('git rev-parse --abbrev-ref HEAD') do set BRANCH=%%b
echo Branche courante : %BRANCH%
echo.

REM Message de commit (prendre les arguments du .bat, sinon message auto)
set MSG=%*
if "%MSG%"=="" set MSG=Maj auto %DATE% %TIME%

REM Ajouter tous les fichiers modifiés
git add -A

REM Vérifier s'il y a quelque chose à commiter
git diff --cached --quiet && (
  echo Aucun changement à valider.
) || (
  echo Commit : "%MSG%"
  git commit -m "%MSG%"
)

echo.
echo Push vers origin/%BRANCH% ...
git push origin %BRANCH%
if not errorlevel 1 (
  echo.
  echo ✅ Push réussi sur [%BRANCH%]
) else (
  echo.
  echo ❌ Echec du push (code %ERRORLEVEL%)
  echo    - Vérifie ta connexion/identifiants
  echo    - Ou essaie: git pull --rebase puis relance le .bat
)

echo.
echo Derniers commits locaux :
git log --oneline -n 3

echo.
pause
endlocal
