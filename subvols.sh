#!/bin/bash
# Author: Egor Gavrilov (github.com/oldzoomer-ru), initially - Diogo Pessoa (github.com/diogopessoa)
# License: GPLv3, initially - MIT
# Description: Migrate Ubuntu (or other distros) to Btrfs subvolumes from LiveUSB environment.

set -e
set -o pipefail

script=$(readlink -f "$0")
scriptname=$(basename "$script")
[ "$(id -u)" -eq 0 ] || { echo "ERROR: Root required."; exit 1; }

mp=/mnt/root

show_help() {
    cat <<EOF
Usage: $scriptname {root-dev} {boot-dev} [{efi-dev}]
Example: $scriptname nvme0n1p2 sda1 nvme0n1p1
EOF
    exit 1
}

[ $# -lt 2 ] && show_help

rootdev="$1"
bootdev="$2"
efidev="${3:-}"
efi=false
[ -n "$efidev" ] && efi=true

migrate_data() {
    local src="$1"
    local dst="$2"
    [ -d "$src" ] || return 0
    [ "$(ls -A "$src" 2>/dev/null)" ] || return 0
    echo "Migrating $src -> $dst"
    if command -v rsync >/dev/null 2>&1; then
        rsync -aHAX --info=progress2 "$src/" "$dst/"
    else
        cp -a "$src/." "$dst/" 2>/dev/null || true
        [ $? -eq 0 ] && find "$src" -mindepth 1 -delete 2>/dev/null || true
    fi
}

preparation() {
    echo "Preparing environment..."
    umount -R "$mp" 2>/dev/null || true
    mkdir -p "$mp"
}
create_subvols() {
    echo "Creating Btrfs Subvolumes..."
    blkid "/dev/$rootdev" | grep -q 'TYPE="btrfs"' || { echo "ERROR: Not Btrfs"; exit 1; }

    mount "/dev/$rootdev" "$mp"
    cd "$mp"

    btrfs subvolume show '@' >/dev/null 2>&1 || btrfs subvolume snapshot . '@'
    find . -maxdepth 1 -mindepth 1 \! -name '@*' -print0 | xargs -0 rm -Rf

    local subvols=( '@home' '@log' '@cache' '@tmp' '@libvirt' '@flatpak' '@docker' '@containers' '@machines' '@var_tmp' '@opt' )
    for subvol in "${subvols[@]}"; do
        btrfs subvolume show "$subvol" >/dev/null 2>&1 || btrfs subvolume create "$subvol"
    done

    migrate_data '@'/home '@home'
    migrate_data '@'/tmp '@tmp'
    migrate_data '@'/opt '@opt'
    migrate_data '@'/var/log '@log'
    migrate_data '@'/var/cache '@cache'
    migrate_data '@'/var/tmp '@var_tmp'
    migrate_data '@'/var/lib/libvirt '@libvirt'
    migrate_data '@'/var/lib/flatpak '@flatpak'
    migrate_data '@'/var/lib/docker '@docker'
    migrate_data '@'/var/lib/containers '@containers'
    migrate_data '@'/var/lib/machines '@machines'

    cd /
    umount "$mp"
    mount "/dev/$rootdev" -o subvol='@' "$mp"

    mkdir -p "$mp"{/home,/var/log,/var/cache,/var/lib/libvirt,/var/lib/flatpak}
    mkdir -p "$mp"{/var/lib/docker,/var/lib/containers,/var/lib/machines,/var/tmp,/tmp,/opt}
}

ajusta_fstab() {
    echo "Adjusting /etc/fstab..."
    local fstab_path="$mp/etc/fstab"
    [ -f "$fstab_path" ] || { echo "ERROR: fstab not found"; exit 1; }
    cp "$fstab_path" "${fstab_path}.bak.$(date +%s)"

    local root_uuid=$(blkid --output export "/dev/$rootdev" | grep ^UUID= | cut -d= -f2)
    sed -i '/[[:space:]]btrfs[[:space:]]/d' "$fstab_path"
    # Удаляем только swap-файлы (путь начинается с /), разделы оставляем
    sed -i '/^[[:space:]]*\/.*[[:space:]]none[[:space:]]swap[[:space:]]/d' "$fstab_path"
    sed -i '/^[[:space:]]*\/.*[[:space:]]swap[[:space:]]/d' "$fstab_path"

    declare -A mountpoints=(
        ['@']='/' ['@home']='/home' ['@log']='/var/log' ['@cache']='/var/cache'
        ['@libvirt']='/var/lib/libvirt' ['@flatpak']='/var/lib/flatpak'
        ['@docker']='/var/lib/docker' ['@containers']='/var/lib/containers'
        ['@machines']='/var/lib/machines' ['@var_tmp']='/var/tmp'
        ['@tmp']='/tmp' ['@opt']='/opt'
    )

    for subvol in "${!mountpoints[@]}"; do
        echo "UUID=$root_uuid ${mountpoints[$subvol]} btrfs defaults,ssd,discard=async,noatime,space_cache=v2,compress=zstd:1,subvol=$subvol 0 0" >> "$fstab_path"
    done
}

chroot_and_update() {
    echo "Updating bootloader..."
    for dir in proc sys dev run; do mount --bind "/$dir" "$mp/$dir"; done
    mount "/dev/$bootdev" "$mp/boot"
    $efi && mount "/dev/$efidev" "$mp/boot/efi"

    if chroot "$mp" command -v update-grub >/dev/null 2>&1; then
        chroot "$mp" update-grub || echo "Warning: update-grub failed"
    else
        chroot "$mp" grub-mkconfig -o /boot/grub/grub.cfg
    fi
    chroot "$mp" update-initramfs -u -k all
}

unmount_everything() {
    echo "Unmounting..."
    umount -R "$mp" 2>/dev/null || true
    umount "$mp" 2>/dev/null || true
}

rollback() {
    echo "ROLLBACK: Error occurred."
    unmount_everything
    echo "Check $mp/etc/fstab.bak.*"
}

trap rollback ERR

preparation
create_subvols
ajusta_fstab
chroot_and_update
unmount_everything

trap - ERR

echo "Done. Reboot required."
echo "Post-check: snapper -c root create-config /"