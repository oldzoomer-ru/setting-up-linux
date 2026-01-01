{ config, pkgs, ... }:

{
  imports = [ ./hardware-configuration.nix ];

  # --- Основные параметры системы
  system.copySystemConfiguration = true;
  system.stateVersion = "24.11";

  # --- Загрузчик: UKI + systemd-boot (efistub через UKI)
  boot.loader = {
    systemd-boot.enable = true;
    efi.canTouchEfiVariables = true;
    efi.efiSysMountPoint = "/boot";
    timeout = 2;
  };

  # Включаем Unified Kernel Images (UKI)
  boot.kernelPackages = pkgs.linuxPackages_latest;
  boot.kernel.prepareUnifiedKernelImage = true;
  boot.kernel.unifiedKernelImage = {
    enable = true;
    bundles = [{
      name = "nixos";
      kernel = config.boot.kernelPackages.kernel;
      initrd = config.boot.initrd;
      cmdline = config.boot.kernelParams;
      osRelease = config.system.nixos.release;
    }];
  };

  # --- Параметры ядра
  boot.kernelParams = [
    "quiet"
    "loglevel=3"
    "rd.systemd.show_status=false"
    "rd.udev.log_level=3"
    "udev.log_priority=3"
  ];

  # --- Настройки dirty_* для корректного отображения прогресса записи на флешки/NVMe
  # Используем ratio вместо bytes — безопаснее и адаптивнее к объёму RAM
  boot.kernel.sysctl = {
    "vm.dirty_background_ratio" = 5;
    "vm.dirty_ratio" = 10;
    "vm.dirty_expire_centisecs" = 1000;
    "vm.dirty_writeback_centisecs" = 500;
  };

  boot.supportedFilesystems = [ "ntfs" ];
  boot.consoleLogLevel = 0;
  boot.initrd.verbose = false;
  boot.plymouth.enable = true;
  boot.tmp.useTmpfs = true;

  # --- ZRAM: 100% от RAM
  zramSwap.enable = true;
  zramSwap.memoryPercent = 100;
  zramSwap.algorithm = "zstd";  # эффективнее, чем lzo/lz4 при большом объёме

  networking.hostName = "oldzoomer-laptop";
  networking.networkmanager.enable = true;

  # Отключаем встроенный nftables-файрволл
  networking.firewall.enable = false;

  # Включаем firewalld
  services.firewalld.enable = true;

  # --- Системные сервисы
  services.fstrim.enable = true;

  # --- Nix
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 14d";
  };
  nix.settings.auto-optimise-store = true;

  # --- Управление памятью
  services.earlyoom.enable = true;
  services.earlyoom.memoryThreshold = 10;
  services.earlyoom.swapThreshold = 10;

  # --- X11 / GNOME
  services.xserver = {
    enable = true;
    displayManager.gdm.enable = true;
    desktopManager.gnome.enable = true;
    xkb = {
      layout = "us,ru";
      options = "grp:caps_toggle";
    };
  };

  # --- Pipewire
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
    # Bluetooth A2DP/HFP
    media-session.enable = true;
  };

  # --- Bluetooth
  hardware.bluetooth.enable = true;

  # --- Дополнительные сервисы
  services.flatpak.enable = true;
  services.printing.enable = true;

  # --- Docker
  virtualisation.docker.enable = true;

  # --- Локаль и часы
  time.timeZone = "Europe/Moscow";
  i18n.defaultLocale = "en_US.UTF-8";

  # --- Пользователь
  users.users.oldzoomer = {
    isNormalUser = true;
    description = "Egor Gavrilov";
    extraGroups = [ "wheel" "networkmanager" "docker" "audio" "video" ];
  };

  # --- Переменные окружения
  environment.variables = {
    EDITOR = "nano";
    VISUAL = "nano";
    XDG_CURRENT_DESKTOP = "GNOME";
  };

  # --- Пакеты
  nixpkgs.config.allowUnfree = true;

  environment.systemPackages = with pkgs; [
    wget htop tree efibootmgr git gnupg curl file docker-compose
  ];

  # --- Исключение GNOME-приложений
  environment.gnome.excludePackages = with pkgs; [
    gnome-maps gnome-contacts geary gnome-calendar
    gnome-characters gnome-connections gnome-tour epiphany
    simple-scan gnome-music snapshot file-roller gnome-font-viewer
  ];

  # --- GNOME-интеграция
  services.gnome.gnome-browser-connector.enable = true;
  programs.dconf.enable = true;
}