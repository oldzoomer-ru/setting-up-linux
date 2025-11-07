{ config, pkgs, ... }:

{
  imports = [ ./hardware-configuration.nix ];

  system.copySystemConfiguration = true;
  system.stateVersion = "24.11";

  boot.loader = {
    systemd-boot.enable = true;
    efi.canTouchEfiVariables = true;
    timeout = 2;
  };

  boot.kernelParams = [
    "quiet"
    "splash"
    "loglevel=3"
    "rd.systemd.show_status=false"
    "rd.udev.log_level=3"
    "udev.log_priority=3"
  ];

  boot.kernel.sysctl = {
    "vm.dirty_bytes" = 2097152;
    "vm.dirty_background_bytes" = 2097152;
  };

  boot.supportedFilesystems = [ "ntfs" ];

  boot.consoleLogLevel = 0;
  boot.initrd.verbose = false;
  boot.plymouth.enable = true;
  boot.tmp.useTmpfs = true;
  boot.extraModprobeConfig = "options rtw88_core disable_lps_deep=y";

  services.fstrim.enable = true;

  networking.hostName = "oldzoomer-laptop";
  networking.networkmanager.enable = true;
  networking.firewall.enable = false;

  zramSwap.enable = true;

  nix.gc.automatic = true;
  nix.settings.auto-optimise-store = true;

  services.earlyoom.enable = true;
  services.journald.extraConfig = "SystemMaxUse=50M";

  services.xserver = {
    enable = true;
    desktopManager.gnome.enable = true;
    displayManager.gdm.enable = true;
    xkb = {
      layout = "us,ru";
      options = "grp:caps_toggle";
    };
  };

  services.pipewire = {
    enable = true;
    pulse.enable = true;
    alsa.enable = true;
  };
  services.flatpak.enable = true;
  services.printing.enable = true;

  virtualisation.docker.enable = true;

  time.timeZone = "Europe/Moscow";
  i18n.defaultLocale = "ru_RU.UTF-8";
  console = {
    font = "cyr-sun16";
    useXkbConfig = true;
  };

  users.users.oldzoomer = {
    isNormalUser = true;
    extraGroups = [ "wheel" "networkmanager" "docker" ];
  };

  environment.variables = {
    EDITOR = "nano";
    VISUAL = "nano";
  };

  nixpkgs.config.allowUnfree = true;
  environment.systemPackages = with pkgs; [
    wget htop tree efibootmgr
    nano docker-compose git
    gnomeExtensions.gsconnect
    gnomeExtensions.vitals
    gnomeExtensions.appindicator
    gnomeExtensions.bing-wallpaper-changer
  ];

  environment.gnome.excludePackages = with pkgs; [
    gnome-maps gnome-contacts geary gnome-calendar
    gnome-characters gnome-connections gnome-tour epiphany
    simple-scan gnome-music snapshot file-roller gnome-font-viewer
  ];

  services.gnome.gnome-browser-connector.enable = true;
  programs.dconf.enable = true;
}
