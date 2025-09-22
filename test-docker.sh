#!/bin/bash

# Script to test Docker build and run

set -e

echo "🔨 Building Docker image..."
docker build -t ghost-mcp-server:test .

echo "✅ Docker build successful!"

echo "📦 Checking image size..."
docker images ghost-mcp-server:test

echo "🧪 Running container in test mode..."
# Create a test .env file if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Created .env from .env.example - please update with real values"
fi

# Run container with health check
echo "🚀 Starting container..."
CONTAINER_ID=$(docker run -d \
    --name ghost-mcp-test \
    -p 8000:8000 \
    --env-file .env \
    ghost-mcp-server:test)

echo "⏳ Waiting for container to be healthy..."
for i in {1..30}; do
    if docker exec ghost-mcp-test curl -f http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ Container is healthy!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Container failed to become healthy"
        docker logs ghost-mcp-test
        docker stop ghost-mcp-test
        docker rm ghost-mcp-test
        exit 1
    fi
    sleep 2
done

echo "🔍 Testing endpoints..."
# Test root endpoint
echo "Testing / endpoint..."
docker exec ghost-mcp-test curl -s http://localhost:8000/ | python3 -m json.tool

# Test health endpoint
echo "Testing /health endpoint..."
docker exec ghost-mcp-test curl -s http://localhost:8000/health | python3 -m json.tool

echo "📋 Container logs:"
docker logs --tail 20 ghost-mcp-test

echo "🧹 Cleaning up..."
docker stop ghost-mcp-test
docker rm ghost-mcp-test

echo "✅ All Docker tests passed!"
echo ""
echo "To run in production:"
echo "  docker run -d --name ghost-mcp -p 8000:8000 --env-file .env ghost-mcp-server:test"