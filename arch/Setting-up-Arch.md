# Настраиваем Arch...

## База

```shell
sudo pacman -S bash-completion tree less nano
```

## Настраиваем локаль

```shell
sudo localectl set-x11-keymap us,ru pc105+inet "" grp:caps_toggle
sudo bash -c 'echo "FONT=cyr-sun16" >> /etc/vconsole.conf'
```

## Настраиваем базовые шрифты

```shell
sudo pacman -S noto-fonts ttf-liberation noto-fonts-cjk noto-fonts-emoji
```

## Включаем нужные сервисы

```shell
sudo pacman -S bluez
sudo systemctl enable --now bluetooth.service
```

## Устанавливаем yay

```shell
sudo pacman -S git && git clone https://aur.archlinux.org/yay-bin.git && cd yay-bin && makepkg -si
```

## MS Fonts

```shell
yay -S ttf-ms-fonts
```

## systemd-resolved

<https://wiki.archlinux.org/title/Systemd-resolved>

## Plymouth

<https://wiki.archlinux.org/title/Plymouth>

## Avahi

<https://wiki.archlinux.org/title/Avahi>

## CUPS

<https://wiki.archlinux.org/title/CUPS>

## Flatpak

<https://wiki.archlinux.org/title/Flatpak>
