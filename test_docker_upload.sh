#!/bin/bash

# Test script to debug Docker upload issues
# This script will build and run the Docker container with debug output

echo "🐳 DOCKER UPLOAD DEBUG TEST"
echo "=========================="

# Build the Docker image
echo "📦 Building Docker image..."
cd /Users/warren/dev/vending-machine/vm-py
docker build -t vending-machine-debug -f Dockerfile .

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed!"
    exit 1
fi

echo "✅ Docker build successful!"

# Run the debug script inside Docker
echo ""
echo "🔍 Running debug script inside Docker container..."
echo "================================================="

docker run --rm --env-file .env vending-machine-debug conda run -n vending-machine python debug_upload.py

echo ""
echo "🏁 Docker debug test completed!"

# Also test the status endpoint
echo ""
echo "🌐 Testing status endpoint in Docker..."
echo "======================================"

# Start container in background
docker run -d --name vending-machine-debug-test --env-file .env -p 8001:8000 vending-machine-debug

# Wait a moment for startup
sleep 5

# Test status endpoint
echo "📡 Calling /status endpoint..."
curl -s http://localhost:8001/status | python -m json.tool

# Cleanup
echo ""
echo "🧹 Cleaning up..."
docker stop vending-machine-debug-test
docker rm vending-machine-debug-test

echo "✅ All tests completed!"

