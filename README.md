# mailru-export

Экспорт почты Mail.ru в `.eml` / `.mbox` **без доступа по IMAP** и без
платной подписки — через серверную «лёгкую» веб-версию `light.mail.ru`.
Плюс два способа доставки: загрузка готовой выгрузки на IMAP-сервер
или прямая миграция Mail.ru → IMAP без промежуточных файлов.

## Когда это нужно

- Mail.ru ограничил/закрыл доступ по IMAP, а почту нужно сохранить
  локально в оригинальном виде (бекап, миграция в архиватор, перенос
  на другой сервис).
- У вас несколько ящиков (в том числе с двухфакторной аутентификацией) —
  скрипты универсальны: пароль либо куки из браузера на каждый ящик.
- Нужен перезапускаемый процесс: и выгрузка, и загрузка докачиваются
  с места остановки.
- Нужно переехать с Mail.ru на другой почтовый сервис целиком —
  прямой режим `mailru2imap.py` переносит письма сразу на новый сервер.

## Три инструмента

| Инструмент | Что делает |
|---|---|
| [`light-dump/`](light-dump/) | Mail.ru → `.eml` (пофайлово) + `.mbox` (по папкам) на диск |
| [`imap-upload/`](imap-upload/) | готовая выгрузка `.eml` → любой IMAP-сервер |
| [`mailru2imap.py`](README-mailru2imap.md) | Mail.ru → IMAP напрямую, без файлов на диске («труба») |

Все три: вход по паролю (классический `auth.mail.ru`, обходит VK ID) или
по кукам из браузера для ящиков с 2FA (`Mpop`, домен `.mail.ru`),
resume, стоп на капче/потере сессии, только стандартная библиотека Python.

## Как работает выгрузка (light-dump)

1. Вход классическим POST на `auth.mail.ru` (обходит VK ID) **или** по
   готовым кукам из браузера (`Mpop`, домен `.mail.ru`) — для ящиков с 2FA.
2. Списки папок и писем — из `light.mail.ru` (полностью серверный HTML,
   включая пользовательские папки `/messages/folder/N` и пагинацию
   с учётом особенности `?page=1 == ?page=0`).
3. Каждое письмо — оригинальный `.eml` (`message/rfc822`) через
   `cgi-bin/getmsg`, байт в байт как хранит сервер.
4. Опционально — упаковка в `.mbox` по папкам для импорта в
   почтовые архиваторы (MailStore, MailArchiva, mail-archiver и т.п.).

Подробности и примеры — в [`light-dump/README.md`](light-dump/README.md).

## Быстрый старт

```bash
git clone https://github.com/osjinc/mailru-export.git

# 1) выгрузить ящик на диск (.eml + .mbox)
cd mailru-export/light-dump
./dump.sh you@mail.ru

# 2a) залить выгрузку на IMAP-сервер (Gmail, свой сервер, ...)
cd ../imap-upload
./upload.sh eml/you@mail.ru imap.gmail.com arch@gmail.com 'app-password' --prefix mailru

# 2б) или напрямую Mail.ru -> IMAP, без файлов на диске
cd ..
python3 -I mailru2imap.py --mailru-login you@mail.ru \
    --host imap.gmail.com --login arch@gmail.com --password 'app-password' \
    --prefix mailru
```

Результат выгрузки:

```
eml/you@mail.ru/
├── inbox/  sent/  archive/  folder_1/ ...   # <id>.eml
├── inbox.mbox  sent.mbox  archive.mbox ...
├── index.csv        # реестр: файл, папка, id, размер
├── manifest.json    # счётчики по папкам на момент выгрузки
└── cookies_you@mail.ru.txt   # сессия (не публиковать!)
```

## Требования

- Python 3.8+, только стандартная библиотека.

## Важно про безопасность

Cookie-файл равнозначен паролю. Не кладите его в git, не публикуйте.
Скрипты предназначены для бекапа **своих** ящиков; недокументированные
эндпоинты могут измениться в любой момент — используйте на свой страх
и риск и держите разумные паузы между запросами.

## FAQ

**Работает ли с ящиками @mail.ru, @list.ru, @bk.ru, @inbox.ru?** — Да,
логин передавайте полным адресом.

**У меня двухфакторная аутентификация** — экспортируйте куки из браузера
(`--cookie` / `--mailru-cookie`), пароль скриптам не нужен.

**Можно докачивать позже?** — Да, просто перезапустите: существующие
`.eml` и журнал загрузок пропускаются, докачивается только недостающее.

**Gmail?** — да, но нужен App Password (2FA → App passwords), обычный
пароль IMAP не примет. Не забудьте исключить `[Gmail]/All Mail` из
обратной синхронизации, иначе дубли.

## Структура репозитория

```
light-dump/
├── light_dump.py   # выгрузка .eml (вход, папки, пагинация, resume)
├── build_mbox.py   # упаковка .eml -> .mbox по папкам
├── dump.sh         # обёртка: ./dump.sh <login> [out]
└── README.md
imap-upload/
├── imap_upload.py  # загрузка выгрузки на IMAP-сервер (папки, APPEND, resume)
├── upload.sh       # обёртка: ./upload.sh <src> <host> <login> <pass>
└── README.md
mailru2imap.py      # Mail.ru -> IMAP напрямую (труба, resume, dry-run)
README-mailru2imap.md
```

## License

MIT
