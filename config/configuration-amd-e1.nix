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
  };

  services.journald.extraConfig = "SystemMaxUse=50M";

  zramSwap.enable = true;
  boot.kernel.sysctl = {
    "vm.swappiness" = 30;
    "vm.vfs_cache_pressure" = 500;
  };

  networking.hostName = "oldzoomer-laptop";
  networking.networkmanager.enable = true;
  time.timeZone = "Europe/Moscow";

  i18n.defaultLocale = "ru_RU.UTF-8";
  console = {
    font = "cyr-sun16";
    useXkbConfig = true;
  };

  services.xserver = {
    enable = true;
    desktopManager.lxde.enable = true;
    displayManager = {
      lightdm.enable = true;
      autoLogin = {
        enable = true;
        user = "oldzoomer";
      };
    };
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
  security.sudo.extraConfig = ''Defaults timestamp_timeout=30'';

  nix = {
    gc = {
      automatic = true;
      dates = "weekly";
      options = "--delete-older-than 7d";
    };
    settings.auto-optimize-store = true;
  };

  system.stateVersion = "24.11";
}
