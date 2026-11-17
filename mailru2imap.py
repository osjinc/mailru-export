#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Прямая миграция Mail.ru -> IMAP без промежуточных файлов на диске:
списки папок/письма берутся из light.mail.ru, каждое письмо сразу APPEND'ится
на целевой IMAP-сервер.

Использование:
  python3 -I mailru2imap.py --mailru-login you@mail.ru \
      [--mailru-password ... | --mailru-cookie cookies.txt] \
      --host imap.gmail.com --login arch@gmail.com --password 'app-password' \
      [--prefix mailru] [--dry-run]

Resume: журнал ~/.mailru2imap_<ящик>.txt хранит "папка/id" уже перенесённого.
Стоп на капче/потере сессии — как в light_dump.py.
"""
import argparse
import getpass
import imaplib
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "light-dump"))
sys.path.insert(0, os.path.join(_HERE, "imap-upload"))
from light_dump import MailClient  # переиспользуем вход/листинг/getmsg
from imap_upload import utf7_path, ensure_folder, DEFAULT_MAP

MSG_LINK_RE = re.compile(r'href="/message/(\d{6,})/\?folder=(\d+)"')
CUSTOM_FOLDER_RE = re.compile(r'href="/messages/folder/(\d+)')
KNOWN_FOLDERS = ("inbox", "sent", "drafts", "spam", "trash", "archive")


class CaptchaError(Exception):
    pass


def check_captcha(body):
    low = body[:6000].lower()
    if b"captcha" in low or b"/login?fail=1" in low:
        raise CaptchaError("капча/потеря сессии на стороне mail.ru")
    i = body.find(b"<title>")
    title = body[i:i + 200] if i >= 0 else b""
    ok_title = b"\xd0\x9f\xd0\xbe\xd1\x87\xd1\x82\xd0\xb0 Mail.ru" in title
    if not ok_title:
        raise CaptchaError("сессия mail.ru недействительна (title=%s)" % title[:60].decode("utf-8", "replace"))


def list_messages(client, slug, fid):
    base = ("https://light.mail.ru/messages/%s" % slug) if fid is None else \
           ("https://light.mail.ru/messages/folder/%s" % fid)
    seen, msgs = set(), []
    page, empty = 0, 0
    while True:
        url = base if page == 0 else "%s?page=%d" % (base, page)
        st, ct, body = client.get(url)
        check_captcha(body)
        new = 0
        for mid, _ in MSG_LINK_RE.findall(body.decode("utf-8", "replace")):
            if mid not in seen:
                seen.add(mid)
                msgs.append(mid)
                new += 1
        empty = empty + 1 if new == 0 else 0
        if empty >= 2:
            break
        page = 2 if page == 0 else page + 1
        time.sleep(0.3)
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mailru-login", required=True)
    ap.add_argument("--mailru-password")
    ap.add_argument("--mailru-cookie", help="Netscape cookie-файл (для 2FA-ящиков)")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=993)
    ap.add_argument("--no-ssl", action="store_true")
    ap.add_argument("--login", required=True, help="логин на целевом IMAP")
    ap.add_argument("--password", help="пароль/App Password целевого IMAP")
    ap.add_argument("--prefix", default="", help="префикс папок на целевом сервере")
    ap.add_argument("--flat", action="store_true", help="всё в один INBOX")
    ap.add_argument("--folders", default="all")
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.mailru_password and not args.mailru_cookie:
        args.mailru_password = getpass.getpass("Пароль Mail.ru (%s): " % args.mailru_login)
    if not args.password:
        args.password = getpass.getpass("Пароль IMAP (%s): " % args.login)

    cpath = args.mailru_cookie or os.path.join(
        "cookies_%s.txt" % re.sub(r"[^A-Za-z0-9._@-]", "_", args.mailru_login))
    client = MailClient(cpath)
    if args.mailru_cookie:
        client.jar.load(cpath, ignore_discard=True, ignore_expires=True)
    else:
        if not (os.path.exists(cpath) and "Mpop" in open(cpath).read()):
            print("[i] Логинюсь в Mail.ru ...")
            client.login(args.mailru_login, args.mailru_password)
        client.jar.load(cpath, ignore_discard=True, ignore_expires=True)
    if not client.logged_in():
        if args.mailru_password:
            print("[i] Куки устарели, перелогин...")
            client.login(args.mailru_login, args.mailru_password)
            client.jar.load(cpath, ignore_discard=True, ignore_expires=True)
        if not client.logged_in():
            raise SystemExit("Вход в Mail.ru не удался")
    print("[i] Mail.ru: вход OK")

    if args.no_ssl:
        imap = imaplib.IMAP4(args.host, args.port)
    else:
        imap = imaplib.IMAP4_SSL(args.host, args.port)
    if not args.dry_run:
        imap.login(args.login, args.password)
        print("[i] IMAP: вход OK (%s)" % args.host)

    folders = client.discover_folders()
    if args.folders != "all":
        want = set(args.folders.split(","))
        folders = [f for f in folders if f[0] in want]
    print("[i] Папки:", [f[0] for f in folders])

    journal_path = os.path.expanduser(
        "~/.mailru2imap_%s.txt" % re.sub(r"[^A-Za-z0-9._@-]", "_", args.mailru_login))
    done = set()
    if os.path.exists(journal_path):
        done = set(x.strip() for x in open(journal_path) if x.strip())
        print("[i] Журнал: уже перенесено %d" % len(done))
    journal = open(journal_path, "a")

    total_ok = total_skip = total_err = 0
    try:
        for slug, fid in folders:
            print("[i] Папка %s: листаю..." % slug)
            mids = list_messages(client, slug, fid)
            base_name = "INBOX" if args.flat else DEFAULT_MAP.get(slug, slug)
            target = base_name if (args.flat or not args.prefix) \
                else "%s/%s" % (args.prefix, base_name)
            todo = [m for m in mids if "%s/%s" % (slug, m) not in done]
            print("[i] Папка %s -> %s: %d писем (%d новых)" % (slug, target, len(mids), len(todo)))
            if args.dry_run or not todo:
                continue
            ensure_folder(imap, utf7_path(target))
            imap.select('"%s"' % target)
            for i, mid in enumerate(todo, 1):
                try:
                    st, ct, data = client.get(
                        "https://light.mail.ru/cgi-bin/getmsg?id=%s" % mid)
                    if "message/rfc822" not in ct and not data.startswith(
                            (b"Delivered-To", b"Received")):
                        check_captcha(data)
                        raise RuntimeError("не .eml (ct=%s)" % ct)
                    norm = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                    typ, dat = imap.append('"%s"' % target, None, None, norm)
                    if typ != "OK":
                        raise RuntimeError("APPEND: %s" % dat)
                    journal.write("%s/%s\n" % (slug, mid))
                    total_ok += 1
                except CaptchaError:
                    raise
                except Exception as e:
                    print("[!] %s: %s" % (mid, e))
                    total_err += 1
                if i % 50 == 0:
                    journal.flush()
                    print("    ...%d/%d" % (i, len(todo)))
                time.sleep(args.sleep)
    except CaptchaError as e:
        print("[!!] %s — останов. Перезапуск той же командой продолжит с журнала." % e)
    finally:
        journal.close()
        if not args.dry_run:
            try:
                imap.logout()
            except Exception:
                pass
    print("[✓] Перенесено: %d, ошибок: %d" % (total_ok, total_err))


if __name__ == "__main__":
    main()
