#!/bin/bash

# Server initialization script for Digital Ocean Docker droplet
# Usage: ./setup-server.sh YOUR_DROPLET_IP

if [ -z "$1" ]; then
    echo "❌ Error: Please provide your droplet IP address"
    echo "Usage: ./setup-server.sh YOUR_DROPLET_IP"
    exit 1
fi

DROPLET_IP=$1

echo "🔧 Initializing Docker droplet at $DROPLET_IP..."

# Run server initialization commands
ssh root@$DROPLET_IP << 'EOF'
echo "📦 Updating system packages..."
apt update && apt upgrade -y

echo "🔧 Installing essential packages..."
apt install -y git curl wget htop nano ufw

echo "✅ Docker already installed on Docker droplet"

echo "🔥 Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8000/tcp
ufw --force enable
echo "✅ Firewall configured"

echo "📁 Creating application directory..."
mkdir -p /app/vending-machine
cd /app/vending-machine

echo "📝 Creating update script..."
cat > update.sh << 'SCRIPT_EOF'
#!/bin/bash

echo "🔄 Updating vending-machine application..."

# Pull latest code if using git
if [ -d ".git" ]; then
    git pull origin main
fi

# Stop and remove existing container
docker stop vending-machine-api 2>/dev/null
docker rm vending-machine-api 2>/dev/null

# Navigate to app directory
cd /app/vending-machine/vm-py

# Rebuild Docker image
./docker-build.sh

# Run new container
docker run -d \
  --name vending-machine-api \
  --restart unless-stopped \
  -p 8000:8000 \
  vending-machine-api

echo "✅ Update complete! Application is running on port 8000"
echo "🌐 Access your app at: http://$(curl -s ifconfig.me):8000"

# Show container status
docker ps | grep vending-machine-api
SCRIPT_EOF

chmod +x update.sh

echo "🧹 Setting up system cleanup..."
cat > /etc/cron.weekly/docker-cleanup << 'CLEANUP_EOF'
#!/bin/bash
docker system prune -f
CLEANUP_EOF

chmod +x /etc/cron.weekly/docker-cleanup

echo ""
echo "🎉 Server setup completed successfully!"
echo ""
echo "📋 What was configured:"
echo "  ✅ System updates"
echo "  ✅ Essential packages (git, curl, wget, htop, nano, ufw)"
echo "  ✅ Firewall configuration (ports 22, 80, 443, 8000)"
echo "  ✅ Application directory: /app/vending-machine"
echo "  ✅ Update script: /app/vending-machine/update.sh"
echo "  ✅ Weekly Docker cleanup job"
echo ""
echo "🚀 Next steps:"
echo "  1. Transfer your .env file to the server"
echo "  2. Run: ./deploy-to-server.sh $DROPLET_IP"
echo ""

# Show system info
echo "💻 Server information:"
echo "  OS: $(lsb_release -d | cut -f2)"
echo "  Memory: $(free -h | grep '^Mem:' | awk '{print $2}')"
echo "  Disk: $(df -h / | tail -1 | awk '{print $2}')"
echo "  Docker: $(docker --version)"
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Server setup completed successfully!"
    echo ""
    echo "🚀 Next steps:"
    echo "  1. Make sure your .env file is in vm-py/.env"
    echo "  2. Deploy your app: ./deploy-to-server.sh $DROPLET_IP"
    echo ""
else
    echo "❌ Server setup failed!"
    exit 1
fi
