#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Универсальный экспорт почты Mail.ru в .eml через light-интерфейс (без IMAP).

Использование:
  python3 -I light_dump.py --login you@mail.ru --password '...' [--out eml]
  python3 -I light_dump.py --login you@mail.ru --cookie cookies/you.txt [--out eml]

На выходе:
  <out>/<логин>/<папка>/<id>.eml
  <out>/<логин>/index.csv
  <out>/<логин>/manifest.json
"""
import argparse
import csv
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Папки: slug -> человекочитаемое имя
KNOWN_FOLDERS = {
    "inbox": "inbox",
    "sent": "sent",
    "drafts": "drafts",
    "spam": "spam",
    "trash": "trash",
    "archive": "archive",
}

MSG_LINK_RE = re.compile(r'href="/message/(\d{6,})/\?folder=(\d+)"')
FOLDER_HREF_RE = re.compile(r'href="/messages/([a-z]+)(?:/folder/(\d+))?')
# произвольные папки: /messages/folder/N
CUSTOM_FOLDER_RE = re.compile(r'href="/messages/folder/(\d+)')


class MailClient:
    def __init__(self, cookie_path):
        self.jar = http.cookiejar.MozillaCookieJar(cookie_path)
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", UA),
                                  ("Accept", "text/html,application/xhtml+xml,*/*;q=0.8"),
                                  ("Accept-Language", "ru-RU,ru;q=0.9")]

    def get(self, url, expect_html=True, retries=3):
        for attempt in range(retries):
            try:
                with self.opener.open(url, timeout=60) as r:
                    data = r.read()
                    return r.status, r.headers.get("Content-Type", ""), data
            except Exception as e:
                if attempt == retries - 1:
                    raise
                time.sleep(2 * (attempt + 1) + random.random())

    def logged_in(self):
        st, ct, body = self.get("https://light.mail.ru/messages/inbox")
        return st == 200 and b"logout" in body

    def login(self, login, password):
        data = urllib.parse.urlencode({
            "Login": login, "Domain": "", "Password": password,
        }).encode()
        req = urllib.request.Request("https://auth.mail.ru/cgi-bin/auth", data=data)
        req.add_header("User-Agent", UA)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(NoRedirect,
                                         urllib.request.HTTPCookieProcessor(self.jar))
        try:
            r = op.open(req, timeout=60)
            loc = r.headers.get("Location", "")
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location", "")
        if "fail=1" in loc:
            raise SystemExit("Не удалось войти: неверный логин/пароль или капча (%s)" % loc)
        self.jar.save(cookie_path, ignore_discard=True, ignore_expires=True)

    def discover_folders(self):
        """Возвращает список (slug, fid_or_None) из сайдбара light-интерфейса."""
        st, ct, body = self.get("https://light.mail.ru/messages/inbox")
        html = body.decode("utf-8", "replace")
        folders = []
        seen = set()
        for slug in KNOWN_FOLDERS:
            if ("/messages/%s" % slug) in html:
                folders.append((slug, None))
                seen.add(slug)
        for m in CUSTOM_FOLDER_RE.finditer(html):
            fid = m.group(1)
            if ("folder", fid) not in [(s, f) for s, f in folders]:
                folders.append(("folder_%s" % fid, fid))
        return folders

    def list_messages(self, slug, fid, max_pages=None, page_size=50):
        """Возвращает список (msg_id, folder_num) со всех страниц."""
        base = ("https://light.mail.ru/messages/%s" % slug) if fid is None else \
               ("https://light.mail.ru/messages/folder/%s" % fid)
        msgs = []
        seen = set()
        page = 0
        empty_pages = 0
        pages_fetched = 0
        while True:
            url = base if page == 0 else "%s?page=%d" % (base, page)
            st, ct, body = self.get(url)
            self.check_captcha(body)
            html = body.decode("utf-8", "replace")
            found = MSG_LINK_RE.findall(html)
            new = 0
            for mid, f in found:
                if mid not in seen:
                    seen.add(mid)
                    msgs.append((mid, f))
                    new += 1
            pages_fetched += 1
            if new == 0:
                empty_pages += 1
                if empty_pages >= 2 or (max_pages and pages_fetched >= max_pages):
                    break
            else:
                empty_pages = 0
                if max_pages and pages_fetched >= max_pages:
                    break
            # в light-версии page=1 показывает ту же первую страницу; листаем 0,2,3,...
            page = 2 if page == 0 else page + 1
            time.sleep(0.5)
        return msgs

    def check_captcha(self, body, ct=""):
        """Кидает CaptchaError, если сервер начал показывать капчу/логин."""
        if b"captcha" in body[:3000].lower() or b"/login?fail=1" in body[:3000]:
            raise CaptchaError("сервер потребовал капчу")
        if b"\xd0\xbe\xd0\xb1\xd0\xbd\xd0\xbe\xd0\xb2\xd0\xb8\xd1\x82\xd1\x8c" in body[:6000]:
            raise CaptchaError("сессия недействительна (страница 'обновите браузер')")
        if b"<title>" in body[:4000]:
            m = re.search(rb"<title>([^<]{0,60})", body)
            title = m.group(1) if m else b""
            if b"Login".lower() in title.lower() or b"\xd0\x92\xd0\xbe\xd0\xb9\xd1\x82\xd0\xb8" in title \
               or b"VK ID" in title:
                raise CaptchaError("ответ — страница входа, сессия отвалилась")

    def download_eml(self, mid, dest):
        st, ct, body = self.get("https://light.mail.ru/cgi-bin/getmsg?id=%s" % mid)
        if "message/rfc822" not in ct and not body.startswith(b"Delivered-To") \
           and not body.startswith(b"Received"):
            self.check_captcha(body, ct)
            raise RuntimeError("не .eml ответ (ct=%s, статус=%s)" % (ct, st))
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, dest)
        return len(body)


class CaptchaError(RuntimeError):
    pass


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._@-]", "_", s)


def parse_letter_header(html):
    """Достаёт тему/дату/адресата со страницы письма для индекса (best effort)."""
    def first(pat):
        m = re.search(pat, html)
        return m.group(1).strip() if m else ""
    subject = first(r'<title>(?:[^<]*?-\s*)?([^<]*?)\s*-\s*Почта Mail\.ru</title>')
    return subject


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", required=True, help="полный адрес ящика")
    ap.add_argument("--password", help="пароль (иначе нужен --cookie)")
    ap.add_argument("--cookie", help="путь к готовому cookie-файлу Netscape")
    ap.add_argument("--out", default="eml", help="каталог выгрузки")
    ap.add_argument("--folders", help="через запятую: inbox,sent,... или all (по умолчанию all)")
    ap.add_argument("--max-pages", type=int, help="ограничение страниц на папку (тест)")
    ap.add_argument("--sleep", type=float, default=0.4, help="пауза между письмами, сек")
    ap.add_argument("--workers", type=int, default=1, help="параллельных загрузок (1-4)")
    args = ap.parse_args()

    global cookie_path
    login = args.login
    account_dir = safe_name(login)
    os.makedirs(args.out, exist_ok=True)
    cookie_path = os.path.join(args.out, "cookies_%s.txt" % account_dir)

    client = MailClient(cookie_path)
    if args.cookie:
        cookie_path = args.cookie
        client = MailClient(cookie_path)
        client.jar.load(cookie_path, ignore_discard=True, ignore_expires=True)
    elif args.password:
        if not os.path.exists(cookie_path) or not _cookie_valid(cookie_path):
            print("[i] Логинюсь %s ..." % login)
            client.login(login, args.password)
        client.jar.load(cookie_path, ignore_discard=True, ignore_expires=True)
    else:
        raise SystemExit("Нужен --password или --cookie")

    if not client.logged_in():
        if args.password:
            print("[i] Куки устарели, перелогин...")
            client.login(login, args.password)
            client.jar.load(cookie_path, ignore_discard=True, ignore_expires=True)
            if not client.logged_in():
                raise SystemExit("Вход не удался после перелогина")
        else:
            raise SystemExit("Куки недействительны — перелогиньтесь и обновите cookie-файл")
    print("[i] Вход OK")

    folders = client.discover_folders()
    if args.folders and args.folders != "all":
        want = set(args.folders.split(","))
        folders = [f for f in folders if f[0] in want]
    print("[i] Папки:", folders)

    index_path = os.path.join(args.out, account_dir, "index.csv")
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    new_index = not os.path.exists(index_path)
    index_f = open(index_path, "a", newline="", encoding="utf-8")
    writer = csv.writer(index_f)
    if new_index:
        writer.writerow(["file", "message_id_hdr", "folder", "remote_id", "bytes"])

    manifest = {"account": login, "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "folders": {}}
    manifest_path = os.path.join(args.out, account_dir, "manifest.json")
    if os.path.exists(manifest_path):
        try:
            manifest = json.load(open(manifest_path, encoding="utf-8"))
        except Exception:
            pass

    total_ok = total_skip = total_err = 0
    for slug, fid in folders:
        print("[i] Папка %s: собираю список..." % slug)
        msgs = client.list_messages(slug, fid, max_pages=args.max_pages)
        fdir = os.path.join(args.out, account_dir, slug)
        os.makedirs(fdir, exist_ok=True)
        manifest["folders"][slug] = {"count": len(msgs), "downloaded": 0, "errors": 0}
        print("[i] Папка %s: %d писем" % (slug, len(msgs)))
        todo = []
        for mid, fnum in msgs:
            dest = os.path.join(fdir, "%s.eml" % mid)
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                total_skip += 1
            else:
                todo.append((mid, dest))

        def work(item):
            mid, dest = item
            size = client.download_eml(mid, dest)
            return mid, dest, size

        done_in_folder = 0
        workers = max(1, min(args.workers, 4))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, it): it for it in todo}
            try:
                for fut in as_completed(futures):
                    done_in_folder += 1
                    try:
                        mid, dest, size = fut.result()
                        writer.writerow([os.path.relpath(dest, os.path.join(args.out, account_dir)),
                                         mid, slug, mid, size])
                        manifest["folders"][slug]["downloaded"] += 1
                        total_ok += 1
                    except CaptchaError as e:
                        raise
                    except Exception as e:
                        print("[!] %s: %s" % (futures[fut][0], e))
                        manifest["folders"][slug]["errors"] += 1
                        total_err += 1
                    if done_in_folder % 50 == 0:
                        index_f.flush()
                        print("    ...%d/%d" % (done_in_folder, len(todo)))
                    time.sleep(args.sleep)
            except CaptchaError as e:
                print("[!!] КАПЧА/СЕССИЯ: %s — останавливаю. Перезапусти позже той же командой." % e)
                pool.shutdown(wait=False, cancel_futures=True)
                break
        index_f.flush()

    index_f.close()
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("[✓] Готово: скачано %d, пропущено (уже было) %d, ошибок %d" %
          (total_ok, total_skip, total_err))
    print("    Выгрузка: %s/%s" % (args.out, account_dir))


def _cookie_valid(path):
    try:
        return "Mpop" in open(path).read()
    except Exception:
        return False


if __name__ == "__main__":
    main()
