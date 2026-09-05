#!/bin/bash
# =============================================================================
# config.sh — Build-target constants for WSABuilds
#
# Target: WSA x64  |  Magisk Stable  |  OpenGApps Pico  |  Retail  |  Win 11
#
# Source this file from build.sh and any other script that needs these values.
# ALL values are declared readonly so downstream scripts cannot accidentally
# override them.
#
# Copyright (C) 2024 WSABuilds Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

# ---------------------------------------------------------------------------
# Architecture & WSA release channel
# ---------------------------------------------------------------------------
readonly TARGET_ARCH="x64"
readonly TARGET_ARCH_NATIVE="x86_64"          # used by GApps / OpenGApps naming
readonly TARGET_RELEASE_TYPE="retail"

# ---------------------------------------------------------------------------
# Root solution
# ---------------------------------------------------------------------------
readonly TARGET_ROOT_SOL="magisk"
readonly TARGET_MAGISK_VER="stable"
readonly MIN_MAGISK_VERSION_CODE=26000         # Magisk 26.0 minimum requirement

# ---------------------------------------------------------------------------
# GApps
# ---------------------------------------------------------------------------
readonly TARGET_GAPPS_VARIANT="pico"           # OpenGApps Pico
readonly TARGET_GAPPS_SOURCE="opengapps"       # opengapps | mindthegapps

# Android API level shipped by the current WSA generation.
# WSA >= 2211 ships API 33 (Android 13); older builds ship API 32.
# This is the *default*; build.sh may downgrade it after inspecting the WSA
# major version extracted from the package.
readonly DEFAULT_ANDROID_API=33
readonly ANDROID_API_MAP_30="11.0"
readonly ANDROID_API_MAP_32="12.1"
readonly ANDROID_API_MAP_33="13.0"

# OpenGApps Pico for Android 13 x86_64 is published in the opengapps/x86_64
# GitHub releases repo. The asset name follows the pattern:
#   open_gapps-x86_64-13.0-pico-YYYYMMDD.zip
readonly OPENGAPPS_GITHUB_OWNER="opengapps"
readonly OPENGAPPS_GITHUB_REPO="x86_64"

# ---------------------------------------------------------------------------
# Device model (used by fixGappsProp.py for GApps compatibility)
# ---------------------------------------------------------------------------
readonly TARGET_DEVICE_MODEL="redfin"         # Pixel 5
readonly TARGET_DEVICE_NAME="redfin"

# ---------------------------------------------------------------------------
# Compression / output
# ---------------------------------------------------------------------------
readonly DEFAULT_COMPRESS_FORMAT="7z"         # default final artifact format

# ---------------------------------------------------------------------------
# Derived file / directory names (computed, not overridable)
# ---------------------------------------------------------------------------
# These are functions rather than readonly vars because they depend on
# ANDROID_API which may be adjusted at runtime.
gapps_image_name() {
    local api="${1:-$DEFAULT_ANDROID_API}"
    local api_ver
    case "$api" in
        30) api_ver="$ANDROID_API_MAP_30" ;;
        32) api_ver="$ANDROID_API_MAP_32" ;;
        33) api_ver="$ANDROID_API_MAP_33" ;;
        *)  echo "config.sh: unknown API level: $api" >&2; return 1 ;;
    esac
    echo "gapps-${api_ver}-${TARGET_ARCH_NATIVE}.img"
}

gapps_rc_name() {
    local api="${1:-$DEFAULT_ANDROID_API}"
    local api_ver
    case "$api" in
        30) api_ver="$ANDROID_API_MAP_30" ;;
        32) api_ver="$ANDROID_API_MAP_32" ;;
        33) api_ver="$ANDROID_API_MAP_33" ;;
        *)  echo "config.sh: unknown API level: $api" >&2; return 1 ;;
    esac
    echo "gapps-${api_ver}.rc"
}
