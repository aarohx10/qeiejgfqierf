#!/bin/bash

# Exit on error
set -e

# Function to handle errors
handle_error() {
    echo "Error occurred in deployment at line $1"
    echo "Check the logs at /var/log/sendora-voice/deployment.log"
    exit 1
}

trap 'handle_error $LINENO' ERR

# Check system requirements
echo "Checking system requirements..."
if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 
   exit 1
fi

# Create log directory
mkdir -p /var/log/sendora-voice
chown root:root /var/log/sendora-voice

# Setup logging
exec 1> >(tee -a "/var/log/sendora-voice/deployment.log")
exec 2>&1

# Check available memory
TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM" -lt 4000 ]; then
    echo "Warning: Less than 4GB of RAM available. The application might not perform optimally."
fi

# Check available disk space
FREE_DISK=$(df -m / | awk 'NR==2 {print $4}')
if [ "$FREE_DISK" -lt 10000 ]; then
    echo "Warning: Less than 10GB of free disk space available."
fi

# Check Python version
PYTHON_OK=$(python3 -c 'import sys; print(sys.version_info >= (3,8))')
if [ "$PYTHON_OK" != "True" ]; then
    echo "Error: Python 3.8 or higher is required"
    exit 1
fi

# Update system
echo "Updating system..."
apt update && apt upgrade -y

# Install required packages
echo "Installing required packages..."
apt install -y python3 python3-pip python3-venv nginx redis-server certbot python3-certbot-nginx

# Backup existing configuration if it exists
if [ -d "/opt/sendora-voice" ]; then
    echo "Backing up existing configuration..."
    BACKUP_DIR="/opt/sendora-voice_backup_$(date +%Y%m%d_%H%M%S)"
    mv /opt/sendora-voice "$BACKUP_DIR"
fi

# Create application directory
echo "Setting up application directory..."
mkdir -p /opt/sendora-voice
chown $SUDO_USER:$SUDO_USER /opt/sendora-voice
cd /opt/sendora-voice

# Create and activate virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Configure Redis
echo "Configuring Redis..."
REDIS_PASSWORD=$(openssl rand -base64 32)
sed -i "s/# requirepass foobared/requirepass $REDIS_PASSWORD/" /etc/redis/redis.conf
systemctl restart redis

# Setup Nginx
echo "Configuring Nginx..."
cp sendora-voice.nginx.conf /etc/nginx/sites-available/sendora-voice
ln -sf /etc/nginx/sites-available/sendora-voice /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

# Setup SSL
echo "Setting up SSL..."
read -p "Enter your email for SSL certificate: " EMAIL
certbot --nginx -d voice.sendora.ai --non-interactive --agree-tos --email "$EMAIL"

# Update service file with Redis password
sed -i "s/your_redis_password/$REDIS_PASSWORD/" sendora-voice.service

# Setup systemd service
echo "Setting up systemd service..."
cp sendora-voice.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable sendora-voice
systemctl start sendora-voice

# Verify services are running
echo "Verifying services..."
if ! systemctl is-active --quiet redis; then
    echo "Error: Redis is not running"
    exit 1
fi

if ! systemctl is-active --quiet nginx; then
    echo "Error: Nginx is not running"
    exit 1
fi

if ! systemctl is-active --quiet sendora-voice; then
    echo "Error: Sendora Voice service is not running"
    exit 1
fi

echo "Deployment completed successfully!"
echo "Redis password: $REDIS_PASSWORD"
echo "Check application status: systemctl status sendora-voice"
echo "View application logs: journalctl -u sendora-voice -f"
echo "View deployment logs: cat /var/log/sendora-voice/deployment.log" 