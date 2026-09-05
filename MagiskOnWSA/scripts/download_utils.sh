#!/bin/bash
# =============================================================================
# download_utils.sh — Download helper functions for WSABuilds
#
# Provides:
#   aria2_download  – resilient aria2c wrapper (resume, retry, integrity check)
#   verify_sha256   – verify a file against a known checksum
#   clean_on_fail   – delete a partial download when a step fails
#   mark_clean_*    – set flags that trigger clean_on_fail in the parent trap
#
# Usage:
#   source download_utils.sh
#
# Copyright (C) 2024 WSABuilds Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# =============================================================================

# Guard against double-sourcing
[[ -n "${_DOWNLOAD_UTILS_LOADED:-}" ]] && return 0
readonly _DOWNLOAD_UTILS_LOADED=1

# ---------------------------------------------------------------------------
# aria2_download <download_list_file> <log_file>
#
# Calls aria2c with a proven set of flags:
#   -x16 -s16   – 16 connections per server, 16 segments per file
#   -j5         – up to 5 parallel downloads
#   -c          – continue partial downloads
#   -R          – remote-time (preserve server timestamp)
#   -m0         – unlimited retries
#   --async-dns=false   – avoid DNS resolution failures in some CI envs
#   --check-integrity=true – hash-check each completed file
#   --conditional-get=true – skip re-download if file unchanged
#
# Returns non-zero on any download failure.
# ---------------------------------------------------------------------------
aria2_download() {
    local input_file="$1"
    local log_file="$2"

    if [[ -z "$input_file" || ! -f "$input_file" ]]; then
        echo "download_utils: aria2_download: input file not found: $input_file" >&2
        return 1
    fi

    aria2c \
        --no-conf \
        --log-level=info \
        --log="$log_file" \
        -x16 -s16 -j5 \
        -c -R -m0 \
        --async-dns=false \
        --check-integrity=true \
        --continue=true \
        --allow-overwrite=true \
        --conditional-get=true \
        -i "$input_file"
}

# ---------------------------------------------------------------------------
# verify_sha256 <file> <expected_hash>
#
# Computes the SHA-256 of <file> and compares it to <expected_hash>
# (case-insensitive).  Returns 0 on match, 1 on mismatch.
# ---------------------------------------------------------------------------
verify_sha256() {
    local file="$1"
    local expected="$2"

    if [[ ! -f "$file" ]]; then
        echo "download_utils: verify_sha256: file not found: $file" >&2
        return 1
    fi

    local actual
    actual=$(sha256sum "$file" | awk '{print $1}')

    if [[ "${actual,,}" != "${expected,,}" ]]; then
        echo "download_utils: verify_sha256: MISMATCH for $(basename "$file")" >&2
        echo "  expected: ${expected,,}" >&2
        echo "  actual:   ${actual,,}" >&2
        return 1
    fi

    echo "download_utils: verify_sha256: OK — $(basename "$file")"
    return 0
}

# ---------------------------------------------------------------------------
# assert_file_exists <path> [label]
#
# Aborts (exits the *calling* script) if <path> does not exist.
# Optional <label> is used in the error message.
# ---------------------------------------------------------------------------
assert_file_exists() {
    local path="$1"
    local label="${2:-$(basename "$path")}"

    if [[ ! -f "$path" ]]; then
        echo "ERROR: Required file missing — $label" >&2
        echo "       Expected path: $path" >&2
        echo "       Hint: Check that the download step completed successfully." >&2
        return 1
    fi
}

# ---------------------------------------------------------------------------
# clean_partial_download <file>...
#
# Removes one or more files that are known to be partial / corrupt so that
# a re-run will trigger a fresh download rather than re-using bad data.
# Safe to call even if the file does not exist.
# ---------------------------------------------------------------------------
clean_partial_download() {
    local f
    for f in "$@"; do
        if [[ -f "$f" ]]; then
            echo "download_utils: removing partial/corrupt file: $f"
            rm -f "$f"
        fi
    done
}

# ---------------------------------------------------------------------------
# write_aria2_entry <output_file> <url> <dest_dir> <out_filename>
#
# Appends one download entry to an aria2c input file in the format:
#
#   <url>
#     dir=<dest_dir>
#     out=<out_filename>
#
# ---------------------------------------------------------------------------
write_aria2_entry() {
    local output_file="$1"
    local url="$2"
    local dest_dir="$3"
    local out_filename="$4"

    {
        echo "$url"
        echo "  dir=${dest_dir}"
        echo "  out=${out_filename}"
    } >> "$output_file"

    echo "download_utils: queued — ${out_filename}"
    echo "               url    — ${url}"
}

# ---------------------------------------------------------------------------
# to_native_path <path>
#
# Converts Unix/MSYS2 paths to standard Windows format with forward slashes
# when running in Git Bash/MSYS2, so Windows-native binaries can read them.
# On Linux runners, returns the path untouched.
# ---------------------------------------------------------------------------
to_native_path() {
    local p="$1"
    if command -v cygpath >/dev/null 2>&1; then
        cygpath -m "$p"
    else
        echo "$p"
    fi
}
