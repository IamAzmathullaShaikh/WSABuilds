#!/bin/bash
# =============================================================================
# build.sh — WSABuilds core build script
#
# Target (locked):
#   Architecture  : x64
#   WSA channel   : retail (stable)
#   Root solution : Magisk Stable (≥ 26.0)
#   GApps         : OpenGApps Pico (x86_64, Android 13 / API 33)
#   Amazon        : kept (not removed)
#   Output        : Windows 11 x64 7z artifact
#
# Usage:
#   ./build.sh [options]
#
# Options:
#   --offline           Skip all downloads; use cached files in ../download
#   --skip-download-wsa Skip WSA download only (use cached WSA zip)
#   --magisk-custom     Use a custom Magisk build already placed in ../download
#   --compress-format   Output format: 7z | zip | none  (default: 7z)
#   --debug             Enable bash -x tracing
#   --help              Show this help and exit
#
# Copyright (C) 2024 WSABuilds Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

# ── Bash guard ───────────────────────────────────────────────────────────────
if [ ! "$BASH_VERSION" ]; then
    echo "ERROR: Run this script directly with bash, do not invoke via sh." >&2
    exit 1
fi

# ── Host architecture guard ──────────────────────────────────────────────────
HOST_ARCH=$(uname -m)
if [ "$HOST_ARCH" != "x86_64" ] && [ "$HOST_ARCH" != "aarch64" ]; then
    echo "ERROR: Unsupported host architecture: $HOST_ARCH" >&2
    exit 1
fi

# ── Change to script directory ───────────────────────────────────────────────
cd "$(dirname "$0")" || exit 1

# =============================================================================
# Source modules
# =============================================================================

# shellcheck source=config.sh
source ./config.sh || { echo "ERROR: Failed to source config.sh" >&2; exit 1; }

# shellcheck source=download_utils.sh
source ./download_utils.sh || { echo "ERROR: Failed to source download_utils.sh" >&2; exit 1; }

# =============================================================================
# Directory / path constants
# =============================================================================

DOWNLOAD_DIR=../download
DOWNLOAD_CONF_NAME=download.list
OUTPUT_DIR=../output
PYTHON_VENV_DIR="$(dirname "$PWD")/python3-env"

# =============================================================================
# Runtime state (set in setup_env, consumed throughout)
# =============================================================================

WORK_DIR=""
WSA_WORK_ENV=""
ANDROID_API=$DEFAULT_ANDROID_API

# Download-flag vars — set to 1 when a file must be deleted on failure
CLEAN_DOWNLOAD_WSA=""
CLEAN_DOWNLOAD_MAGISK=""
CLEAN_DOWNLOAD_GAPPS=""

# Version strings populated after extraction
MAGISK_VERSION_NAME=""
MAGISK_VERSION_CODE=0
WSA_VER=""
WSA_REL=""
WSA_MAJOR_VER=0
GAPPS_RC_NAME=""
OPENGAPPS_ZIP_NAME=""

# Parsed CLI flags
OFFLINE=""
SKIP_DOWN_WSA=""
CUSTOM_MAGISK=""
COMPRESS_FORMAT="${DEFAULT_COMPRESS_FORMAT:-7z}"
DEBUG=""

# =============================================================================
# Trap / cleanup functions
# =============================================================================

# ---------------------------------------------------------------------------
# dir_clean — remove work directory and deactivate Python venv
# Called automatically on EXIT via trap.
# ---------------------------------------------------------------------------
dir_clean() {
    [ -d "$WORK_DIR" ] && rm -rf "${WORK_DIR:?}"

    if [ "$TMPDIR" ] && [ -d "$TMPDIR" ]; then
        echo "build: cleaning TMPDIR"
        rm -rf "${TMPDIR:?}"
        unset TMPDIR
    fi

    rm -f "${DOWNLOAD_DIR:?}/$DOWNLOAD_CONF_NAME" 2>/dev/null || true

    # Deactivate Python venv if we are inside one
    if python3 -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)' 2>/dev/null; then
        echo "build: deactivating Python venv"
        deactivate 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# clean_download — remove partial/corrupt download files that were flagged
