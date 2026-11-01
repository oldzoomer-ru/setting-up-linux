# QUICKSTART.md - Fast Setup Guide

## One-Command Setup

```bash
# Clone the repository
git clone https://github.com/oldzoomer/setting-up-linux.git
cd setting-up-linux

# Make scripts executable
chmod +x setup-wrapper.sh

# Run setup (will detect distro and prompt for confirmation)
./setup-wrapper.sh
```

## First-Time Setup Options

### Dry Run (See What Would Happen)
```bash
./setup-wrapper.sh --dry-run
```

### With Custom Variables
```bash
NODEJS_VERSION=22.x JAVA_VERSION=21 ./setup-wrapper.sh
```

### Using Ansible Directly
```bash
cd config/ansible
ansible-playbook -i "localhost" initial-setup.yml -e "nodejs_version=22.x java_version=21"
```

## Configuration

All settings are in `config/setup.cfg`. Edit this file to customize:

- `NODEJS_VERSION` - Node.js version from NodeSource
- `JAVA_VERSION` - OpenJDK version
- `DEV_USER` - Your username (for docker group)
- `APT_ARCH` - Architecture (auto-detected)
- `ZRAM_SWAP_SIZE` - ZRAM swap size
- `GIGABYTE_LAPTOP` - Set to `true` for Gigabyte laptops

## Supported Distributions

| Distro | Family | Package Manager |
|--------|--------|-----------------|
| Ubuntu/Debian | debian | apt |
| Fedora/RHEL/CentOS | redhat | dnf/yum |
| Arch Linux | redhat | pacman |

## Post-Installation

After setup completes:

1. Log out and log back in (to apply docker group membership)
2. Verify installations:
   ```bash
   docker --version
   code --version
   node --version
   java -version
   ```
3. Check ZRAM status:
   ```bash
   cat /etc/systemd/zram-generator.conf
   systemctl status systemd-zram-setup@zram0.service
   ```

## Common Issues

### Docker Group Not Applied
- Log out and back in, or run: `newgrp docker`
- Or restart the terminal

### Flatpak Issues
- Ensure Flathub is added: `flatpak remote-list --system`
- Check masked packages: `flatpak list --system | grep oh264`

### Node.js Version Not Updated
- Run the NodeSource setup script manually
- Or override via: `NODEJS_VERSION=22.x ./setup-wrapper.sh`