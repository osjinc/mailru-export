#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Загрузка выгрузки (light_dump.py) на IMAP-сервер: папки создаются,
письма добавляются как оригинальные .eml (RFC822), докачка по файлу-журналу.

Использование:
  python3 -I imap_upload.py --src eml/you@mail.ru --host imap.gmail.com \
      --login you@gmail.com --password 'app-password' \
      --prefix mailru --ssl

  python3 -I imap_upload.py --src eml --host ... --login ...   # все аккаунты из eml/

Параметры:
  --src         каталог аккаунта (eml/<login>) или общий каталог (eml/)
  --host/--port IMAP-сервер (по умолчанию порт 993)
  --no-ssl      без TLS (порт 143)
  --login/--password
  --prefix      префикс IMAP-папок (по умолчанию нет: inbox -> INBOX,
                sent -> Sent, archive -> Archive, folder_1 -> folder_1)
  --flat        всё в одну папку INBOX
  --dry-run     показать план без загрузки
  --sleep       пауза между письмами, сек (по умолчанию 0.1)
  --workers     не используется: IMAP APPEND последовательный по протоколу

Докачка: в каталоге аккаунта ведётся журнал uploaded_<login>.txt —
уже загруженные файлы пропускаются. Перезапуск безопасен.
"""
import argparse
import email
import os
import re
import sys
import time
import imaplib

# локальное имя папки -> общепринятое IMAP-имя
DEFAULT_MAP = {
    "inbox": "INBOX",
    "sent": "Sent",
    "drafts": "Drafts",
    "spam": "Junk",
    "trash": "Trash",
    "archive": "Archive",
}


def utf7_path(name):
    """IMAP-modified UTF-7 для не-ASCII имён папок (простая реализация)."""
    try:
        name.encode("ascii")
        return name
    except UnicodeEncodeError:
        # imaplib умеет encode_utf7 начиная с Python 3.5 в _imap... нет —
        # используем собственный минимальный конвертер
        out = bytearray()
        buf = []
        def flush():
            if buf:
                b = ("".join(buf)).encode("utf-16-be")
                out.extend(b"&" + b.replace(b"\x2f", b"\x2c").replace(b"\x00", b"") + b"-")
                buf.clear()
        for ch in name:
            if 0x20 <= ord(ch) <= 0x7e:
                flush()
                if ch in "&/":
                    out.extend(b"&-" if ch == "&" else b"/")
                else:
                    out.extend(ch.encode("ascii"))
            else:
                buf.append(ch)
        flush()
        return out.decode("ascii")


def ensure_folder(imap, name):
    typ, _ = imap.select('"%s"' % name, readonly=True)
    if typ == "OK":
        imap.close()
        return
    typ, _ = imap.create('"%s"' % name)
    if typ != "OK":
        raise RuntimeError("не удалось создать папку %s" % name)


def upload_account(src, args):
    login = os.path.basename(src.rstrip("/"))
    journal_path = os.path.join(src, "uploaded_%s.txt" % re.sub(r"[^A-Za-z0-9._@-]", "_", args.login or login))
    done = set()
    if os.path.exists(journal_path):
        done = set(x.strip() for x in open(journal_path) if x.strip())
        print("[i] журнал: уже загружено %d" % len(done))

    if args.ssl:
        imap = imaplib.IMAP4_SSL(args.host, args.port)
    else:
        imap = imaplib.IMAP4(args.host, args.port)
    if not args.dry_run:
        imap.login(args.login, args.password)
        print("[i] IMAP вход OK (%s)" % args.host)

    folders = sorted(
        d for d in os.listdir(src)
        if os.path.isdir(os.path.join(src, d))
    )
    plan = []
    for d in folders:
        fdir = os.path.join(src, d)
        emls = sorted(f for f in os.listdir(fdir) if f.endswith(".eml"))
        target = "INBOX" if args.flat else DEFAULT_MAP.get(d, d)
        if not args.flat:
            target = "%s/%s" % (args.prefix, target) if args.prefix else target
        plan.append((d, target, [os.path.join(fdir, f) for f in emls]))

    if args.dry_run:
        for d, t, files in plan:
            new = [f for f in files if os.path.basename(f) not in done]
            print("  %-15s -> %-25s %d писем (%d новых)" % (d, t, len(files), len(new)))
        imap.logout()
        return

    total_ok = total_skip = total_err = 0
    journal = open(journal_path, "a")
    for d, target, files in plan:
        todo = [f for f in files if os.path.basename(f) not in done]
        if not todo:
            print("[i] %-15s -> %-25s всё уже загружено" % (d, target))
            continue
        print("[i] %-15s -> %-25s %d новых" % (d, target, len(todo)))
        ensure_folder(imap, utf7_path(target))
        imap.select('"%s"' % target)
        for i, path in enumerate(todo, 1):
            with open(path, "rb") as fh:
                data = fh.read()
            # нормализуем EOL для APPEND (imaplib требует CRLF внутри literal)
            typ, dat = imap.append(
                '"%s"' % target, None, None, data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            if typ != "OK":
                print("[!] %s: %s" % (os.path.basename(path), dat))
                total_err += 1
                continue
            journal.write(os.path.basename(path) + "\n")
            total_ok += 1
            if i % 50 == 0:
                journal.flush()
                print("    ...%d/%d" % (i, len(todo)))
            time.sleep(args.sleep)
        imap.close()
    journal.close()
    imap.logout()
    print("[✓] загружено %d, пропущено %d, ошибок %d" % (total_ok, total_skip, total_err))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="eml/<аккаунт> или общий eml/")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=993)
    ap.add_argument("--no-ssl", action="store_true")
    ap.add_argument("--login", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--prefix", default="", help="префикс папок на сервере")
    ap.add_argument("--flat", action="store_true", help="всё в INBOX без папок")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.1)
    args = ap.parse_args()
    args.ssl = not args.no_ssl

    if os.path.basename(args.src.rstrip("/")) == "eml" or any(
            os.path.isdir(os.path.join(args.src, d)) for d in os.listdir(args.src)):
        for d in sorted(os.listdir(args.src)):
            sub = os.path.join(args.src, d)
            if os.path.isdir(sub) and not d.startswith("."):
                print("[i] аккаунт %s" % d)
                upload_account(sub, args)
    else:
        upload_account(args.src, args)


if __name__ == "__main__":
    main()
