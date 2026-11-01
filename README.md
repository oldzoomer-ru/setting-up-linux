# Setting-up-Linux
Personal Linux Desktop Setup Scripts and Configuration

This repository contains personal configurations and scripts for setting up a Linux desktop environment. It includes:

- Ansible roles for system configuration
- Autoinstall settings for unattended installs
- Distribution-specific guides (Arch, Debian, Fedora)
- AI/LLM FastAPI configuration

## Quick Start

### Prerequisites

- Python 3 + pip
- Ansible 2.10+
- Git

### Installation

```bash
git clone https://github.com/oldzoomer/setting-up-linux.git
cd setting-up-linux
chmod +x setup-wrapper.sh
./setup-wrapper.sh
```

### Configuration

All configurable variables are in `config/setup.cfg`. Override via environment variables or Ansible `-e` flags, eg: `NODEJS_VERSION=26.x ./setup-wrapper.sh`

## Components

### Ansible Roles

- `desktop` - GNOME settings, Flatpak, ZRAM
- `docker` - Docker CE installation and group management
- `extras` - Development tools (build-essential, jq)
- `vscode` - Visual Studio Code installation
- `java` - OpenJDK installation
- `nodejs` - Node.js setup from NodeSource
- `gigabyte` - Gigabyte laptop specific quirks

### Autoinstall

- `config/autoinstall/autoinstall.yaml` - Ubuntu autoinstall config
- `config/autoinstall/preseed.txt` - Debian preseed
- `config/autoinstall/configuration.nix` - NixOS config

### Setup Scripts

- `setup-wrapper.sh` - Universal distro-detecting wrapper

### AI/LLM

- `config/ai/main.py` - FastAPI LLM proxy
- `config/ai/models.ini` - Model configurations

## Supported Distributions

- Debian/Ubuntu (apt-based)
- Fedora/RHEL/CentOS (dnf/yum-based)
- Arch Linux (pacman-based)

## License

GPL-3.0-or-later