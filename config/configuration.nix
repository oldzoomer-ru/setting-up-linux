{ config, pkgs, ... }:

{
  imports = [ ./hardware-configuration.nix ];

  # --- Основные параметры системы
  system.copySystemConfiguration = true;
  system.stateVersion = "24.11";

  # --- Загрузчик: systemd-boot
  boot.loader = {
    systemd-boot.enable = true;
    efi.canTouchEfiVariables = true;
    efi.efiSysMountPoint = "/boot";
    timeout = 2;
  };
  boot.kernelPackages = pkgs.linuxPackages;

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

  # --- Системные сервисы
  services.fstrim.enable = true;

  # --- Nix
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 14d";
  };
  nix.settings.auto-optimise-store = true;

  # --- X11 / GNOME
  hardware.graphics.enable = true;

  services.xserver = {
    enable = true;
    videoDrivers = ["nvidia"];
    xkb = {
      layout = "us,ru";
      options = "grp:caps_toggle";
    };
  };

  services.displayManager.gdm.enable = true;
  services.desktopManager.gnome.enable = true;

  hardware.nvidia = {
    modesetting.enable = true;
    powerManagement.enable = true;
    powerManagement.finegrained = true;

    prime = {
      offload = {
        enable = true;
        enableOffloadCmd = true;
      };

      nvidiaBusId = "PCI:1:0:0";
      amdgpuBusId = "PCI:101:0:0"; # 65 в hex (lspci) = 101 в dec (Xorg)
    };

    open = true;
    nvidiaSettings = true;
    package = config.boot.kernelPackages.nvidiaPackages.stable;
  };

  services.switcherooControl.enable = true;

  # --- Pipewire
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
    # Bluetooth A2DP/HFP
    wireplumber.enable = true;
  };

  # --- Bluetooth
  hardware.bluetooth.enable = true;

  # --- Дополнительные сервисы
  services.flatpak.enable = true;
  services.printing.enable = true;

  virtualisation.podman = {
    enable = true;
    dockerCompat = true;
  };

  virtualisation.libvirtd.enable = true;
  programs.virt-manager.enable = true;
  virtualisation.libvirtd.qemu.swtpm.enable = true;

  # --- Локаль и часы
  time.timeZone = "Europe/Moscow";
  i18n.defaultLocale = "ru_RU.UTF-8";

  # --- Пользователь
  users.users.oldzoomer = {
    isNormalUser = true;
    description = "Егор Гаврилов";
    extraGroups = [ "wheel" "networkmanager" "audio" "video" "libvirtd" ];
  };

  # --- Переменные окружения
  environment.variables = {
    EDITOR = "nano";
    VISUAL = "nano";
  };

  # --- Пакеты
  nixpkgs.config.allowUnfree = true;

  environment.systemPackages = with pkgs; [
    tree efibootmgr curl pciutils git
    distrobox dnsmasq bridge-utils
  ];

  # --- Исключение GNOME-приложений
  environment.gnome.excludePackages = with pkgs; [
    gnome-maps gnome-connections gnome-tour
    epiphany simple-scan file-roller
  ];

  # --- GNOME-интеграция
  services.gnome.gnome-browser-connector.enable = true;
}
