#!/usr/bin/env bash
# pdash SQLite backup.
#
# Uses `sqlite3 ... ".backup"` so the snapshot is consistent even while
# the backend is writing. Tar-gzipped output lands in data/backups/.
# Rotation:
#   - Keep the last 30 daily backups.
#   - Keep one backup per month (the first one each month) for the last 12 months.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DB="${ROOT_DIR}/data/pdash.db"
BACKUP_DIR="${ROOT_DIR}/data/backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DB="${BACKUP_DIR}/pdash-${STAMP}.db"
OUT_TGZ="${OUT_DB}.tar.gz"

if [ ! -f "${DB}" ]; then
    echo "backup: database file not found: ${DB}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

# 1. Online snapshot. sqlite3 reads from disk while the backend holds the
#    writer lock; .backup uses pages, so it never blocks for long.
sqlite3 "${DB}" ".backup '${OUT_DB}'"

# 2. Compress.
tar -czf "${OUT_TGZ}" -C "${BACKUP_DIR}" "$(basename "${OUT_DB}")"
rm -f "${OUT_DB}"

echo "backup: wrote ${OUT_TGZ}"

# 3. Rotate.
cd "${BACKUP_DIR}"

# 3a. Last 30 *daily* snapshots — keep newest 30 matching pdash-*.db.tar.gz.
mapfile -t ALL_BACKUPS < <(ls -1t pdash-*.db.tar.gz 2>/dev/null || true)
KEEP_DAILY=30
i=0
declare -A KEEP_SET=()
for f in "${ALL_BACKUPS[@]}"; do
    if (( i < KEEP_DAILY )); then
        KEEP_SET["${f}"]=1
    fi
    i=$(( i + 1 ))
done

# 3b. Last 12 months — keep the oldest backup that falls inside each of the
#     past 12 calendar months.
declare -A MONTH_SEEN=()
for f in "${ALL_BACKUPS[@]}"; do
    # Parse YYYYMM from filename pdash-YYYYMMDDTHHMMSSZ.db.tar.gz
    ym="${f:6:6}"  # YYYYMM
    if [ -z "${MONTH_SEEN[$ym]:-}" ]; then
        MONTH_SEEN["$ym"]="$f"
        KEEP_SET["$f"]=1
    fi
done
# Drop any month-keep older than 12 distinct months.
mapfile -t SORTED_MONTHS < <(printf '%s\n' "${!MONTH_SEEN[@]}" | sort -r)
m=0
for ym in "${SORTED_MONTHS[@]}"; do
    if (( m >= 12 )); then
        unset 'KEEP_SET[${MONTH_SEEN[$ym]}]' || true
    fi
    m=$(( m + 1 ))
done

# 3c. Delete anything not in KEEP_SET.
for f in "${ALL_BACKUPS[@]}"; do
    if [ -z "${KEEP_SET[$f]:-}" ]; then
        rm -f "$f"
        echo "backup: rotated out ${f}"
    fi
done

echo "backup: rotation complete; ${#KEEP_SET[@]} files retained"
