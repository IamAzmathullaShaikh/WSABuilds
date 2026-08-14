#!/bin/bash
#
# This file is part of the WSABuilds project.
#
# apply_custom_model.sh applies the requested Pixel "custom model" build props
# (ro.product.*, ro.build.fingerprint, ...) to a freshly built WSA artifact by
# mounting the ext4 system/vendor images, running fixGappsProp.py against them
# and repacking the images back to vhdx.
#
# Usage: apply_custom_model.sh <artifact_folder> <model_code>
#   e.g. ./scripts/apply_custom_model.sh WSA_2407.40000.4.0_x64 redfin
#
# It is wired into the build workflows after the Houdini step, so it runs only
# when a device model was requested (devicemodel != none).

set -e

if [ ! "$BASH_VERSION" ]; then
    echo "Please do not use sh to run this script, just execute it directly" 1>&2
    exit 1
fi
cd "$(dirname "$0")" || exit 1

ARTIFACT_FOLDER="$1"
MODEL_CODE="$2"
if [ -z "$ARTIFACT_FOLDER" ] || [ -z "$MODEL_CODE" ] || [ "$MODEL_CODE" = "none" ]; then
    echo "Usage: $0 <artifact_folder> <model_code>"
    exit 1
fi

# Model code -> human readable Pixel name (used by fixGappsProp.py)
declare -A MODEL_NAME_MAP=(
    ["sunfish"]="Pixel 4a"
    ["bramble"]="Pixel 4a (5G)"
    ["redfin"]="Pixel 5"
    ["barbet"]="Pixel 5a"
    ["raven"]="Pixel 6 Pro"
    ["oriole"]="Pixel 6"
    ["bluejay"]="Pixel 6a"
    ["panther"]="Pixel 7"
    ["cheetah"]="Pixel 7 Pro"
    ["lynx"]="Pixel 7a"
    ["tangorpro"]="Pixel Tablet"
    ["felix"]="Pixel Fold"
)
MODEL_NAME="${MODEL_NAME_MAP[$MODEL_CODE]}"
if [ -z "$MODEL_NAME" ]; then
    echo "Unknown custom model: $MODEL_CODE"
    exit 1
fi

# This script lives in MagiskOnWSA/scripts, so the repo root is the parent
WORK_DIR="$(dirname "$PWD")"
WSA_PATH="$WORK_DIR/output/$ARTIFACT_FOLDER"
MOUNT_BASE="$WORK_DIR/mount_temp"

abort() {
    echo "Error: $1"
    sudo umount "$MOUNT_BASE/system" 2>/dev/null || true
    sudo umount "$MOUNT_BASE/vendor" 2>/dev/null || true
    sudo rm -rf "$MOUNT_BASE" 2>/dev/null || true
    exit 1
}
trap abort EXIT

if [ ! -f "$WSA_PATH/system.vhdx" ] || [ ! -f "$WSA_PATH/vendor.vhdx" ]; then
    abort "WSA images not found in $WSA_PATH"
fi

echo "Applying custom model: $MODEL_CODE ($MODEL_NAME)"

for image_type in system vendor; do
    echo "=== Processing $image_type image ==="
    qemu-img convert -f vhdx -O raw "$WSA_PATH/$image_type.vhdx" "$WSA_PATH/$image_type.img" || abort "Failed to convert $image_type.vhdx"
    sudo rm -rf "$WSA_PATH/$image_type.vhdx" || abort "Failed to remove $image_type.vhdx"
    # Unshare copy-on-write blocks so the read-only images become writable
    sudo e2fsck -pf -E unshare_blocks "$WSA_PATH/$image_type.img" || {
        echo "y" | sudo e2fsck -E unshare_blocks "$WSA_PATH/$image_type.img" || abort "Failed to prepare $image_type filesystem for read-write access"
    }
    sudo mkdir -p "$MOUNT_BASE/$image_type" || abort "Failed to create mount point for $image_type"
    sudo mount -t ext4 -o loop "$WSA_PATH/$image_type.img" "$MOUNT_BASE/$image_type" || abort "Failed to mount $image_type.img"
done

# fixGappsProp.py expects a root containing system/build.prop, vendor/build.prop,
# vendor/odm/etc/build.prop and vendor/vendor_dlkm/etc/build.prop
sudo python3 fixGappsProp.py "$MOUNT_BASE" "$MODEL_CODE" "$MODEL_NAME" || abort "Failed to fix build props"

# Reset timestamps so the image is reproducible
sudo find "$MOUNT_BASE" -not -type l -exec touch -hamt 200901010000.00 {} \; 2>/dev/null || true

for image_type in system vendor; do
    echo "=== Finalizing $image_type image ==="
    sudo umount "$MOUNT_BASE/$image_type" || abort "Failed to unmount $image_type"
    sudo e2fsck -yf "$WSA_PATH/$image_type.img" || abort "Failed to check filesystem for $image_type.img"
    sudo resize2fs -M "$WSA_PATH/$image_type.img" || abort "Failed to minimize $image_type.img"
    qemu-img convert -f raw -O vhdx "$WSA_PATH/$image_type.img" "$WSA_PATH/$image_type.vhdx" || abort "Failed to convert $image_type.img to vhdx"
    rm -f "$WSA_PATH/$image_type.img" || true
done

sudo rm -rf "$MOUNT_BASE" 2>/dev/null || true
trap - EXIT
echo "Custom model $MODEL_CODE applied successfully"
