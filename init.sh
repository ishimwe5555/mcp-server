#!/bin/bash

# Eddie MCP Service - Quick Start Script

set -e

echo "🚀 Eddie MCP Service - Quick Start"
echo "=================================="
echo ""

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✓ Docker & Docker Compose found"

# Check for .env file
if [ ! -f .env ]; then
    echo ""
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env with your OAuth2 credentials:"
    echo "   - OAUTH2_CLIENT_ID"
    echo "   - OAUTH2_USERNAME"
    echo "   - OAUTH2_PASSWORD"
    echo ""
    read -p "Press Enter to continue after you've edited .env..."
fi

echo ""
echo "📦 Building Docker image..."
docker-compose build

echo ""
echo "🏃 Starting Eddie MCP Service..."
docker-compose up -d

echo ""
echo "⏳ Waiting for service to be ready..."
sleep 5

echo ""
echo "🔍 Checking health..."
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✓ Service is healthy!"
else
    echo "⚠️  Service might need more time to start. Check logs:"
    echo "   docker-compose logs -f"
fi

echo ""
echo "📊 Available endpoints:"
echo "   - API Docs:      http://localhost:8000/docs"
echo "   - Health Check:  http://localhost:8000/health"
echo "   - List Tools:    http://localhost:8000/tools"
echo "   - Auth Status:   http://localhost:8000/auth/status"
echo ""
echo "🔗 View logs:"
echo "   docker-compose logs -f eddie-mcp"
echo ""
echo "🛑 To stop the service:"
echo "   docker-compose down"
echo ""
echo "✅ Setup complete!"
