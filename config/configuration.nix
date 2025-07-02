{ config, pkgs, ... }:

{
  imports = [ ./hardware-configuration.nix ];

  system.autoUpgrade.enable = true;
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

  boot.consoleLogLevel = 0;
  boot.initrd.verbose = false;
  boot.plymouth.enable = true;
  boot.tmp.useTmpfs = true;
  boot.extraModprobeConfig = "options rtw88_core disable_lps_deep=y";

  services.fstrim.enable = true;

  networking.hostName = "oldzoomer-laptop";
  networking.networkmanager.enable = true;
  networking.firewall = {
    allowedTCPPortRanges = [{ from = 1714; to = 1764; }];
    allowedUDPPortRanges = [{ from = 1714; to = 1764; }];
    allowPing = false;
  };

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

  services.tlp.enable = true;
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
  
  security.sudo.extraConfig = ''
    Defaults editor=${pkgs.nano}/bin/nano
  '';

  nixpkgs.config.allowUnfree = true;
  environment.systemPackages = with pkgs; [
    wget htop tree efibootmgr nano
    docker-compose google-chrome
    gnomeExtensions.gsconnect
    gnomeExtensions.vitals
    gnomeExtensions.appindicator
    gnomeExtensions.bing-wallpaper-changer
  ];

  environment.gnome.excludePackages = with pkgs; [
    gnome-maps gnome-contacts geary gnome-calendar
    gnome-characters gnome-connections gnome-tour epiphany
  ];

  services.gnome.gnome-browser-connector.enable = true;
  programs.dconf.enable = true;

  dconf.settings = {
    "org/gnome/shell" = {
      enabled-extensions = [
        "gsconnect@andyholmes.github.io"
        "Vitals@CoreCoding.com"
        "appindicatorsupport@rgcjonas.gmail.com"
        "BingWallpaper@ineffable-gmail.com"
      ];
    };
    
    "org/gnome/shell/extensions/bingwallpaper" = {
      country = "ru";
      change-interval = "hourly";
    };
    
    "org/gnome/shell/extensions/vitals" = {
      show-storage = true;
      show-voltage = false;
      show-network = true;
      show-temperature = true;
      show-memory = true;
      show-processor = true;
    };
  };
}