# Called from abort() so a re-run triggers fresh downloads.
# ---------------------------------------------------------------------------
clean_download() {
    [ -d "$DOWNLOAD_DIR" ] || return
    echo "build: cleaning flagged download files"
    [ "$CLEAN_DOWNLOAD_WSA"    ] && clean_partial_download "${WSA_ZIP_PATH:?}"
    [ "$CLEAN_DOWNLOAD_MAGISK" ] && clean_partial_download "${MAGISK_PATH:?}"
    [ "$CLEAN_DOWNLOAD_GAPPS"  ] && {
        clean_partial_download "${DOWNLOAD_DIR:?}/$(gapps_image_name "$ANDROID_API")"
        clean_partial_download "${DOWNLOAD_DIR:?}/$(gapps_rc_name "$ANDROID_API")"
    }
}

# ---------------------------------------------------------------------------
# abort [message] — print error, clean up, and exit 1
# ---------------------------------------------------------------------------
abort() {
    [ "$1" ] && echo -e "ERROR: $1" >&2
    echo "build: fatal error — aborting." >&2
    dir_clean
    clean_download
    exit 1
}

trap dir_clean  EXIT
trap 'abort "Interrupted by user"' INT TERM

# =============================================================================
# Argument parsing
# =============================================================================

usage() {
    cat <<'EOF'
WSABuilds — Magisk Stable + OpenGApps Pico (Retail x64)

Usage:
  ./build.sh [options]

Options:
  --offline             Skip all downloads; use cached files in ../download/
  --skip-download-wsa   Skip WSA download only; still download Magisk + GApps
  --magisk-custom       Use a custom Magisk already in ../download/
                          Named:  magisk-stable.zip  OR  app-stable.apk
  --compress-format     Output compression: 7z | zip | none  (default: 7z)
  --debug               Enable bash -x tracing
  --help                Show this help message and exit

Examples:
  ./build.sh
  ./build.sh --offline
  ./build.sh --magisk-custom
  ./build.sh --compress-format zip
EOF
}

parse_args() {
    local opts
    opts=$(getopt \
        --longoptions "offline,skip-download-wsa,magisk-custom,compress-format:,debug,help" \
        --name "$(basename "$0")" \
        --options "" \
        -- "$@") || {
        echo "ERROR: Failed to parse arguments. Run with --help for usage." >&2
        exit 1
    }

    eval set -- "$opts"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --offline)
                OFFLINE=1
                shift
                ;;
            --skip-download-wsa)
                SKIP_DOWN_WSA=1
                shift
                ;;
            --magisk-custom)
                CUSTOM_MAGISK=1
                shift
                ;;
            --compress-format)
                COMPRESS_FORMAT="$2"
                shift 2
                ;;
            --debug)
                DEBUG=1
                shift
                ;;
            --help)
                usage
                exit 0
                ;;
            --)
                shift
                break
                ;;
        esac
    done

    # Validate compress format
    case "$COMPRESS_FORMAT" in
        7z|zip|none) ;;
        *)
            echo "ERROR: Invalid --compress-format '$COMPRESS_FORMAT'. Valid: 7z, zip, none" >&2
            exit 1
            ;;
    esac

    [ "$DEBUG" ] && set -x
}

# =============================================================================
# setup_env — initialise work directory and Python venv
# =============================================================================

setup_env() {
    echo "════════════════════════════════════════════════════"
    echo " WSABuilds  |  Magisk Stable + OpenGApps Pico"
    echo " Arch: ${TARGET_ARCH}  |  Release: ${TARGET_RELEASE_TYPE}"
    echo "════════════════════════════════════════════════════"

    # Create work directory
    WORK_DIR=$(mktemp -d -t wsa-build-XXXXXXXXXX) || abort "mktemp failed"

    # Set up shared env file (key=value pairs shared between bash and python)
    WSA_WORK_ENV="${WORK_DIR}/ENV"
    touch "$WSA_WORK_ENV"
    export WSA_WORK_ENV

    # Ensure download dir exists
    mkdir -p "$DOWNLOAD_DIR"

    # Activate Python venv if present
    # shellcheck disable=SC1091
    [ -f "$PYTHON_VENV_DIR/bin/activate" ] && {
        source "$PYTHON_VENV_DIR/bin/activate" \
            || abort "Failed to activate Python venv. Re-run install_deps.sh."
    }

    echo "build: work dir = $WORK_DIR"
}

# =============================================================================
# Path helpers — computed from config + runtime state
# =============================================================================

WSA_ZIP_PATH=""
MAGISK_PATH=""
CUST_PATH=""
vclibs_PATH=""
UWPVCLibs_PATH=""
xaml_PATH=""

