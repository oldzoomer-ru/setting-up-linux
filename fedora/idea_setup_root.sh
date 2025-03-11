#!/bin/bash -eu

if [ "$(id -u)" -ne 0 ]; then
        echo 'This script must be run by root' >&2
        exit 1
fi

sudo dnf install java-21-openjdk-devel -y
mkdir /opt/idea-community-edition
curl -L "https://download.jetbrains.com/product?code=IC&latest&distribution=linux" | tar xvz -C /opt/idea-community-edition --strip 1
