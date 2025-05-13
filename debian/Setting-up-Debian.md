# Гайд по настройке Debian

## Самое необходимое

### Сброс MOK в UEFI

```shell
sudo mokutil --reset
```

## Менее необходимые программы

### WireGuard

```shell
sudo -i
apt install wireguard
cd /etc/wireguard/
umask 077; wg genkey | tee privatekey | wg pubkey > publickey
nano wg0.conf
systemctl start wg-quick@wg0
systemctl enable wg-quick@wg0
ip a show wg0
```

### Snap

```shell
sudo apt install snapd
# Ребут...
sudo snap install snapd
sudo snap install hello-world
hello-world
```

### VLC

```shell
flatpak install flathub org.videolan.VLC
```

### Создание видео

#### OBS Studio

```shell
flatpak install flathub com.obsproject.Studio
```

#### Kdenlive

```shell
flatpak install flathub org.kde.kdenlive
```

#### Audacity

```shell
flatpak install flathub org.audacityteam.Audacity
```

### Мессенджеры

#### Discord

```shell
flatpak install flathub com.discordapp.Discord
```

### Виртуализация

#### Docker

```shell
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
```

#### VirtualBox

Сначала ставим DKMS:

```shell
sudo apt install dkms
```

Потом (если включён Secure Boot):

```shell
sudo mkdir -p /var/lib/shim-signed/mok
sudo openssl req -nodes -new -x509 -newkey rsa:2048 -outform DER -addext "extendedKeyUsage=codeSigning" -keyout /var/lib/shim-signed/mok/MOK.priv -out /var/lib/shim-signed/mok/MOK.der
sudo mokutil --import /var/lib/shim-signed/mok/MOK.der
```

Дальше читаем это: <https://github.com/dell/dkms?tab=readme-ov-file#module-signing>

И ребутимся.

Потом ставим VBox по данному гайду: <https://www.virtualbox.org/wiki/Linux_Downloads>

И после установки вызываем эту команду:

```shell
sudo usermod -aG vboxusers $USER
```

И ребутимся опять.

### Разработка

#### DBeaver

```shell
flatpak install flathub io.dbeaver.DBeaverCommunity
```

##### XAMPP (если вам не хочется Docker'а)

Качаем XAMPP с официального сайта (<https://www.apachefriends.org/ru/index.html>),
и устанавливаем его:

```shell
chmod 755 xampp-linux-*-installer.run
sudo ./xampp-linux-*-installer.run
```

И запускаем:

```shell
sudo /opt/lampp/lampp start
```

Остановка:

```shell
sudo /opt/lampp/lampp stop
```

Для удобной работы с ним, делаем следующие команды:

```shell
cd /opt/lampp
sudo chown $USER:$USER htdocs
chmod 775 htdocs
cd
ln -s /opt/lampp/htdocs/ ~/htdocs
```

#### Node.js

<https://nodejs.org/en/download/package-manager>

### Загрузка файлов

#### Uget

```shell
flatpak install flathub com.ugetdm.uGet
```

#### Transmission

```shell
flatpak install flathub com.transmissionbt.Transmission
```