resolve_paths() {
    WSA_ZIP_PATH="$DOWNLOAD_DIR/wsa-${TARGET_RELEASE_TYPE}.zip"
    vclibs_PATH="$DOWNLOAD_DIR/Microsoft.VCLibs.140.00_${TARGET_ARCH}.appx"
    UWPVCLibs_PATH="$DOWNLOAD_DIR/Microsoft.VCLibs.140.00.UWPDesktop_${TARGET_ARCH}.appx"
    xaml_PATH="$DOWNLOAD_DIR/Microsoft.UI.Xaml.2.8_${TARGET_ARCH}.appx"
    MAGISK_PATH="$DOWNLOAD_DIR/magisk-stable.zip"
    CUST_PATH="$DOWNLOAD_DIR/cust.img"
}

# =============================================================================
# Step 1 — Download WSA
# =============================================================================

download_wsa() {
    echo -e "\n── Step 1: Download WSA ────────────────────────────────────────"

    if [ -z "$OFFLINE" ]; then
        if [ -z "$SKIP_DOWN_WSA" ]; then
            echo "build: generating WSA download links …"
            python3 generateWSALinks.py \
                "$TARGET_ARCH" "$TARGET_RELEASE_TYPE" \
                "$DOWNLOAD_DIR" "$DOWNLOAD_CONF_NAME" \
                || abort "generateWSALinks.py failed"
            echo "build: downloading WSA …"
        else
            echo "build: generating WSA dependency links (WSA zip will be reused) …"
            python3 generateWSALinks.py \
                "$TARGET_ARCH" "$TARGET_RELEASE_TYPE" \
                "$DOWNLOAD_DIR" "$DOWNLOAD_CONF_NAME" \
                "skip_wsa" \
                || abort "generateWSALinks.py failed"
            echo "build: skipping WSA zip download; downloading dependencies only …"
        fi

        if [ -f "$DOWNLOAD_DIR/$DOWNLOAD_CONF_NAME" ]; then
            aria2_download \
                "$DOWNLOAD_DIR/$DOWNLOAD_CONF_NAME" \
                "$DOWNLOAD_DIR/aria2_wsa.log" \
                || abort "WSA download failed. See $DOWNLOAD_DIR/aria2_wsa.log"
            rm -f "${DOWNLOAD_DIR:?}/$DOWNLOAD_CONF_NAME"
        fi
    else
        echo "build: offline mode — skipping WSA download"
    fi
}

# =============================================================================
# Step 2 — Extract WSA
# =============================================================================

extract_wsa() {
    echo -e "\n── Step 2: Extract WSA ─────────────────────────────────────────"

    assert_file_exists "$WSA_ZIP_PATH" "WSA zip (${WSA_ZIP_PATH})" \
        || abort "WSA zip not found. Run without --offline or check ../download/."

    if ! python3 extractWSA.py "$TARGET_ARCH" "$WSA_ZIP_PATH" "$WORK_DIR" "$WSA_WORK_ENV"; then
        CLEAN_DOWNLOAD_WSA=1
        abort "Extraction of WSA zip failed — the file may be corrupt."
    fi

    echo "build: WSA extracted"
    echo -e "done\n"

    # Load WSA version variables into this shell
    # shellcheck disable=SC1090
    source "$WSA_WORK_ENV" || abort "Failed to load WSA environment variables"

    # WSA < 2211 ships Android 12.1 (API 32), not 13 (API 33)
    if [[ "$WSA_MAJOR_VER" -lt 2211 ]]; then
        ANDROID_API=32
        echo "build: WSA version ${WSA_MAJOR_VER} — using Android API 32"
    else
        echo "build: WSA version ${WSA_MAJOR_VER} — using Android API ${ANDROID_API}"
    fi
}

# =============================================================================
# Step 3 — Download Magisk Stable + OpenGApps Pico
# =============================================================================

