#!/bin/bash
set -e
# Простой универсальный скрипт настройки Gigabyte / AORUS ноутбука
# (прямой аналог ansible роли gigabyte/tasks/main.yml без особых проверок)

# ============================================================
# Определение пакетного менеджера
# ============================================================

if command -v apt-get >/dev/null 2>&1; then
  PKG_MGR="apt"
elif command -v dnf >/dev/null 2>&1; then
  PKG_MGR="dnf"
elif command -v yum >/dev/null 2>&1; then
  PKG_MGR="yum"
elif command -v pacman >/dev/null 2>&1; then
  PKG_MGR="pacman"
else
  echo "Неизвестный пакетный менеджер" >&2
  exit 1
fi

install_pkgs() {
  case "$PKG_MGR" in
    apt)  apt-get update && apt-get install -y "$@" ;;
    dnf)  dnf install -y "$@" ;;
    yum)  yum install -y "$@" ;;
    pacman) pacman -Sy --noconfirm "$@" ;;
  esac
}

# ============================================================
# 1. Конфигурация клавиатуры (hwdb-правило + keyd)
# ============================================================

cat > /etc/udev/hwdb.d/99-gigabyte.hwdb << 'EOF'
evdev:input:b0003v0414p8104e0111*
 KEYBOARD_KEY_7006f=fn
 KEYBOARD_KEY_70067=www
EOF

systemd-hwdb update
udevadm trigger

install_pkgs keyd

mkdir -p /etc/keyd

cat > /etc/keyd/default.conf << 'EOF'
[ids]
*

[main]
# Аккорд для Скриншота (на базе S, Shift, Meta)
s+leftshift+leftmeta = print

# Кнопка Copilot активирует слой для GoldED
f23+leftshift+leftmeta = layer(fido)

[fido]
i = insert
w = f2
EOF

systemctl restart keyd || true

# ============================================================
# 2. AORUS Laptop DKMS модуль и управление
# ============================================================

case "$PKG_MGR" in
  apt)  HEADERS_PKG="linux-headers-amd64" ;;
  dnf|yum) HEADERS_PKG="kernel-devel" ;;
  pacman) HEADERS_PKG="linux-headers" ;;
esac

install_pkgs dkms "$HEADERS_PKG"

curl -L -o /tmp/gigabyte-laptop-wmi.tar.gz \
  https://github.com/tangalbert919/gigabyte-laptop-wmi/tarball/master

tar -xzf /tmp/gigabyte-laptop-wmi.tar.gz -C /tmp/

sed -i 's/PACKAGE_VERSION=@PKGVER@/PACKAGE_VERSION="dev"/' \
  /tmp/tangalbert919-gigabyte-laptop-wmi/dkms.conf

tar -czf /tmp/dkms-aorus.tar.gz \
  -C /tmp/tangalbert919-gigabyte-laptop-wmi \
  Makefile aorus-laptop.c dkms.conf

dkms ldtarball /tmp/dkms-aorus.tar.gz

modprobe aorus-laptop

sh -c 'if [ -f /var/lib/dkms/mok.key ]; then
  cp /var/lib/dkms/mok.key /etc/ && cp /var/lib/dkms/mok.pub /etc/ &&
  echo "Existing MOK key found" || echo "No existing key"
else
  echo "No existing MOK key, will create new one"
fi'

cd /tmp && git clone https://github.com/vladkoisnych/aorus-laptop-control.git && \
  cd aorus-laptop-control && ./install.sh

systemctl enable --now aorusctl-web.service aorusctld.service aorusctl-profile.service

echo "Готово. Настройка Gigabyte / AORUS завершена."