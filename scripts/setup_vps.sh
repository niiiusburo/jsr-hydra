#!/bin/bash
# ════════════════════════════════════════════════════════════════
# JSR HYDRA — VPS SETUP SCRIPT
# ════════════════════════════════════════════════════════════════
#
# Run this on your VPS after SSH'ing in:
#   ssh root@160.187.240.251
#   (password: your VPS password)
#   bash setup_vps.sh
#
# This script:
#   1. Cleans the VPS completely
#   2. Updates Ubuntu
#   3. Installs Docker + Docker Compose
#   4. Installs Git, Python 3.11, Node.js 20
#   5. Sets up firewall
#   6. Creates project directory
#   7. Sets up SSH key for GitHub
#   8. Ready for code deployment
#
# Time: ~10-15 minutes
# ════════════════════════════════════════════════════════════════

set -e  # Stop on any error

echo "════════════════════════════════════════════"
echo "  JSR HYDRA — VPS SETUP v1.0.0"
echo "════════════════════════════════════════════"
echo ""

# ──────────────────────────────────────
# STEP 1: CLEAN EVERYTHING
# ──────────────────────────────────────
echo "[1/9] Cleaning VPS..."

# Stop all running containers if Docker exists
if command -v docker &> /dev/null; then
    docker stop $(docker ps -aq) 2>/dev/null || true
    docker rm $(docker ps -aq) 2>/dev/null || true
    docker system prune -af --volumes 2>/dev/null || true
fi

# Remove old project files (if any)
rm -rf /opt/jsr-hydra 2>/dev/null || true
rm -rf /root/jsr-hydra 2>/dev/null || true

echo "Done"

# ──────────────────────────────────────
# STEP 2: UPDATE SYSTEM
# ──────────────────────────────────────
echo "[2/9] Updating system..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get autoremove -y -qq

echo "Done"

# ──────────────────────────────────────
# STEP 3: INSTALL ESSENTIALS
# ──────────────────────────────────────
echo "[3/9] Installing essentials..."

apt-get install -y -qq \
    curl \
    wget \
    git \
    vim \
    htop \
    tmux \
    unzip \
    jq \
    ufw \
    fail2ban \
    build-essential \
    libpq-dev \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common

echo "Done"

# ──────────────────────────────────────
# STEP 4: INSTALL DOCKER
# ──────────────────────────────────────
echo "[4/9] Installing Docker..."

# Remove old Docker versions
apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# Add Docker GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker
systemctl enable docker
systemctl start docker

# Verify
docker --version
docker compose version

echo "Done"

# ──────────────────────────────────────
# STEP 5: INSTALL PYTHON 3.11
# ──────────────────────────────────────
echo "[5/9] Installing Python 3.11..."

add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv python3.11-dev python3-pip

# Make python3.11 the default
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 2>/dev/null || true

python3.11 --version

echo "Done"

# ──────────────────────────────────────
# STEP 6: INSTALL NODE.JS 20
# ──────────────────────────────────────
echo "[6/9] Installing Node.js 20..."

curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y -qq nodejs

node --version
npm --version

echo "Done"

# ──────────────────────────────────────
# STEP 7: FIREWALL SETUP
# ──────────────────────────────────────
echo "[7/9] Configuring firewall..."

ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# SSH
ufw allow 22/tcp

# HTTP/HTTPS (for dashboard via Caddy)
ufw allow 80/tcp
ufw allow 443/tcp

# FastAPI (dev access — remove in production)
ufw allow 8000/tcp

# Next.js (dev access — remove in production)
ufw allow 3000/tcp

# VNC for MT5 (restrict to your IP later)
ufw allow 5900/tcp

ufw --force enable

echo "Done"

# ──────────────────────────────────────
# STEP 8: CREATE PROJECT DIRECTORY
# ──────────────────────────────────────
echo "[8/9] Creating project directory..."

mkdir -p /opt/jsr-hydra
mkdir -p /opt/jsr-hydra/backups

echo "Done"

# ──────────────────────────────────────
# STEP 9: SETUP GIT + SSH KEY
# ──────────────────────────────────────
echo "[9/9] Setting up Git..."

# Generate SSH key for GitHub (if not exists)
if [ ! -f /root/.ssh/id_ed25519 ]; then
    ssh-keygen -t ed25519 -C "jsr-hydra-vps" -f /root/.ssh/id_ed25519 -N ""
    echo ""
    echo "════════════════════════════════════════════"
    echo "  ADD THIS SSH KEY TO YOUR GITHUB ACCOUNT:"
    echo "════════════════════════════════════════════"
    echo ""
    cat /root/.ssh/id_ed25519.pub
    echo ""
    echo "Go to: https://github.com/settings/ssh/new"
    echo "════════════════════════════════════════════"
fi

echo "Done"

# ──────────────────────────────────────
# DONE
# ──────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════"
echo "  JSR HYDRA VPS SETUP COMPLETE"
echo "════════════════════════════════════════════════════════"
echo ""
echo "  VPS:       160.187.240.251"
echo "  Project:   /opt/jsr-hydra"
echo "  Python:    $(python3.11 --version 2>&1)"
echo "  Node:      $(node --version 2>&1)"
echo "  Docker:    $(docker --version 2>&1)"
echo "  Compose:   $(docker compose version 2>&1)"
echo ""
echo "  NEXT STEPS:"
echo "  1. Add the SSH key above to GitHub"
echo "  2. Create repo: github.com/YOUR_USER/jsr-hydra"
echo "  3. Push code from your Mac:"
echo "     cd jsr-hydra && git init && git add -A"
echo "     git commit -m 'feat: JSR Hydra v1.0.0'"
echo "     git remote add origin git@github.com:YOUR_USER/jsr-hydra.git"
echo "     git push -u origin main"
echo "  4. On VPS: cd /opt/jsr-hydra"
echo "     git clone git@github.com:YOUR_USER/jsr-hydra.git ."
echo "     cp .env.example .env && vim .env  # fill credentials"
echo "     make deploy"
echo ""
echo "  SYSTEM INFO:"
echo "  RAM: $(free -h | awk '/^Mem:/ {print $2}')"
echo "  CPU: $(nproc) cores"
echo "  Disk: $(df -h / | awk 'NR==2 {print $4}') free"
echo ""
echo "  SECURITY REMINDERS:"
echo "  - Change the .env passwords before going live"
echo "  - Set DRY_RUN=true (already set) for paper trading first"
echo "  - Update MT5 credentials in .env"
echo "  - Update Telegram bot token in .env"
echo "════════════════════════════════════════════════════════"
