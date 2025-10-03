@echo off
REM Newsroom Docker Setup for Windows
REM ===================================

echo.
echo Newsroom Docker Setup (Windows)
echo ================================
echo.

REM Check if docker-compose.yml exists
if not exist "docker-compose.yml" (
    echo [ERROR] docker-compose.yml not found!
    echo Please run this script from the project root directory.
    pause
    exit /b 1
)

REM Check if .env exists
if not exist ".env" (
    echo [INFO] Creating .env file...
    if exist ".env.example" (
        copy .env.example .env
        echo [OK] .env created from .env.example
        echo.
        echo [WARNING] Please edit .env and add your OPENAI_API_KEY!
        echo Opening .env in notepad...
        timeout /t 2 >nul
        notepad .env
        echo.
        echo Press any key after you've added OPENAI_API_KEY...
        pause >nul
    ) else (
        echo [ERROR] .env.example not found!
        pause
        exit /b 1
    )
)

REM Create nginx directories
echo [INFO] Creating nginx directories...
if not exist "nginx" mkdir nginx
if not exist "nginx\ssl" mkdir nginx\ssl

REM Check for SSL certificates
if not exist "nginx\ssl\fullchain.pem" (
    echo.
    echo [INFO] SSL certificates not found.
    echo.
    echo Choose certificate type:
    echo   1. Self-signed (for development/testing) - RECOMMENDED
    echo   2. I'll add them manually later
    echo.
    set /p cert_choice="Enter choice (1-2): "
    
    if "%cert_choice%"=="1" (
        echo.
        echo [INFO] Creating self-signed certificates...
        echo.
        
        REM Check if openssl is available
        where openssl >nul 2>nul
        if %errorlevel% neq 0 (
            echo [ERROR] OpenSSL not found!
            echo.
            echo Please install OpenSSL or Git for Windows which includes OpenSSL.
            echo Download from: https://git-scm.com/download/win
            echo.
            echo After installation, run this script again.
            pause
            exit /b 1
        )
        
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout nginx\ssl\privkey.pem -out nginx\ssl\fullchain.pem -subj "/C=FI/ST=Pirkanmaa/L=Tampere/O=Dev/CN=localhost" 2>nul
        
        if exist "nginx\ssl\fullchain.pem" (
            echo [OK] Self-signed certificates created
        ) else (
            echo [ERROR] Failed to create certificates
            pause
            exit /b 1
        )
    ) else (
        echo [WARNING] Remember to add certificates to nginx\ssl\ before starting
    )
)

REM Create static directory
echo [INFO] Creating static directory...
if not exist "static" mkdir static

REM Check if Docker is running
echo.
echo [INFO] Checking Docker...
docker version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop and run this script again.
    pause
    exit /b 1
)

docker-compose version >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] docker-compose is not installed!
    pause
    exit /b 1
)

echo [OK] Docker is running

REM Build images
echo.
echo [INFO] Building Docker images...
echo This may take 5-10 minutes on first run...
echo.
docker-compose build

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

REM Start services
echo.
echo [INFO] Starting services...
docker-compose up -d

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start services!
    pause
    exit /b 1
)

REM Wait for services
echo.
echo [INFO] Waiting for services to start...
timeout /t 15 >nul

REM Check status
echo.
echo [INFO] Checking service status...
docker-compose ps

echo.
echo ============================================
echo [OK] Setup complete!
echo ============================================
echo.
echo SERVICES:
echo   Main URL:     https://localhost
echo   GraphQL:      https://localhost/graphql
echo   Health:       https://localhost/health
echo   API Docs:     https://localhost/docs
echo.
echo USEFUL COMMANDS:
echo   View logs:       docker-compose logs -f
echo   Stop all:        docker-compose down
echo   Restart service: docker-compose restart backend
echo   Check status:    docker-compose ps
echo.
echo NOTE: If using self-signed certificates, your browser
echo       will show a security warning. This is normal for
echo       development. Click "Advanced" and proceed.
echo.
pause