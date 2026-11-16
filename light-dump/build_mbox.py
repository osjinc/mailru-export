#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает .mbox из выгруженных .eml (результат export_mailru.py).

Использование:
  python3 -I build_mbox.py eml/<account>            # один аккаунт
  python3 -I build_mbox.py eml                          # все аккаунты

Для каждой папки создаёт mbox рядом: eml/<аккаунт>/<папка>.mbox
"""
import mailbox
import os
import sys


def build_account(account_dir):
    made = []
    for name in sorted(os.listdir(account_dir)):
        fdir = os.path.join(account_dir, name)
        if not os.path.isdir(fdir):
            continue
        emls = sorted(f for f in os.listdir(fdir) if f.endswith(".eml"))
        if not emls:
            continue
        mbox_path = os.path.join(account_dir, name + ".mbox")
        if os.path.exists(mbox_path):
            os.remove(mbox_path)  # собираем заново с нуля
        box = mailbox.mbox(mbox_path)
        n = 0
        for f in emls:
            with open(os.path.join(fdir, f), "rb") as fh:
                msg = mailbox.mboxMessage(fh.read())
                # сохраняем исходный Message-ID и добавляем метаданные папки
                msg["X-MailRu-Folder"] = name
                msg["X-MailRu-Id"] = f[:-4]
            box.add(msg)
            n += 1
        box.flush()
        box.close()
        made.append((name, n, os.path.getsize(mbox_path)))
    return made


def is_account_dir(path):
    """Каталог аккаунта: содержит подпапки с .eml."""
    for name in os.listdir(path):
        sub = os.path.join(path, name)
        if os.path.isdir(sub) and any(
                f.endswith(".eml") for f in os.listdir(sub)):
            return True
    return False


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    targets = sys.argv[1:]
    for t in targets:
        if is_account_dir(t):
            print("[i]", os.path.basename(t))
            for name2, n, size in build_account(t):
                print("    %-12s %5d писем  %8.1f MB" % (name2, n, size / 1e6))
        else:
            for name in sorted(os.listdir(t)):
                adir = os.path.join(t, name)
                if os.path.isdir(adir) and is_account_dir(adir):
                    print("[i]", name)
                    for name2, n, size in build_account(adir):
                        print("    %-12s %5d писем  %8.1f MB"
                              % (name2, n, size / 1e6))


if __name__ == "__main__":
    main()