download_magisk_and_gapps() {
    echo -e "\n── Step 3: Download Magisk + OpenGApps Pico ────────────────────"

    if [ -n "$OFFLINE" ]; then
        echo "build: offline mode — skipping Magisk + GApps download"
        return
    fi

    # Wipe the conf file so we start fresh
    rm -f "${DOWNLOAD_DIR:?}/$DOWNLOAD_CONF_NAME"

    # -- Magisk Stable --------------------------------------------------------
    if [ -z "$CUSTOM_MAGISK" ]; then
        echo "build: fetching Magisk stable link …"
        python3 generateMagiskLink.py \
            "$DOWNLOAD_DIR" "$DOWNLOAD_CONF_NAME" \
            || abort "generateMagiskLink.py failed"
    else
        echo "build: using custom Magisk from $DOWNLOAD_DIR"
        # Allow both naming conventions: magisk-stable.zip and app-stable.apk
        if [ ! -f "$MAGISK_PATH" ]; then
            local apk_path="$DOWNLOAD_DIR/app-stable.apk"
            if [ -f "$apk_path" ]; then
                MAGISK_PATH="$apk_path"
                echo "build: found custom Magisk as $(basename "$MAGISK_PATH")"
            else
                abort "Custom Magisk not found.  Place it in $DOWNLOAD_DIR as:\n" \
                      "  magisk-stable.zip  OR  app-stable.apk"
            fi
        fi
    fi

    # -- OpenGApps Pico -------------------------------------------------------
    echo "build: fetching OpenGApps Pico link …"
    python3 generateGappsLink.py \
        "$DOWNLOAD_DIR" "$DOWNLOAD_CONF_NAME" "$ANDROID_API" \
        || abort "generateGappsLink.py failed"

    # Reload env to pick up OPENGAPPS_ZIP_NAME / GAPPS_RC_NAME
    # shellcheck disable=SC1090
    source "$WSA_WORK_ENV" || abort "Failed to reload WSA_WORK_ENV after GApps link generation"

    # -- Download everything queued -------------------------------------------
    if [ -f "$DOWNLOAD_DIR/$DOWNLOAD_CONF_NAME" ]; then
        echo "build: downloading Magisk + OpenGApps Pico …"
        aria2_download \
            "$DOWNLOAD_DIR/$DOWNLOAD_CONF_NAME" \
            "$DOWNLOAD_DIR/aria2_artifacts.log" \
            || abort "Magisk/GApps download failed. See $DOWNLOAD_DIR/aria2_artifacts.log"
        rm -f "${DOWNLOAD_DIR:?}/$DOWNLOAD_CONF_NAME"
    fi
}

# =============================================================================
# Step 4 — Verify required files exist
# =============================================================================

verify_required_files() {
    echo -e "\n── Step 4: Verify required files ───────────────────────────────"

    local missing=0

    # Reload env to get the latest filenames
    # shellcheck disable=SC1090
    source "$WSA_WORK_ENV" || abort "Failed to load WSA_WORK_ENV"

    local -A required_files=(
        ["VCLibs"]="$vclibs_PATH"
        ["UWP VCLibs"]="$UWPVCLibs_PATH"
        ["XAML"]="$xaml_PATH"
        ["Magisk ZIP"]="$MAGISK_PATH"
        ["WSA-Addon cust.img"]="$CUST_PATH"
    )

    # GApps files — resolved from config functions
    local gapps_img_name
    gapps_img_name=$(gapps_image_name "$ANDROID_API") || abort "Failed to resolve GApps image name"
    local gapps_rc_name
    gapps_rc_name=$(gapps_rc_name "$ANDROID_API") || abort "Failed to resolve GApps RC name"

    required_files["GApps Image ($gapps_img_name)"]="$DOWNLOAD_DIR/$gapps_img_name"
    required_files["GApps RC ($gapps_rc_name)"]="$DOWNLOAD_DIR/$gapps_rc_name"

    for label in "${!required_files[@]}"; do
        local path="${required_files[$label]}"
        if [ ! -f "$path" ]; then
            echo "build: MISSING — $label: $path" >&2
            missing=$((missing + 1))
        else
            echo "build: OK — $label"
        fi
    done

    if [ "$missing" -gt 0 ]; then
        abort "$missing required file(s) missing. Check the download step."
    fi
}

# =============================================================================
# Step 5 — Extract + validate Magisk
# =============================================================================

