@echo off
:: ============================================================
:: NVDA MCP — Installation automatique (Windows)
:: ============================================================
:: Ce script :
::   1. Vérifie que NVDA est installé
::   2. Copie le plugin bridge dans NVDA
::   3. Installe les dépendances Python
::   4. Vérifie Firefox
:: ============================================================

echo.
echo ============================================================
echo   NVDA MCP — Installation
echo ============================================================
echo.

:: --- Vérifier NVDA ---
set "NVDA_PLUGINS=%APPDATA%\nvda\globalPlugins"
if not exist "%APPDATA%\nvda" (
    echo [ERREUR] NVDA n'est pas installe ou n'a jamais ete lance.
    echo          Installez NVDA depuis https://www.nvaccess.org/download/
    echo          Lancez-le une premiere fois, puis relancez ce script.
    exit /b 1
)
echo [OK] Repertoire NVDA trouve : %APPDATA%\nvda

:: --- Créer le répertoire globalPlugins si nécessaire ---
if not exist "%NVDA_PLUGINS%" (
    mkdir "%NVDA_PLUGINS%"
    echo [OK] Repertoire globalPlugins cree
)

:: --- Copier le plugin bridge ---
set "SCRIPT_DIR=%~dp0"
set "BRIDGE_SRC=%SCRIPT_DIR%nvda_global_plugin\nvdaMCPBridge.py"

if not exist "%BRIDGE_SRC%" (
    echo [ERREUR] Plugin bridge introuvable : %BRIDGE_SRC%
    echo          Verifiez que vous lancez ce script depuis le repertoire nvda_mcp.
    exit /b 1
)

copy /Y "%BRIDGE_SRC%" "%NVDA_PLUGINS%\nvdaMCPBridge.py" >nul
echo [OK] Plugin bridge copie dans %NVDA_PLUGINS%\nvdaMCPBridge.py

:: --- Installer les dépendances Python ---
echo.
echo Installation des dependances Python...
pip install mcp >nul 2>&1
if %errorlevel% neq 0 (
    echo [ATTENTION] pip install mcp a echoue. Verifiez votre installation Python.
) else (
    echo [OK] Dependance MCP installee
)

:: --- Vérifier Firefox ---
echo.
set "FIREFOX_PATH="
if exist "C:\Program Files\Mozilla Firefox\firefox.exe" set "FIREFOX_PATH=C:\Program Files\Mozilla Firefox\firefox.exe"
if exist "C:\Program Files (x86)\Mozilla Firefox\firefox.exe" set "FIREFOX_PATH=C:\Program Files (x86)\Mozilla Firefox\firefox.exe"

if defined FIREFOX_PATH (
    echo [OK] Firefox trouve : %FIREFOX_PATH%
) else (
    echo [ATTENTION] Firefox non trouve dans les chemins habituels.
    echo             NVDA necessite Firefox pour naviguer sur le web.
    echo             Installez Firefox depuis https://www.mozilla.org/firefox/
)

:: --- Résumé ---
echo.
echo ============================================================
echo   Installation terminee !
echo ============================================================
echo.
echo   Prochaines etapes :
echo     1. Redemarrer NVDA (le bridge se lance automatiquement)
echo     2. Ouvrir Firefox
echo     3. Verifier le bridge : curl http://127.0.0.1:8765/health
echo     4. Lancer le serveur MCP :
echo        python -m nvda_mcp --transport sse --port 8080
echo     5. Lancer un parcours :
echo        python -m nvda_mcp.navigator https://www.tanaguru.com -o restitution.txt
echo.
pause
