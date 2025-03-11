# Гайд по настройке Fedora

## Самое необходимое

### Первоначальная настройка системы

Используйте скрипт `system_setup.sh` и `system_setup_nonroot.sh`.

Также можно установить расширения для GNOME: <https://extensions.gnome.org/>.

### Настройка swapfile в BTRFS

```shell
sudo btrfs subvolume create /swap
cd /swap
# При >=8 гигах ОЗУ с включённым zram хватит
# и пару гигов (на случай, когда вообще наступит OOM даже с zram)
sudo btrfs filesystem mkswapfile --size 2G swapfile
sudo swapon swapfile
sudo nano /etc/fstab
```

Дальше в fstab **(в самый его конец!)**:

```text
/swap/swapfile none swap defaults 0 0
```

Потом делаем:

```shell
sudo systemctl daemon-reload
```

И ребутимся.

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
```

Дальше мы выносим файлы Docker'а в отдельный subvolume BTRFS'а **(по желанию)**, чтобы было удобнее юзать снапшоты:

```shell
sudo btrfs subvolume create /docker-data
```

И настраиваем их в конфигах:

```shell
sudo nano /etc/docker/daemon.json
```

```text
{
  "data-root": "/docker-data/docker"
}
```

```shell
sudo nano /etc/containerd/config.toml
```

```text
root = "/docker-data/containerd"
```

И делаем завершающие шаги:

```shell
sudo usermod -aG docker $USER
sudo systemctl enable docker.service
sudo systemctl enable containerd.service
```

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

#### DBeaver

```shell
flatpak install flathub io.dbeaver.DBeaverCommunity
```

#### Postman

```shell
flatpak install flathub com.getpostman.Postman
sudo dnf install openssl
cd ~/.var/app/com.getpostman.Postman/config/Postman/proxy
openssl req -subj '/C=US/CN=Postman Proxy' -new -newkey rsa:2048 -sha256 -days 365 -nodes -x509 -keyout postman-proxy-ca.key -out postman-proxy-ca.crt
```

#### Java (разработка)

Если нужен Java 17:

```shell
sudo dnf install java-17-openjdk-devel
```

Если нужен Java 11:

```shell
sudo dnf install java-11-openjdk-devel
```

Если нужен Java 8:

```shell
sudo dnf install java-1.8.0-openjdk-devel
```

##### Maven

```shell
sudo dnf install maven
```

#### PHP

Если вам нужен только CLI для очень простых скриптов: `php-cli` в DNF.

Если вам нужен LAMP, то присмотритесь лучше к решениям на базе Docker-контейнеров. Готовые скрипты для Docker Compose вы можете найти в Интернете.

Если вам нужен PHP для Laravel:

```shell
sudo dnf install php php-common php-cli php-gd php-mysqlnd php-curl php-intl php-mbstring php-bcmath php-xml php-zip composer
```

##### XAMPP (если вам не хочется Docker'а)

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

#### MongoDB Compass

```shell
flatpak install flathub com.mongodb.Compass
```

### Загрузка файлов

#### Uget

```shell
flatpak install flathub com.ugetdm.uGet
```

#### Transmission

```shell
flatpak install flathub com.transmissionbt.Transmission
```

### Снапшоты в BTRFS

```shell
sudo dnf install snapper
sudo snapper -c root create-config /
# Потом нужно поменять настройки в
# /etc/snapper/configs/root через nano
```
