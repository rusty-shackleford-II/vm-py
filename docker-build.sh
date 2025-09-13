#!/bin/bash

# Docker build script for vending-machine FastAPI app

echo "🐳 Building vending-machine Docker image..."

# Build the Docker image
docker build -t vending-machine-api .

if [ $? -eq 0 ]; then
    echo "✅ Docker image built successfully!"
    echo ""
    echo "To run the container:"
    echo "  docker run -p 8000:8000 vending-machine-api"
    echo ""
    echo "To run with environment variables:"
    echo "  docker run -p 8000:8000 --env-file .env vending-machine-api"
    echo ""
    echo "To run in background:"
    echo "  docker run -d -p 8000:8000 --name vending-machine --env-file .env vending-machine-api"
else
    echo "❌ Docker build failed!"
    exit 1
fi
