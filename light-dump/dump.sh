#!/usr/bin/env bash
# Выгрузка ящика Mail.ru в .eml без IMAP.
# Использование: ./dump.sh you@mail.ru [папка-назначения]
set -euo pipefail
cd "$(dirname "$0")"

LOGIN="${1:?Укажите логин: ./dump.sh you@mail.ru [out-dir]}"
OUT="${2:-eml}"
shift 2>/dev/null || true

python3 -I light_dump.py --login "$LOGIN" --out "$OUT" "$@"
echo
echo "[i] Собираю mbox-файлы по папкам..."
python3 -I build_mbox.py "$OUT/$LOGIN"
