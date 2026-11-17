# mailru2imap — прямая миграция Mail.ru -> IMAP без файлов на диске

«Труба»: списки папок и писем читаются из light.mail.ru, каждое письмо
сразу загружается (APPEND) на целевой IMAP-сервер. На диске — только
cookie-файл и журнал перенесённого.

```bash
# с паролем Mail.ru (без 2FA)
python3 -I mailru2imap.py --mailru-login you@mail.ru \
    --host imap.gmail.com --login arch@gmail.com --password 'app-password' \
    --prefix mailru

# с куками из браузера (для ящиков с 2FA)
python3 -I mailru2imap.py --mailru-login you@mail.ru \
    --mailru-cookie cookies/you.txt \
    --host imap.gmail.com --login arch@gmail.com --password 'app-password'

# план без загрузки
python3 -I mailru2imap.py ... --dry-run
```

Особенности:
- Resume: журнал `~/.mailru2imap_<ящик>.txt`, перезапуск продолжает.
- Маппинг папок как в imap_upload (inbox->INBOX, sent->Sent, ...,
  `--prefix`, `--flat`).
- Пароли спрашиваются через getpass, если не переданы аргументом.
- При капче/потере сессии останавливается с понятной ошибкой.
- Требует живые обе стороны: Mail.ru-сессия и целевой IMAP.
