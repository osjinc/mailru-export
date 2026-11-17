#!/usr/bin/env bash
# Загрузка выгрузки на IMAP-сервер.
# Использование: ./upload.sh <src> <host> <login> <password> [--prefix mailru]
set -euo pipefail
cd "$(dirname "$0")"

SRC="${1:?./upload.sh <src> <host> <login> <password> [args]}"
HOST="${2:?}"
LOGIN="${3:?}"
PASSWORD="${4:?}"
shift 4
python3 -I imap_upload.py --src "$SRC" --host "$HOST" --login "$LOGIN" --password "$PASSWORD" "$@"
