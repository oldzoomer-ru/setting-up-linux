#!/bin/bash -eu

if [ "$(id -u)" -eq 0 ]; then
        echo 'This script must NOT be run by root' >&2
        exit 1
fi

sudo apt install git -y

# Укажите реальные данные через переменные
git config --global user.name "$REALNAME"
git config --global user.email "$EMAIL"

sudo apt install openjdk-17-jdk -y
curl -L "https://download.jetbrains.com/product?code=IC&latest&distribution=linux" | sudo tar xvz -C /opt/idea-community-edition --strip 1
