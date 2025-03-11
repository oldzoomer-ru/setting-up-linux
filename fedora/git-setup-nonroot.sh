#!/bin/bash -eu

if [ "$(id -u)" -eq 0 ]; then
        echo 'This script must NOT be run by root' >&2
        exit 1
fi

# Укажите реальные данные через переменные
git config --global user.name "$REALNAME"
git config --global user.email "$EMAIL"