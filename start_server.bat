@echo off
cd /d C:\wavis\wavis_v4

call .venv\Scripts\activate.bat

echo ==========================================
echo WAVIS v4 서버를 시작합니다.
echo 프로젝트 경로: C:\wavis\wavis_v4
echo ==========================================

uvicorn main:app --host 0.0.0.0 --port 8787 --reload

pause