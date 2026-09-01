@echo off
REM Gera o executavel do Alt em .\Programa\Alt.exe
REM
REM Monta em pasta, e nao em arquivo unico, de proposito: executavel de arquivo
REM unico se autodescompacta no %TEMP% a cada abertura, e a heuristica de
REM antivirus marca esse comportamento.
REM
REM Os --hidden-import sao obrigatorios: esses modulos sao importados dentro de
REM funcao, e a analise estatica do PyInstaller nao os encontra sozinha.

setlocal
cd /d "%~dp0"

echo.
echo == Alt: gerando executavel ==
echo.

python -m PyInstaller --noconfirm --clean --windowed ^
  --name Alt --icon alt.ico --add-data "alt.ico;." ^
  --hidden-import win32clipboard --hidden-import win32api ^
  --hidden-import win32con --hidden-import win32gui ^
  --exclude-module numpy --exclude-module pytest ^
  alt.py

if errorlevel 1 (
  echo.
  echo FALHOU. Se faltar o PyInstaller:  pip install pyinstaller
  exit /b 1
)

echo.
echo == organizando ==
if exist "Programa" rmdir /s /q "Programa"
move "dist\Alt" "Programa" >nul
rmdir /s /q "dist" 2>nul
rmdir /s /q "build" 2>nul
del "Alt.spec" 2>nul

echo.
echo Pronto: Programa\Alt.exe
echo Conferindo com o autoteste:
echo.
"Programa\Alt.exe" --autoteste

endlocal
