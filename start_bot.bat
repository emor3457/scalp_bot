@echo off
echo ==================================================
echo BIST Scalp Botu Baslatiliyor...
echo ==================================================

:: Proje dizinine gec
cd /d "%~dp0"

:: Sanal ortami aktif et
call .\.venv\Scripts\activate.bat

:: Sunucuyu baslat
echo FastAPI sunucusu baslatiliyor...
uvicorn main:app --reload

pause
