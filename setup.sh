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

# Luo nginx-kansiot
echo "📁 Creating nginx directories..."
mkdir -p nginx/ssl

# Tarkista SSL-sertifikaatit
if [ ! -f nginx/ssl/fullchain.pem ] || [ ! -f nginx/ssl/privkey.pem ]; then
    echo "🔐 SSL certificates not found."
    echo ""
    echo "Choose certificate type:"
    echo "  1) Self-signed (for development/testing)"
    echo "  2) Let's Encrypt (for production)"
    echo "  3) I'll add them manually later"
    echo ""
    read -p "Enter choice (1-3): " cert_choice
    
    case $cert_choice in
        1)
            echo "Creating self-signed certificates..."
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout nginx/ssl/privkey.pem \
                -out nginx/ssl/fullchain.pem \
                -subj "/C=FI/ST=Pirkanmaa/L=Tampere/O=Dev/CN=localhost" \
                2>/dev/null
            chmod 644 nginx/ssl/*.pem
            echo "✅ Self-signed certificates created"
            ;;
        2)
            echo ""
            echo "For Let's Encrypt certificates:"
            echo "1. Stop nginx if running: docker-compose stop nginx"
            echo "2. Run: sudo certbot certonly --standalone -d your-domain.com"
            echo "3. Copy certificates:"
            echo "   sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/"
            echo "   sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/"
            echo "   sudo chmod 644 nginx/ssl/*.pem"
            echo ""
            read -p "Press Enter after you've added certificates..."
            ;;
        3)
            echo "⚠️  Remember to add certificates to nginx/ssl/ before starting nginx"
            ;;
        *)
            echo "Invalid choice. Creating self-signed certificates..."
            openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
                -keyout nginx/ssl/privkey.pem \
                -out nginx/ssl/fullchain.pem \
                -subj "/C=FI/ST=Pirkanmaa/L=Tampere/O=Dev/CN=localhost" \
                2>/dev/null
            chmod 644 nginx/ssl/*.pem
            ;;
    esac
fi

# Luo static-kansio
echo "📁 Creating static directory..."
mkdir -p static

# Tarkista Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed!"
    exit 1
fi

# Rakenna imaget
echo ""
echo "🏗️  Building Docker images..."
echo "   This may take 5-10 minutes on first run..."
echo ""
docker-compose build

# Käynnistä servicet
echo ""
echo "🚀 Starting services..."
docker-compose up -d

# Odota että servicet käynnistyvät
echo ""
echo "⏳ Waiting for services to start..."
sleep 15

# Tarkista status
echo ""
echo "🔍 Checking service status..."
docker-compose ps

echo ""
echo "✅ Setup complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 SERVICES:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🌐 Main URL:     https://localhost"
echo "  📊 GraphQL:      https://localhost/graphql"
echo "  🏥 Health:       https://localhost/health"
echo "  📚 API Docs:     https://localhost/docs"
echo "  📁 Static files: https://localhost/static/"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 USEFUL COMMANDS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  View logs:       docker-compose logs -f"
echo "  Stop all:        docker-compose down"
echo "  Restart service: docker-compose restart backend"
echo "  Check status:    docker-compose ps"
echo ""
echo "⚠️  Note: If using self-signed certificates, you'll get"
echo "   browser warnings. Use curl -k or accept the certificate."
echo ""