#!/usr/bin/env bash
# First-boot initialization script
# Injects data from the GitHub repo (public access, no token needed)
# Updates config/setup.cfg from the repository

set -euo pipefail

CONFIG_DIR="/tmp/setting-up-linux/config"
PLAYBOOK="${CONFIG_DIR}/ansible/initial-setup.yml"
GIT_REPO="https://github.com/oldzoomer/setting-up-linux.git"
GIT_DIR="${CONFIG_DIR}/.."

echo "=== First-boot setup starting ==="

# Step 1: Ensure the git repo is cloned and up-to-date
if [[ -d "${GIT_DIR}/.git" ]]; then
    echo "Git repo already present, updating..."
    cd "${GIT_DIR}" && git pull --quiet 2>/dev/null || echo "Warning: git pull failed, using existing files"
else
    echo "Cloning git repo (public access, no token needed)..."
    git clone --quiet "${GIT_REPO}" "${GIT_DIR}" 2>/dev/null || {
        echo "Warning: git clone failed, using local configuration"
        GIT_DIR=""
    }
fi

# Step 2: Inject config/setup.cfg from the repo if available
if [[ -n "${GIT_DIR}" && -f "${GIT_DIR}/config/setup.cfg" ]]; then
    echo "Injecting config/setup.cfg from repository..."
    cp -f "${GIT_DIR}/config/setup.cfg" "${CONFIG_DIR}/setup.cfg"
    echo "Configuration updated from repository"
elif [[ -f "${CONFIG_DIR}/setup.cfg" ]]; then
    echo "Using local config/setup.cfg (no repository update needed)"
fi

# Step 3: Detect distribution and set environment variables
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    DISTRO=$ID
    DISTRO_VERSION=$VERSION_ID
else
    DISTRO="unknown"
    DISTRO_VERSION="unknown"
fi

# Step 4: Export variables for Ansible
export NODEJS_VERSION="${NODEJS_VERSION:-26.x}"
export JAVA_VERSION="${JAVA_VERSION:-25}"
export DEV_USER="${DEV_USER:-$USER}"
export APT_ARCH="${APT_ARCH:-$(uname -m)}"

case "$APT_ARCH" in
    x86_64) APT_ARCH="amd64" ;;
    aarch64) APT_ARCH="arm64" ;;
    *) APT_ARCH="amd64" ;;
esac

# Step 5: Run Ansible playbook
echo "Running Ansible setup playbook..."
if ansible-playbook -i "localhost" "$PLAYBOOK" "$@"; then
    echo ""
    echo "=== Setup completed successfully! ==="
    echo "Please log out and log back in for group membership changes to take effect."
else
    echo ""
    echo "=== Setup finished with errors ==="
    exit 1
fi