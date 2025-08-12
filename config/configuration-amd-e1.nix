{ config, lib, pkgs, ... }:

{
  imports = [ ./hardware-configuration.nix ];

  boot = {
    loader = {
      systemd-boot.enable = true;
      efi.canTouchEfiVariables = true;
    };
    tmp.useTmpfs = true;
    consoleLogLevel = 0;
    initrd.verbose = false;
    kernelParams = [
      "quiet"
      "splash"
      "loglevel=3"
      "nowatchdog"
      "zswap.enabled=1"
      "zswap.compressor=lz4"
      "zswap.max_pool_percent=20"
    ];
    kernel.sysctl = {
      "vm.dirty_bytes" = 2097152;
      "vm.dirty_background_bytes" = 2097152;
    };
    supportedFilesystems = [ "ntfs" ];
  };

  services.journald.extraConfig = "SystemMaxUse=50M";

  zramSwap.enable = true;

  networking.hostName = "oldzoomer-laptop";
  networking.networkmanager.enable = true;
  networking.firewall.enable = false;

  time.timeZone = "Europe/Moscow";

  i18n.defaultLocale = "ru_RU.UTF-8";
  console = {
    font = "cyr-sun16";
    useXkbConfig = true;
  };

  services.xserver = {
    enable = true;
    desktopManager.lxde.enable = true;
    displayManager.lightdm.enable = true;
    windowManager.openbox.enable = true;
    xkb.layout = "us,ru";
    xkb.options = "grp:caps_toggle";
  };

  environment.systemPackages = with pkgs; [
    tree
    less
    efibootmgr
    firefox
    libreoffice-fresh
    remmina
    pcmanfm
    xarchiver
    qpdfview
    mpv
    htop
  ];

  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    pulse.enable = true;
    alsa.enable = true;
  };

  users.users.oldzoomer = {
    isNormalUser = true;
    extraGroups = ["wheel" "networkmanager"];
  };

  nixpkgs.config.allowUnfree = true;

  nix = {
    gc.automatic = true;
    settings.auto-optimize-store = true;
  };

  system.stateVersion = "24.11";
}
