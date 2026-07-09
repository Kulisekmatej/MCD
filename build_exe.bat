@echo off
REM ============================================================
REM  Sestaveni .exe aplikace pro Windows pomoci Nuitky.
REM  Nuitka prelozi Python do C a zkompiluje do nativni binarky
REM  (mene planych hlaseni antiviru, rychlejsi, hur dekompilovatelne).
REM  Spustit na Windows s nainstalovanym Pythonem (python.org).
REM  Pri prvnim spusteni si Nuitka muze stahnout C kompilator (MinGW)
REM  - potvrd stazeni "yes".
REM ============================================================

echo Instaluji zavislosti...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt nuitka
if errorlevel 1 (
    echo.
    echo CHYBA pri instalaci zavislosti. Mas nainstalovany Python z python.org?
    pause
    exit /b 1
)

echo.
echo Sestavuji aplikaci pomoci Nuitky (muze chvili trvat) ...
python -m nuitka --standalone --assume-yes-for-downloads ^
    --enable-plugin=tk-inter --windows-console-mode=disable ^
    --include-package=hours_tracker --include-package=pdfplumber ^
    --include-package=pdfminer --include-package=openpyxl ^
    --include-package-data=pdfminer ^
    --output-dir=build_nuitka --output-filename=PocitadloHodin.exe main.py
if errorlevel 1 (
    echo.
    echo CHYBA pri sestaveni.
    pause
    exit /b 1
)

echo.
echo Hotovo! Aplikaci spustis zde:
echo    build_nuitka\main.dist\PocitadloHodin.exe
echo (celou slozku main.dist muzes prejmenovat, zkopirovat nebo zazipovat a prenest jinam)
echo.
pause