extract_magisk() {
    echo -e "\n── Step 5: Extract Magisk ──────────────────────────────────────"

    if ! python3 extractMagisk.py "$TARGET_ARCH" "$MAGISK_PATH" "$WORK_DIR"; then
        CLEAN_DOWNLOAD_MAGISK=1
        abort "Magisk extraction failed — the ZIP may be corrupt or incomplete."
    fi

    # shellcheck disable=SC1090
    source "$WSA_WORK_ENV" || abort "Failed to reload WSA_WORK_ENV after Magisk extraction"

    echo "build: Magisk ${MAGISK_VERSION_NAME} (${MAGISK_VERSION_CODE}) extracted"

    # Double-check version code (extractMagisk.py already enforces this,
    # but an explicit check here provides a clear message in the build log)
    if [ -n "$MAGISK_VERSION_CODE" ] && \
       [ "$MAGISK_VERSION_CODE" -lt "$MIN_MAGISK_VERSION_CODE" ] 2>/dev/null; then
        abort "Magisk ${MAGISK_VERSION_NAME} is too old. Need ≥ 26.0 (code ≥ ${MIN_MAGISK_VERSION_CODE})."
    fi

    chmod +x "$WORK_DIR/magisk/magiskboot" || abort "chmod on magiskboot failed"
    echo -e "done\n"
}

# =============================================================================
# Step 6 — Integrate Magisk into initrd
# =============================================================================

integrate_magisk() {
    echo -e "\n── Step 6: Integrate Magisk ────────────────────────────────────"

    # Compress Magisk binaries with xz for storage in the ramdisk overlay
    if [ -f "$WORK_DIR/magisk/magisk64" ]; then
        # Dual-ABI build (normal for Magisk ≥ 24)
        "$WORK_DIR/magisk/magiskboot" compress=xz \
            "$WORK_DIR/magisk/magisk64" "$WORK_DIR/magisk/magisk64.xz" \
            || abort "Failed to compress magisk64"
        "$WORK_DIR/magisk/magiskboot" compress=xz \
            "$WORK_DIR/magisk/magisk32" "$WORK_DIR/magisk/magisk32.xz" \
            || abort "Failed to compress magisk32"
    else
        # Single-ABI fallback
        "$WORK_DIR/magisk/magiskboot" compress=xz \
            "$WORK_DIR/magisk/magisk" "$WORK_DIR/magisk/magisk.xz" \
            || abort "Failed to compress magisk"
    fi

    if [ -f "$WORK_DIR/magisk/init-ld" ]; then
        "$WORK_DIR/magisk/magiskboot" compress=xz \
            "$WORK_DIR/magisk/init-ld" "$WORK_DIR/magisk/init-ld.xz" \
            || abort "Failed to compress init-ld"
    fi

    # Compress the full Magisk APK stub — used by magiskinit to set up /data
    "$WORK_DIR/magisk/magiskboot" compress=xz \
        "$MAGISK_PATH" "$WORK_DIR/magisk/stub.xz" \
        || abort "Failed to compress Magisk stub"

    echo "build: patching initrd.img with Magisk …"

    local target_initrd
    target_initrd=$(to_native_path "$WORK_DIR/wsa/$TARGET_ARCH/Tools/initrd.img")
    local path_lspinit
    path_lspinit=$(to_native_path "../bin/$TARGET_ARCH/lspinit")
    local path_magiskinit
    path_magiskinit=$(to_native_path "$WORK_DIR/magisk/magiskinit")
    local path_magisk64
    path_magisk64=$(to_native_path "$WORK_DIR/magisk/magisk64.xz")
    local path_magisk32
    path_magisk32=$(to_native_path "$WORK_DIR/magisk/magisk32.xz")
    local path_magisk
    path_magisk=$(to_native_path "$WORK_DIR/magisk/magisk.xz")
    local path_initld
    path_initld=$(to_native_path "$WORK_DIR/magisk/init-ld.xz")
    local path_stub
    path_stub=$(to_native_path "$WORK_DIR/magisk/stub.xz")
    local path_cust
    path_cust=$(to_native_path "$CUST_PATH")

    # Build CPIO patch command array dynamically with relative paths (no leading slashes)
    local -a cpio_cmds=(
        "mv init wsainit"
        "add 0750 lspinit $path_lspinit"
        "ln lspinit init"
        "add 0750 magiskinit $path_magiskinit"
        "mkdir 0750 overlay.d"
        "mkdir 0750 overlay.d/sbin"
    )

    if [ -f "$WORK_DIR/magisk/magisk64.xz" ]; then
        cpio_cmds+=("add 0644 overlay.d/sbin/magisk64.xz $path_magisk64")
    fi
    if [ -f "$WORK_DIR/magisk/magisk32.xz" ]; then
        cpio_cmds+=("add 0644 overlay.d/sbin/magisk32.xz $path_magisk32")
    fi
    if [ -f "$WORK_DIR/magisk/magisk.xz" ]; then
        cpio_cmds+=("add 0644 overlay.d/sbin/magisk.xz $path_magisk")
    fi
    if [ -f "$WORK_DIR/magisk/init-ld.xz" ]; then
        cpio_cmds+=("add 0644 overlay.d/sbin/init-ld.xz $path_initld")
    fi

    cpio_cmds+=(
        "add 0644 overlay.d/sbin/stub.xz $path_stub"
        "mkdir 000 .backup"
        "add 000 overlay.d/init.lsp.magisk.rc init.lsp.magisk.rc"
        "add 000 overlay.d/sbin/post-fs-data.sh post-fs-data.sh"
        "add 000 overlay.d/sbin/lsp_cust.img $path_cust"
    )

    # Patch the WSA ramdisk (initrd.img) via magiskboot cpio
    "$WORK_DIR/magisk/magiskboot" cpio "$target_initrd" "${cpio_cmds[@]}" \
        || abort "magiskboot cpio failed — unable to patch initrd"

    # Verify that the boot trampoline was properly injected
    "$WORK_DIR/magisk/magiskboot" cpio "$target_initrd" "exists wsainit" \
        || abort "Verification failed: wsainit not found in patched initrd"

    echo -e "done\n"
}

