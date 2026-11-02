#!/bin/bash
set -eu
# ============================================================
# Установка инструментов разработки:
#   1) Podman + Podman Compose      (через пакетный менеджер)
#   2) GraalVM                      (через SDKMAN!)
#   3) Node.js LTS + npm            (через nvm)
#
# Поддерживаемые дистрибутивы: Debian/Ubuntu (apt), Fedora (dnf),
# RHEL/CentOS (yum), Arch (pacman).
# SDKMAN! и nvm ставятся в домашний каталог текущего пользователя,
# поэтому системные пакеты устанавливаются через sudo (если не root).
# ============================================================

# --- определение пакетного менеджера ---
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

# sudo нужен только для системных пакетов
if [ "$EUID" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

install_pkgs() {
  case "$PKG_MGR" in
    apt)  $SUDO apt-get update && $SUDO apt-get install -y "$@" ;;
    dnf)  $SUDO dnf install -y "$@" ;;
    yum)  $SUDO yum install -y "$@" ;;
    pacman) $SUDO pacman -Sy --noconfirm "$@" ;;
  esac
}

echo ">>> Пакетный менеджер: $PKG_MGR"

# ============================================================
# 1. Podman и Podman Compose (строго из репозиториев дистрибутива)
# ============================================================
install_podman() {
  echo "=== Установка Podman и Podman Compose ==="

  case "$PKG_MGR" in
    apt)  install_pkgs podman podman-compose ;;
    dnf)  install_pkgs podman podman-compose ;;
    yum)  install_pkgs podman podman-compose ;;
    pacman) install_pkgs podman podman-compose ;;
  esac

  echo "Podman:        $(podman --version 2>/dev/null || echo 'не найден')"
  echo "Podman Compose: $(podman-compose --version 2>/dev/null || echo 'не найден')"
}

# ============================================================
# 2. uv (официальный инсталлятор Astral)
# ============================================================
install_uv() {
  echo "=== Установка uv ==="

  if command -v uv >/dev/null 2>&1; then
    echo "uv уже установлен"
  else
    echo "Установка uv ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi

  export PATH="$HOME/.local/bin:$PATH"
  echo "uv: $(uv --version 2>/dev/null || echo 'не найден')"
}

# ============================================================
# 3. GraalVM через SDKMAN!
# ============================================================
install_graalvm() {
  echo "=== Установка GraalVM (SDKMAN!) ==="

  if [ ! -s "$HOME/.sdkman/bin/sdkman-init.sh" ]; then
    echo "Установка SDKMAN! ..."
    curl -s "https://get.sdkman.io" | bash
  else
    echo "SDKMAN! уже установлен"
  fi

  # shellcheck source=/dev/null
  source "$HOME/.sdkman/bin/sdkman-init.sh"

  echo "Установка GraalVM ..."
  sdk install java 25-graal
  sdk default java 25-graal 2>/dev/null || true

  echo "Java: $(java -version 2>&1 | head -1 2>/dev/null || echo 'не найден')"
}

# ============================================================
# 4. Node.js через nvm
# ============================================================
install_nodejs() {
  echo "=== Установка Node.js (nvm) ==="

  if [ ! -s "$HOME/.nvm/nvm.sh" ]; then
    echo "Установка nvm ..."
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
  else
    echo "nvm уже установлен"
  fi

  # shellcheck source=/dev/null
  source "$HOME/.nvm/nvm.sh"

  echo "Установка Node.js LTS ..."
  nvm install --lts
  nvm alias default 'lts/*' 2>/dev/null || true
  nvm use --lts 2>/dev/null || true

  echo "Node.js: $(node -v 2>/dev/null || echo 'не найден')"
  echo "npm:     $(npm -v 2>/dev/null || echo 'не найден')"
}

# ============================================================
# Выполнение
# ============================================================
install_podman
install_uv
install_graalvm
install_nodejs

echo ""
echo "============================================================"
echo "Готово. Установлено:"
echo "  - Podman + Podman Compose (из репозиториев дистрибутива)"
echo "  - uv"
echo "  - GraalVM (SDKMAN!)"
echo "  - Node.js LTS + npm (nvm)"
echo ""
echo "Примечание: SDKMAN! и nvm добавили инициализацию в ~/.bashrc / ~/.profile."
echo "Чтобы инструменты были доступны в новых сессиях, перезапустите оболочку"
echo "или выполните: source ~/.bashrc"
echo "============================================================"
