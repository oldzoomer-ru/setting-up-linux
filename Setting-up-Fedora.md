# Гайд по настройке Fedora

## Самое необходимое

### Сброс MOK в UEFI

```shell
sudo mokutil --reset
```

### Удаление старых ядер

```shell
sudo dnf remove $(dnf rq --installonly --latest-limit=-1)
```

## Менее необходимые программы

### Snap

```shell
sudo dnf install snapd
sudo ln -s /var/lib/snapd/snap /snap
# Ребут...
sudo snap install hello-world
hello-world
```

### VLC

```shell
sudo dnf install vlc
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

#### Virt-Manager

```shell
sudo dnf install virt-manager
sudo usermod -aG libvirt $USER
```

#### VirtualBox

```shell
sudo dnf install dkms
```

Потом (если включён Secure Boot):

```shell
sudo mkdir -p /var/lib/shim-signed/mok
sudo openssl req -nodes -new -x509 -newkey rsa:2048 -outform DER -addext "extendedKeyUsage=codeSigning" -keyout /var/lib/shim-signed/mok/MOK.priv -out /var/lib/shim-signed/mok/MOK.der
sudo mokutil --import /var/lib/shim-signed/mok/MOK.der
```

Дальше читаем это: <https://github.com/dell/dkms?tab=readme-ov-file#module-signing>

Дальше ребутимся.

Потом ставим VBox по данному гайду: <https://www.virtualbox.org/wiki/Linux_Downloads>

И после установки вызываем эту команду:

```shell
sudo usermod -aG vboxusers $USER
```

И ребутимся опять.

### Разработка

#### XAMPP (если вам не хочется Docker'а)

Ставим зависимости:

```shell
sudo dnf install libnsl libxcrypt-compat
```

Далее качаем XAMPP с официального сайта (<https://www.apachefriends.org/ru/index.html>),
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
