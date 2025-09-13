# 🚀 Digital Ocean Deployment Guide

This guide covers deploying the vending-machine FastAPI app to a Digital Ocean droplet using Docker.

## 📋 Prerequisites

- Digital Ocean droplet with Docker installed
- SSH access to your droplet
- Your `.env` file with all required environment variables
- Domain name (optional, for production)

## 🔧 Initial Server Setup

### 1. Connect to Your Droplet

```bash
ssh root@YOUR_DROPLET_IP
```

### 2. Update System and Install Dependencies

```bash
# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y git curl wget htop nano ufw

# Install Docker (if not already installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Start Docker service
systemctl start docker
systemctl enable docker
```

### 3. Setup Firewall

```bash
# Configure UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw allow 8000/tcp  # FastAPI app
ufw --force enable
```

### 4. Create Application Directory

```bash
mkdir -p /app/vending-machine
cd /app/vending-machine
```

## 📦 Deploy the Application

### Method 1: Direct File Transfer (Recommended for Development)

#### Step 1: Transfer Files to Server

From your local machine:

```bash
# Copy the entire vm-py directory to your droplet
scp -r vm-py/ root@YOUR_DROPLET_IP:/app/vending-machine/

# Or use rsync for better performance
rsync -avz --progress vm-py/ root@YOUR_DROPLET_IP:/app/vending-machine/
```

#### Step 2: Build and Run on Server

SSH into your droplet and run:

```bash
cd /app/vending-machine

# Make build script executable
chmod +x docker-build.sh

# Build the Docker image
./docker-build.sh

# Run the container
docker run -d \
  --name vending-machine-api \
  --restart unless-stopped \
  -p 8000:8000 \
  vending-machine-api
```

### Method 2: Git Repository (Recommended for Production)

#### Step 1: Setup Git Repository

```bash
cd /app/vending-machine

# Clone your repository
git clone https://github.com/YOUR_USERNAME/vending-machine.git .

# Or if using private repo with token:
git clone https://YOUR_TOKEN@github.com/YOUR_USERNAME/vending-machine.git .
```

#### Step 2: Add Environment File

```bash
# Create .env file (copy from your local machine or create manually)
nano vm-py/.env

# Paste your environment variables and save (Ctrl+X, Y, Enter)
```

#### Step 3: Build and Deploy

```bash
cd vm-py

# Build the Docker image
./docker-build.sh

# Run the container
docker run -d \
  --name vending-machine-api \
  --restart unless-stopped \
  -p 8000:8000 \
  vending-machine-api
```

## 🔄 Updating the Application

### Quick Update Script

Create an update script for easy deployments:

```bash
# Create update script
cat > /app/vending-machine/update.sh << 'EOF'
#!/bin/bash

echo "🔄 Updating vending-machine application..."

# Stop and remove existing container
docker stop vending-machine-api 2>/dev/null
docker rm vending-machine-api 2>/dev/null

# Pull latest code (if using git)
git pull origin main

# Navigate to app directory
cd vm-py

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
EOF

# Make it executable
chmod +x /app/vending-machine/update.sh
```

### To Update Your App:

```bash
cd /app/vending-machine
./update.sh
```

## 📊 Monitoring and Management

### Check Application Status

```bash
# Check if container is running
docker ps

# View application logs
docker logs vending-machine-api

# Follow logs in real-time
docker logs -f vending-machine-api

# Check app health
curl http://localhost:8000/status
```

### Container Management Commands

```bash
# Start the container
docker start vending-machine-api

# Stop the container
docker stop vending-machine-api

# Restart the container
docker restart vending-machine-api

# Remove the container
docker rm vending-machine-api

# View container resource usage
docker stats vending-machine-api
```

### System Monitoring

```bash
# Check system resources
htop

# Check disk usage
df -h

# Check memory usage
free -h

# Check Docker system usage
docker system df
```

## 🌐 Production Setup with Nginx (Optional)

For production, you may want to use Nginx as a reverse proxy:

### 1. Install Nginx

```bash
apt install -y nginx
```

### 2. Configure Nginx

```bash
cat > /etc/nginx/sites-available/vending-machine << 'EOF'
server {
    listen 80;
    server_name YOUR_DOMAIN.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Enable the site
ln -s /etc/nginx/sites-available/vending-machine /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default

# Test and restart Nginx
nginx -t
systemctl restart nginx
```

### 3. Setup SSL with Certbot (Optional)

```bash
# Install Certbot
apt install -y certbot python3-certbot-nginx

# Get SSL certificate
certbot --nginx -d YOUR_DOMAIN.com

# Auto-renewal (already set up by certbot)
```

## 🔒 Security Best Practices

### 1. Create Non-Root User

```bash
# Create app user
adduser appuser
usermod -aG docker appuser
usermod -aG sudo appuser

# Switch to app user for deployments
su - appuser
```

### 2. Setup SSH Key Authentication

```bash
# On your local machine, generate SSH key if you don't have one
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"

# Copy public key to server
ssh-copy-id root@YOUR_DROPLET_IP

# Disable password authentication (optional)
nano /etc/ssh/sshd_config
# Set: PasswordAuthentication no
systemctl restart sshd
```

### 3. Regular Updates

```bash
# Create auto-update script
cat > /etc/cron.weekly/system-update << 'EOF'
#!/bin/bash
apt update && apt upgrade -y
docker system prune -f
EOF

chmod +x /etc/cron.weekly/system-update
```

## 🐛 Troubleshooting

### Common Issues

1. **Port 8000 not accessible**
   ```bash
   # Check if firewall allows port 8000
   ufw status
   ufw allow 8000/tcp
   ```

2. **Container won't start**
   ```bash
   # Check container logs
   docker logs vending-machine-api
   
   # Check if .env file exists
   ls -la vm-py/.env
   ```

3. **Out of disk space**
   ```bash
   # Clean up Docker
   docker system prune -a
   
   # Remove old images
   docker image prune -a
   ```

4. **Memory issues**
   ```bash
   # Check memory usage
   free -h
   
   # Add swap if needed
   fallocate -l 2G /swapfile
   chmod 600 /swapfile
   mkswap /swapfile
   swapon /swapfile
   echo '/swapfile none swap sw 0 0' >> /etc/fstab
   ```

### Log Locations

- Application logs: `docker logs vending-machine-api`
- Nginx logs: `/var/log/nginx/`
- System logs: `/var/log/syslog`

## 🚀 Quick Start Commands

```bash
# Complete deployment in one go
ssh root@YOUR_DROPLET_IP << 'EOF'
cd /app/vending-machine/vm-py
docker stop vending-machine-api 2>/dev/null
docker rm vending-machine-api 2>/dev/null
./docker-build.sh
docker run -d --name vending-machine-api --restart unless-stopped -p 8000:8000 vending-machine-api
echo "✅ Deployment complete!"
curl -s http://localhost:8000/status
EOF
```

## 📝 Environment Variables

Make sure your `.env` file includes all required variables from `config.py`:

```env
# Example .env structure
BRIGHTDATA_API_KEY=your_key_here
BRIGHTDATA_API_ZONE=your_zone_here
GITHUB_USERNAME=your_username
GITHUB_TOKEN=your_token
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_key
# ... add all other required variables
```

---

## 🎉 Success!

Your FastAPI application should now be running at:
- **Direct access**: `http://YOUR_DROPLET_IP:8000`
- **With domain**: `http://YOUR_DOMAIN.com` (if using Nginx)

Check the status endpoint: `http://YOUR_DROPLET_IP:8000/status`
