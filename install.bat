@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo  ╔══════════════════════════════════════╗
echo  ║     SubSync — Kurulum Başlıyor       ║
echo  ║  İngilizce → Türkçe Altyazı Aracı   ║
echo  ╚══════════════════════════════════════╝
echo.

set SCRIPT_DIR=%~dp0
set CONDA_BASE=%USERPROFILE%\miniconda3
set ENV_NAME=subsync
set MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe
set MINICONDA_INSTALLER=%TEMP%\miniconda_installer.exe

:: ── 1. Miniconda kurulu mu? ──────────────────────────────────────────────────
echo [1/6] Miniconda kontrol ediliyor...
if exist "%CONDA_BASE%\Scripts\conda.exe" (
    echo       Miniconda zaten kurulu, atlanıyor.
) else (
    echo       Miniconda bulunamadı, indiriliyor...
    powershell -Command "Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile '%MINICONDA_INSTALLER%'"
    if errorlevel 1 (
        echo HATA: Miniconda indirilemedi. İnternet bağlantınızı kontrol edin.
        pause & exit /b 1
    )
    echo       Miniconda kuruluyor...
    start /wait "" "%MINICONDA_INSTALLER%" /InstallationType=JustMe /RegisterPython=0 /S /D=%CONDA_BASE%
    if errorlevel 1 (
        echo HATA: Miniconda kurulumu başarısız.
        pause & exit /b 1
    )
    echo       Miniconda kuruldu ✓
)

:: ── 2. Conda env oluştur ─────────────────────────────────────────────────────
echo.
echo [2/6] Conda ortamı oluşturuluyor...
call "%CONDA_BASE%\Scripts\activate.bat"
call conda create -n %ENV_NAME% python=3.11 -y >nul 2>&1
echo       Ortam hazır ✓

:: ── 3. PyTorch kur ──────────────────────────────────────────────────────────
echo.
echo [3/6] PyTorch kuruluyor (GPU varsa CUDA, yoksa CPU)...
call conda activate %ENV_NAME%

:: GPU var mı kontrol et
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo       GPU bulunamadı, CPU sürümü kuruluyor...
    call pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu -q
) else (
    echo       NVIDIA GPU tespit edildi, CUDA sürümü kuruluyor...
    call pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 -q
)
echo       PyTorch kuruldu ✓

:: ── 4. Kütüphaneleri kur ─────────────────────────────────────────────────────
echo.
echo [4/6] Kütüphaneler kuruluyor...
call pip install faster-whisper gradio google-generativeai yt-dlp dbus-next pystray pillow huggingface_hub tqdm -q
echo       Kütüphaneler kuruldu ✓

:: ── 5. ffmpeg kur ────────────────────────────────────────────────────────────
echo.
echo [5/6] ffmpeg kuruluyor...
call conda install -c conda-forge ffmpeg -y -q >nul 2>&1
echo       ffmpeg kuruldu ✓

:: ── 6. Whisper modeli indir ───────────────────────────────────────────────────
echo.
echo [6/6] Whisper modeli indiriliyor (ilk seferinde ~1.5GB)...
python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')" 2>nul
echo       Whisper modeli hazır ✓

:: ── Masaüstü kısayolu oluştur ────────────────────────────────────────────────
echo.
echo Masaüstü kısayolu oluşturuluyor...
set SHORTCUT=%USERPROFILE%\Desktop\SubSync.lnk
set TARGET=%SCRIPT_DIR%launch.bat
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.IconLocation = 'shell32.dll,277'; $s.Description = 'SubSync - İngilizce → Türkçe Altyazı'; $s.Save()"
echo       Masaüstü kısayolu oluşturuldu ✓

echo.
echo  ╔══════════════════════════════════════╗
echo  ║        Kurulum Tamamlandı!           ║
echo  ║                                      ║
echo  ║  Başlatmak için:                     ║
echo  ║  • Masaüstündeki SubSync ikonuna     ║
echo  ║    çift tıklayın                     ║
echo  ║                                      ║
echo  ║  İlk açılışta Ayarlar sekmesinden    ║
echo  ║  Gemini API key girmeyi unutmayın.   ║
echo  ╚══════════════════════════════════════╝
echo.
pause
