#!/bin/bash -eu

if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi

FILE="/etc/systemd/journald.conf"
CONFIG_HEADER="[Journal]"

if ! grep -Fxq "$CONFIG_HEADER" $FILE
then
    echo "$CONFIG_HEADER" >> $FILE
fi

echo "SystemMaxUse=50M" >> $FILE
systemctl restart systemd-journald.service

# snap remove --purge snap-store
apt install -y flatpak
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
apt install -y gnome-software-plugin-flatpak gnome-software
apt install -y ubuntu-restricted-extras
# wget -P /tmp https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
# apt install -y /tmp/google-chrome-stable_current_amd64.deb
# rm /tmp/google-chrome-stable_current_amd64.deb
