#!/bin/bash -eu

if [ "$(id -u)" -eq 0 ]; then
        echo 'This script must NOT be run by root' >&2
        exit 1
fi

# Укажите реальные данные через переменные
git config --global user.name "$REALNAME"
git config --global user.email "$EMAIL"

sudo apt-get install wget gpg -y
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /tmp/packages.microsoft.gpg
sudo install -D -o root -g root -m 644 /tmp/packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" |sudo tee /etc/apt/sources.list.d/vscode.list > /dev/null
rm -f /tmp/packages.microsoft.gpg

sudo apt install apt-transport-https -y
sudo apt update
sudo apt install code -y