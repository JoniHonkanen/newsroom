#!/bin/bash
# LINUX TUOTANTO
# Newsroom Docker Setup Script
# Toimii sekä kehityksessä että tuotannossa

set -e

echo "🚀 Newsroom Docker Setup"
echo "========================"
echo ""

# Tarkista että ollaan oikeassa kansiossa
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: docker-compose.yml not found!"
    echo "   Please run this script from the project root directory."
    exit 1
fi

# Tarkista että tarvittavat tiedostot on olemassa
if [ ! -f "server.py" ] || [ ! -f "graphql_server.py" ] || [ ! -f "main.py" ]; then
    echo "❌ Error: Required Python files not found!"
    echo "   Make sure you're in the correct project directory."
    exit 1
fi

# Luo .env jos ei ole olemassa
if [ ! -f .env ]; then
    echo "📝 Creating .env file..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✅ .env created from .env.example"
        echo ""
        echo "⚠️  IMPORTANT: Edit .env and add your OPENAI_API_KEY!"
        echo "   nano .env"
        echo ""
        read -p "Press Enter after you've added OPENAI_API_KEY to .env..."
    else
        echo "❌ .env.example not found!"
        exit 1
    fi
fi

# Tarkista että OPENAI_API_KEY on asetettu
if ! grep -q "OPENAI_API_KEY=sk-" .env; then
    echo "⚠️  Warning: OPENAI_API_KEY not properly set in .env"
    echo "   Current value: $(grep OPENAI_API_KEY .env)"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Please edit .env first."
        exit 1
    fi
fi

# Luo tarvittavat kansiot
echo "📁 Creating necessary directories..."
mkdir -p npm/data
mkdir -p npm/letsencrypt
mkdir -p static

echo "✅ Directories created"

# Tarkista Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ docker-compose is not installed!"
    exit 1
fi

echo "✅ Docker is installed"

# Rakenna imaget
echo ""
echo "🏗️  Building Docker images..."
echo "   This may take 5-10 minutes on first run..."
echo ""
docker compose build

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Build failed"
    exit 1
fi

# Käynnistä servicet
echo ""
echo "🚀 Starting services..."
docker compose up -d

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Failed to start services"
    exit 1
fi

# Odota että servicet käynnistyvät
echo ""
echo "⏳ Waiting for services to start..."
sleep 15

# Tarkista status
echo ""
echo "🔍 Checking service status..."
docker compose ps

echo ""
echo "✅ Setup complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 SERVICES:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🌐 Nginx Proxy Manager: http://YOUR_IP:81"
echo "     Default login: admin@example.com / changeme"
echo "     ⚠️  CHANGE PASSWORD IMMEDIATELY!"
echo ""
echo "  📊 Backend API:      http://YOUR_IP:8000/docs"
echo "  📊 GraphQL:          http://YOUR_IP:4000/graphql"
echo "  🏥 Health:           http://YOUR_IP:8000/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔐 NEXT STEPS - NGINX PROXY MANAGER:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Open http://YOUR_IP:81"
echo "2. Login with: admin@example.com / changeme"
echo "3. Change password immediately"
echo "4. Add Proxy Host for your domain:"
echo "   - Domain: api.yourdomain.com"
echo "   - Forward to: backend:8000"
echo "   - Enable WebSocket Support"
echo "   - Request SSL Certificate (Let's Encrypt)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 USEFUL COMMANDS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  View logs:       docker compose logs -f"
echo "  View NPM logs:   docker compose logs -f npm"
echo "  Stop all:        docker compose down"
echo "  Restart service: docker compose restart backend"
echo "  Check status:    docker compose ps"
echo ""
echo "⚠️  Remember to update .env with:"
echo "   LOCALTUNNEL_URL=https://api.yourdomain.com"
echo ""