# =============================================================================
# Step 7 — Integrate GApps (Pico minimal package)
# =============================================================================

integrate_pico_gapps() {
    echo -e "\n── Step 7: Integrate GApps (Pico package) ───────────────────────"

    local gapps_img_name
    gapps_img_name=$(gapps_image_name "$ANDROID_API") || abort "Failed to resolve GApps image name"
    local gapps_rc_name
    gapps_rc_name=$(gapps_rc_name "$ANDROID_API") || abort "Failed to resolve GApps RC name"

    local gapps_img="$DOWNLOAD_DIR/$gapps_img_name"
    local gapps_rc="$DOWNLOAD_DIR/$gapps_rc_name"

    assert_file_exists "$gapps_img" "GApps Image ($gapps_img_name)" || abort "GApps image missing"
    assert_file_exists "$gapps_rc"  "GApps RC file ($gapps_rc_name)" || abort "GApps RC file missing"

    echo "build: patching initrd.img with GApps …"

    local target_initrd
    target_initrd=$(to_native_path "$WORK_DIR/wsa/$TARGET_ARCH/Tools/initrd.img")
    local native_gapps_rc
    native_gapps_rc=$(to_native_path "$gapps_rc")
    local native_gapps_img
    native_gapps_img=$(to_native_path "$gapps_img")

    "$WORK_DIR/magisk/magiskboot" cpio \
        "$target_initrd" \
        "add 000 overlay.d/gapps.rc $native_gapps_rc" \
        "add 000 overlay.d/sbin/lsp_gapps.img $native_gapps_img" \
        || { CLEAN_DOWNLOAD_GAPPS=1; abort "magiskboot cpio failed — unable to patch initrd with GApps"; }

    echo -e "done\n"
}

# =============================================================================
# Step 8 — Fix build.prop files for GApps compatibility
# =============================================================================

fix_gapps_props() {
    echo -e "\n── Step 8: Fix build.prop for GApps ───────────────────────────"

    local output_path="$WORK_DIR/wsa/$TARGET_ARCH"
    python3 fixGappsProp.py \
        "$output_path" \
        "$TARGET_DEVICE_NAME" \
        "Pixel 5" \
        "pico" \
        || abort "fixGappsProp.py failed"

    echo -e "done\n"
}

# =============================================================================
# Step 9 — Assemble output directory
# =============================================================================

