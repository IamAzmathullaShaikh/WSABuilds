#!/bin/sh
MAGISKTMP=/sbin
[ -d /sbin ] || MAGISKTMP=/debug_ramdisk
MAGISKBIN=/data/adb/magisk
if [ ! -d /data/adb ]; then
    mkdir -m 700 /data/adb
    chcon u:object_r:adb_data_file:s0 /data/adb
fi
if [ ! -d $MAGISKBIN ]; then
    # shellcheck disable=SC2174
    mkdir -p -m 755 $MAGISKBIN
    chcon u:object_r:system_file:s0 $MAGISKBIN
fi
if [ -f "$MAGISKTMP/adbkey.pub" ]; then
    mkdir -p -m 700 /data/misc/adb
    cat "$MAGISKTMP/adbkey.pub" >> /data/misc/adb/adb_keys
    chmod 640 /data/misc/adb/adb_keys
    chown system:shell /data/misc/adb/adb_keys 2>/dev/null || true
fi
# Configure Magisk superuser policy to grant ADB shell (uid 2000) root access
mkdir -p -m 755 /data/adb/service.d
cat << 'EOFSCRIPT' > /data/adb/service.d/00-adb-root.sh
#!/system/bin/sh
magisk --sqlite "INSERT OR REPLACE INTO settings (key, value) VALUES ('root_access', 3);" 2>/dev/null || true
magisk --sqlite "INSERT OR REPLACE INTO policies (uid, policy, until, logging, notification) VALUES (2000, 2, 0, 1, 1);" 2>/dev/null || true
EOFSCRIPT
chmod 755 /data/adb/service.d/00-adb-root.sh
if [ -x "$MAGISKTMP/magisk" ]; then
    "$MAGISKTMP/magisk" --sqlite "INSERT OR REPLACE INTO settings (key, value) VALUES ('root_access', 3);" 2>/dev/null || true
    "$MAGISKTMP/magisk" --sqlite "INSERT OR REPLACE INTO policies (uid, policy, until, logging, notification) VALUES (2000, 2, 0, 1, 1);" 2>/dev/null || true
fi
ABI=$(getprop ro.product.cpu.abi)
for file in busybox magiskpolicy magiskboot magiskinit; do
    [ -x "$MAGISKBIN/$file" ] || {
        unzip -d $MAGISKBIN -oj $MAGISKTMP/stub.apk "lib/$ABI/lib$file.so"
        mv $MAGISKBIN/lib$file.so $MAGISKBIN/$file
        chmod 755 "$MAGISKBIN/$file"
    }
done
for file in util_functions.sh boot_patch.sh; do
    [ -x "$MAGISKBIN/$file" ] || {
        unzip -d $MAGISKBIN -oj $MAGISKTMP/stub.apk "assets/$file"
        chmod 755 "$MAGISKBIN/$file"
    }
done
for file in "$MAGISKTMP"/*; do
    if echo "$file" | grep -Eq "lsp_.+\.img"; then
        foldername=$(basename "$file" .img)
        mkdir -p "$MAGISKTMP/$foldername"
        mount -t auto -o ro,loop "$file" "$MAGISKTMP/$foldername"
        "$MAGISKTMP/$foldername/post-fs-data.sh" &
    fi
done
wait
for file in "$MAGISKTMP"/*; do
    if echo "$file" | grep -Eq "lsp_.+\.img"; then
        foldername=$(basename "$file" .img)
        umount "$MAGISKTMP/$foldername"
        rm -rf "${MAGISKTMP:?}/${foldername:?}"
        rm -f "$file"
    fi
done
