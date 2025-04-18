#!/bin/bash -eu

if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi

# Для Realtek RTL8821CE
echo "options rtw88_core disable_lps_deep=y" >> /etc/modprobe.d/rtw88.conf

FILE="/etc/dnf/dnf.conf"

echo "max_parallel_downloads=10" >> $FILE
echo "minrate=500k" >> $FILE
echo "timeout=10" >> $FILE

FILE="/etc/systemd/journald.conf"
CONFIG_HEADER="[Journal]"

if ! grep -Fxq "$CONFIG_HEADER" $FILE
then
    echo "$CONFIG_HEADER" >> $FILE
fi

echo "SystemMaxUse=50M" >> $FILE
systemctl restart systemd-journald.service

dnf install -y https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
dnf install rpmfusion-\*-appstream-data -y
dnf swap ffmpeg-free ffmpeg --allowerasing -y
dnf update @multimedia --setopt="install_weak_deps=False" --exclude=PackageKit-gstreamer-plugin -y
# dnf install mozilla-openh264 -y
dnf swap mesa-va-drivers mesa-va-drivers-freeworld -y
dnf swap mesa-vdpau-drivers mesa-vdpau-drivers-freeworld -y
dnf install gnome-tweaks seahorse -y
dnf install curl cabextract xorg-x11-font-utils fontconfig -y
rpm -i https://downloads.sourceforge.net/project/mscorefonts2/rpms/msttcore-fonts-installer-2.6-1.noarch.rpm
# dnf install nm-connection-editor-desktop -y
# dnf install fastfetch -y
# dnf install unrar p7zip p7zip-plugins -y
