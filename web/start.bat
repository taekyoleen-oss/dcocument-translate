@echo off
chcp 65001 >nul
echo.
echo ============================================
echo   논문 번역 시스템 시작
echo ============================================
echo.

REM ANTHROPIC_API_KEY 확인
if "%ANTHROPIC_API_KEY%"=="" (
    echo [오류] ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.
    echo.
    echo 다음 명령어로 API 키를 설정한 후 다시 실행하세요:
    echo   set ANTHROPIC_API_KEY=sk-ant-api03-...
    echo.
    pause
    exit /b 1
)

REM 의존성 확인 및 설치
echo [1/2] 패키지 설치 확인 중...
pip install -q -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [오류] 패키지 설치 실패
    pause
    exit /b 1
)

echo.
echo [2/2] 서버 시작 중...
echo.
echo   브라우저에서 접속: http://localhost:8000
echo   종료하려면 Ctrl+C 를 누르세요.
echo.

cd /d "%~dp0"
python -m uvicorn app:app --host 0.0.0.0 --port 8000
