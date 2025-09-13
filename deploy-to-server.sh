#!/bin/bash

# Deployment script for Digital Ocean droplet
# Usage: ./deploy-to-server.sh YOUR_DROPLET_IP

if [ -z "$1" ]; then
    echo "❌ Error: Please provide your droplet IP address"
    echo "Usage: ./deploy-to-server.sh YOUR_DROPLET_IP"
    exit 1
fi

DROPLET_IP=$1
APP_DIR="/app/vending-machine"

echo "🚀 Deploying vending-machine to $DROPLET_IP..."

# Step 1: Transfer files to server
echo "📦 Transferring files..."
rsync -avz --progress \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '*.md' \
    --exclude 'test_*.py' \
    --exclude '*.json' \
    --exclude '*.xml' \
    --exclude '*.html' \
    . root@$DROPLET_IP:$APP_DIR/vm-py/

if [ $? -ne 0 ]; then
    echo "❌ File transfer failed!"
    exit 1
fi

# Step 2: Build and deploy on server
echo "🔨 Building and deploying on server..."
ssh root@$DROPLET_IP << EOF
cd $APP_DIR/vm-py

# Stop existing container
echo "🛑 Stopping existing container..."
docker stop vending-machine-api 2>/dev/null
docker rm vending-machine-api 2>/dev/null

# Make build script executable
chmod +x docker-build.sh

# Build new image
echo "🔨 Building Docker image..."
./docker-build.sh

if [ \$? -eq 0 ]; then
    # Run new container
    echo "🚀 Starting new container..."
    docker run -d \
        --name vending-machine-api \
        --restart unless-stopped \
        -p 8000:8000 \
        vending-machine-api
    
    echo "✅ Deployment successful!"
    echo "🌐 Your app is running at: http://$DROPLET_IP:8000"
    
    # Check status
    sleep 3
    echo "📊 Container status:"
    docker ps | grep vending-machine-api
    
    echo "🏥 Health check:"
    curl -s http://localhost:8000/status | head -3
else
    echo "❌ Docker build failed!"
    exit 1
fi
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Deployment completed successfully!"
    echo "🌐 Access your app at: http://$DROPLET_IP:8000"
    echo "📊 Check status at: http://$DROPLET_IP:8000/status"
else
    echo "❌ Deployment failed!"
    exit 1
fi