assemble_output() {
    echo -e "\n── Step 9: Assemble output ─────────────────────────────────────"

    # Remove Microsoft signing artifacts (they're re-signed by the installer)
    rm -rf \
        "${WORK_DIR:?}/wsa/$TARGET_ARCH/[Content_Types].xml" \
        "$WORK_DIR/wsa/$TARGET_ARCH/AppxBlockMap.xml" \
        "$WORK_DIR/wsa/$TARGET_ARCH/AppxSignature.p7x" \
        "$WORK_DIR/wsa/$TARGET_ARCH/AppxMetadata" \
        || abort "Failed to remove signing artifacts"

    # Copy Windows runtime libraries and installer scripts
    cp "$vclibs_PATH" "$xaml_PATH" "$WORK_DIR/wsa/$TARGET_ARCH"       || abort "Copy VCLibs failed"
    cp "$UWPVCLibs_PATH" "$xaml_PATH" "$WORK_DIR/wsa/$TARGET_ARCH"    || abort "Copy UWP VCLibs failed"
    cp "../bin/$TARGET_ARCH/makepri.exe" "$WORK_DIR/wsa/$TARGET_ARCH"  || abort "Copy makepri.exe failed"
    mkdir -p "$WORK_DIR/wsa/$TARGET_ARCH/xml"
    cp "../xml/priconfig.xml" "$WORK_DIR/wsa/$TARGET_ARCH/xml/"        || abort "Copy priconfig.xml failed"
    cp ../installer/MakePri.ps1 "$WORK_DIR/wsa/$TARGET_ARCH"           || abort "Copy MakePri.ps1 failed"
    cp ../installer/Install.ps1 "$WORK_DIR/wsa/$TARGET_ARCH"           || abort "Copy Install.ps1 failed"
    cp ../installer/Run.bat     "$WORK_DIR/wsa/$TARGET_ARCH"           || abort "Copy Run.bat failed"

    # Generate the file manifest used by the Windows installer
    find "$WORK_DIR/wsa/$TARGET_ARCH" -maxdepth 1 -mindepth 1 -printf "%P\n" \
        > "$WORK_DIR/wsa/$TARGET_ARCH/filelist.txt" \
        || abort "Failed to generate filelist.txt"

    echo -e "done\n"
}

# =============================================================================
# Step 10 — Move to output and write GitHub output variables
# =============================================================================

finalise_output() {
    echo -e "\n── Step 10: Finalise output ────────────────────────────────────"

    # Reload final env vars (WSA_VER, WSA_REL, etc.)
    # shellcheck disable=SC1090
    source "$WSA_WORK_ENV" || abort "Failed to load final WSA env"

    # Build artifact name components
    local name_root   # -with-magisk-<ver>(<code>)-stable
    local name_gapps  # -GApps-<android_ver>-pico

    name_root="-with-magisk-${MAGISK_VERSION_NAME}(${MAGISK_VERSION_CODE})-stable"

    case "$ANDROID_API" in
        30) name_gapps="-GApps-11.0-pico" ;;
        32) name_gapps="-GApps-12.1-pico" ;;
        33) name_gapps="-GApps-13.0-pico" ;;
        *)  name_gapps="-GApps-pico" ;;
    esac

    local artifact_name="WSA_${WSA_VER}_${TARGET_ARCH}_${WSA_REL}${name_root}${name_gapps}"
    local short_name="WSA_${WSA_VER}_${TARGET_ARCH}"

    mkdir -p "$OUTPUT_DIR"
    local output_path="${OUTPUT_DIR:?}/$short_name"
    mv "$WORK_DIR/wsa/$TARGET_ARCH" "$output_path" || abort "mv output failed"

    echo "build: artifact = $artifact_name"
    echo "build: short    = $short_name"

    # Write outputs consumed by the GitHub Actions job (if running in CI)
    if [ -n "$GITHUB_OUTPUT" ]; then
        {
            echo "artifact_folder=${short_name}"
            echo "artifact=${artifact_name}"
            echo "arch=${TARGET_ARCH}"
            echo "built=$(date -u +%Y%m%d%H%M%S)"
            echo "file_ext=${COMPRESS_FORMAT}"
            echo "magisk_ver=${MAGISK_VERSION_NAME}"
            echo "gapps_variant=pico"
        } >> "$GITHUB_OUTPUT"
    fi

    echo -e "done\n"
    echo "════════════════════════════════════════════════════"
    echo " Build complete:  $artifact_name"
    echo "════════════════════════════════════════════════════"
}

# =============================================================================
# Main entry point
# =============================================================================

main() {
    parse_args "$@"
    setup_env
    resolve_paths

    download_wsa
    extract_wsa
    download_magisk_and_gapps
    verify_required_files
    extract_magisk
    integrate_magisk
    integrate_pico_gapps
    fix_gapps_props
    assemble_output
    finalise_output
}

main "$@"
