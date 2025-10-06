@echo off
setlocal enabledelayedexpansion

echo.
echo Newsroom Docker Setup for Windows
echo ================================
echo.

if not exist "docker-compose.yml" (
    echo ERROR: docker-compose.yml not found!
    echo Please run this script from the project root directory.
    pause
    exit /b 1
)

if not exist ".env" (
    echo INFO: Creating .env file...
    if exist ".env.example" (
        copy .env.example .env
        echo OK: .env created
        echo.
        echo WARNING: Edit .env and add your OPENAI_API_KEY
        echo Opening notepad...
        timeout /t 2 >nul
        notepad .env
        echo.
        pause
    ) else (
        echo ERROR: .env.example not found
        pause
        exit /b 1
    )
) else (
    echo INFO: .env exists, skipping
)

echo INFO: Creating nginx directories...
if not exist "nginx" mkdir nginx
if not exist "nginx\ssl" mkdir nginx\ssl

if not exist "nginx\ssl\fullchain.pem" (
    echo.
    echo INFO: SSL certificates not found
    echo.
    echo Choose certificate type:
    echo   1 = Self-signed for development
    echo   2 = I will add manually
    echo.
    set /p cert_choice="Enter 1 or 2: "
    
    if "!cert_choice!"=="1" (
        echo.
        echo INFO: Creating self-signed certificates...
        
        where openssl >nul 2>nul
        if !errorlevel! neq 0 (
            echo ERROR: OpenSSL not found
            echo.
            echo Install Git for Windows from:
            echo https://git-scm.com/download/win
            echo.
            pause
            exit /b 1
        )
        
        REM Luo molemmat sertifikaatit ilman -subj (välttää Git Bash ongelman)
        echo | openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout nginx\ssl\privkey.pem -out nginx\ssl\fullchain.pem -batch 2>nul
        
        if exist "nginx\ssl\fullchain.pem" (
            echo OK: Certificates created
        ) else (
            echo ERROR: Failed to create certificates
            pause
            exit /b 1
        )
    ) else (
        echo INFO: Add certificates to nginx\ssl\ manually
    )
) else (
    echo INFO: SSL certificates exist, skipping
)

echo INFO: Creating static directory...
if not exist "static" mkdir static

echo.
echo INFO: Checking Docker...
docker version >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Docker is not running
    echo Start Docker Desktop and run this script again
    pause
    exit /b 1
)

docker-compose version >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: docker-compose not installed
    pause
    exit /b 1
)

echo OK: Docker is running

echo.
echo INFO: Building Docker images...
echo This takes 5-10 minutes on first run...
echo.
docker-compose build

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Build failed
    pause
    exit /b 1
)

echo.
echo INFO: Starting services...
docker-compose up -d

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to start services
    pause
    exit /b 1
)

echo.
echo INFO: Waiting for services...
timeout /t 15 >nul

echo.
echo INFO: Service status:
docker-compose ps

echo.
echo ============================================
echo Setup complete!
echo ============================================
echo.
echo SERVICES:
echo   https://localhost
echo   https://localhost/graphql
echo   https://localhost/health
echo   https://localhost/docs
echo.
echo COMMANDS:
echo   Logs:    docker-compose logs -f
echo   Stop:    docker-compose down
echo   Restart: docker-compose restart backend
echo   Status:  docker-compose ps
echo.
echo NOTE: Browser will show security warning
echo       for self-signed certificates.
echo       Click Advanced and proceed.
echo.
pause