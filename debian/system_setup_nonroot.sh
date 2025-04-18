#!/bin/bash -eu

if [ "$(id -u)" -eq 0 ]; then
        echo 'This script must NOT be run by root' >&2
        exit 1
fi

flatpak install flathub com.github.tchx84.Flatseal -y
flatpak install flathub org.telegram.desktop -y
flatpak install flathub org.keepassxc.KeePassXC -y

sudo usermod -aG systemd-journal $USER
