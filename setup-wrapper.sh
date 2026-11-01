## Detect distribution
detect_distro() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        DISTRO=$ID
        DISTRO_VERSION=$VERSION_ID
    elif [[ -f /etc/arch-release ]]; then
        DISTRO="arch"
        DISTRO_VERSION="rolling"
    else
        DISTRO="unknown"
        DISTRO_VERSION="unknown"
    fi
    case "$DISTRO" in
        ubuntu|debian) DISTRO_FAMILY="debian" ;;
        fedora|rhel|centos) DISTRO_FAMILY="redhat" ;;
        arch) DISTRO_FAMILY="redhat" ;;
        *) DISTRO_FAMILY="unknown" ;;
    esac
}

## Show info
show_info() {
    echo ""
    echo "========================================"
    echo "  Linux Setup Wrapper"
    echo "========================================"
    detect_distro
    echo "Config: $CONFIG_DIR/setup.cfg"
    echo "Playbook: $PLAYBOOK"
    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        echo "GitHub token: detected (will inject settings from GitHub)"
    fi
    echo ""
}

## Check prerequisites
check_prerequisites() {
    if ! command -v ansible-playbook &>/dev/null; then
        echo "WARNING: ansible-playbook not found"
    fi
    if ! command -v git &>/dev/null; then
        echo "ERROR: Git is required"
        exit 1
    fi
}

## Main
show_info
check_prerequisites

if [[ "$1" == "--dry-run" ]]; then
    echo "Dry run mode - would execute: ansible-playbook -i localhost $PLAYBOOK"
    exit 0
fi

read -p "Proceed with setup? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    ansible-playbook -i "localhost" "$PLAYBOOK" "$@"
fi