@echo off
:: SubSync — Windows başlatıcı
:: Bu batch dosyası nerede olursa olsun doğru dizini bulur

set SCRIPT_DIR=%~dp0
set CONDA_BASE=%USERPROFILE%\miniconda3
set ENV_NAME=subtitle-pipeline

if not exist "%CONDA_BASE%\Scripts\activate.bat" (
    echo Conda bulunamadi: %CONDA_BASE%
    echo Miniconda kurulu mu?
    pause
    exit /b 1
)

call "%CONDA_BASE%\Scripts\activate.bat" %ENV_NAME%
pythonw "%SCRIPT_DIR%tray.py"
