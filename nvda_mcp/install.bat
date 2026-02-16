@echo off
:: ============================================================
:: NVDA MCP — Installation automatique (Windows)
:: ============================================================
:: Ce script :
::   1. Verifie que NVDA est installe
::   2. Installe l'addon bridge dans NVDA (addons/, pas globalPlugins/)
::   3. Installe les dependances Python
::   4. Verifie Firefox
:: ============================================================

echo.
echo ============================================================
echo   NVDA MCP — Installation
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"

:: --- Verifier NVDA ---
if not exist "%APPDATA%\nvda" (
    echo [ERREUR] NVDA n'est pas installe ou n'a jamais ete lance.
    echo          Installez NVDA depuis https://www.nvaccess.org/download/
    echo          Lancez-le une premiere fois, puis relancez ce script.
    exit /b 1
)
echo [OK] Repertoire NVDA trouve : %APPDATA%\nvda

:: --- Supprimer l'ancien fichier globalPlugins si present ---
if exist "%APPDATA%\nvda\globalPlugins\nvdaMCPBridge.py" (
    del "%APPDATA%\nvda\globalPlugins\nvdaMCPBridge.py"
    echo [OK] Ancien plugin globalPlugins supprime (migration vers addon)
)

:: --- Installer l'addon bridge ---
set "ADDON_DEST=%APPDATA%\nvda\addons\nvdaMCPBridge"
set "PLUGIN_DEST=%ADDON_DEST%\globalPlugins\nvdaMCPBridge"

:: Verifier que les sources existent
if not exist "%SCRIPT_DIR%addon\manifest.ini" (
    echo [ERREUR] Fichier addon\manifest.ini introuvable.
    echo          Lancez ce script depuis le repertoire nvda_mcp.
    exit /b 1
)
if not exist "%SCRIPT_DIR%addon\globalPlugins\nvdaMCPBridge\__init__.py" (
    echo [ERREUR] Fichier addon source introuvable.
    exit /b 1
)

:: Creer l'arborescence addon
if exist "%ADDON_DEST%" (
    rmdir /s /q "%ADDON_DEST%"
)
mkdir "%PLUGIN_DEST%"

:: Copier les fichiers
copy /Y "%SCRIPT_DIR%addon\manifest.ini" "%ADDON_DEST%\" >nul
copy /Y "%SCRIPT_DIR%addon\globalPlugins\nvdaMCPBridge\__init__.py" "%PLUGIN_DEST%\" >nul

echo [OK] Addon installe dans %ADDON_DEST%
echo     manifest.ini
echo     globalPlugins\nvdaMCPBridge\__init__.py

:: --- Installer les dependances Python ---
echo.
echo Installation des dependances Python...
pip install mcp >nul 2>&1
if %errorlevel% neq 0 (
    echo [ATTENTION] pip install mcp a echoue. Verifiez votre installation Python.
) else (
    echo [OK] Dependance MCP installee
)

:: --- Verifier Firefox ---
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

:: --- Resume ---
echo.
echo ============================================================
echo   Installation terminee !
echo ============================================================
echo.
echo   Prochaines etapes :
echo     1. Redemarrer NVDA (le bridge se lance automatiquement)
echo     2. Ouvrir Firefox
echo     3. Verifier le bridge :
echo        curl http://127.0.0.1:8765/health
echo     4. Lancer le serveur MCP :
echo        python -m nvda_mcp --transport sse --port 8080
echo     5. Lancer un parcours :
echo        python -m nvda_mcp.navigator https://www.tanaguru.com -o restitution.txt
echo.
pause
