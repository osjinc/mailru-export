# light-dump — выгрузка почты Mail.ru в .eml без IMAP

Два скрипта: `light_dump.py` (скачивание всех папок ящика в `.eml`) и
`build_mbox.py` (упаковка результата в `.mbox` по папкам — формат, который
принимают почтовые архиваторы и клиенты).

## Как это работает

1. Вход через классический `POST https://auth.mail.ru/cgi-bin/auth`
   (обходит VK ID / silent_token; если у ящика включена двухфакторная
   аутентификация — используйте готовые куки из браузера, см. ниже).
2. Папки и списки писем читаются из «лёгкой» веб-версии
   `light.mail.ru` — она полностью серверная, без JavaScript.
3. Каждое письмо скачивается как **оригинальный `.eml`**
   (`GET /cgi-bin/getmsg?id=...`, `Content-Type: message/rfc822`) —
   со всеми заголовками, вложениями и кодировками, байт в байт как хранит
   сервер.

Пароль нигде не сохраняется: после первого входа куки пишутся в
`<out>/cookies_<логин>.txt` и все повторные запуски идут по ним.

## Требования

- Python 3.8+ (только стандартная библиотека, зависимостей нет)
- curl не нужен

## Быстрый старт

```bash
./dump.sh you@mail.ru
#    → eml/you@mail.ru/<папка>/<id>.eml
#    → eml/you@mail.ru/<папка>.mbox
#    → eml/you@mail.ru/index.csv, manifest.json
```

С паролем (без 2FA):

```bash
python3 -I light_dump.py --login you@mail.ru --password 'p@ssw0rd'
```

С куками из своего браузера (для ящиков с 2FA):

```bash
python3 -I light_dump.py --login you@mail.ru --cookie cookies/you.txt
```

### Как получить куки из браузера

1. Войдите в почту через браузер (VK ID, SMS — как обычно).
2. Откройте `https://light.mail.ru/messages/inbox` — должен показаться
   список писем.
3. Расширением «Get cookies.txt LOCALLY» (Chrome/Firefox) экспортируйте
   куки страницы в Netscape-формате. Нужны куки домена `.mail.ru`,
   главная — `Mpop`.
4. Готово. Расширение выгружает куки всех доменов страницы — скрипт
   использует только домены `*.mail.ru`, остальное игнорирует, так что
   файл можно отдавать как есть. Для порядка можно оставить только
   строки с доменом `.mail.ru` (формат Netscape: домен, флаги, путь,
   secure, expiry, имя, значение — tab-separated).

## Параметры light_dump.py

| Параметр | Значение |
|---|---|
| `--login` | полный адрес ящика |
| `--password` | пароль (если нет `--cookie`) |
| `--cookie` | Netscape cookie-файл из браузера |
| `--out` | каталог выгрузки (по умолчанию `eml`) |
| `--folders` | `inbox,sent,archive,...` или `all` (по умолчанию) |
| `--workers` | параллельных загрузок 1–4 (по умолчанию 1) |
| `--sleep` | пауза между запросами, сек (по умолчанию 0.4) |
| `--max-pages` | ограничение страниц на папку (для теста) |

## Докачка (resume)

Скрипт можно перезапускать сколько угодно: существующие `.eml`
пропускаются, докачивается только недостающее. `manifest.json` фиксирует,
сколько писем было в каждой папке на момент выгрузки — это доказательство
полноты.

## Важно про безопасность

- Cookie-файл равнозначен паролю — не публикуйте его и не кладите в git.
- При экспорте кук из браузера следите, с каким ящиком вы «активны»:
  новый вход в соседний ящик mail.ru может сбросить сессию предыдущего.
- Скрипт останавливается при капче или сбросе сессии — просто перезапустите
  позже той же командой.

## Почему не IMAP / не официальный API

Mail.ru ограничивает доступ по IMAP, а VK ID-флоу веб-входа в headless- и
встроенных браузерах циклически редиректит. Используются недокументированные
веб-эндпоинты — они могут измениться в любой момент. Используйте на свой
страх и риск, держите разумные паузы (`--sleep`), не выгружайте чужие ящики.

## English summary

Dump a Mail.ru mailbox to original `.eml` files (and per-folder `.mbox`)
without IMAP: login via the classic `auth.mail.ru` form endpoint (bypasses
VK ID), message lists are scraped from the server-rendered `light.mail.ru`
interface, messages are downloaded via `cgi-bin/getmsg` as
`message/rfc822`. Password is used only once — afterwards a cookie jar is
reused; for 2FA accounts import cookies from your browser (cookie `Mpop`,
domain `.mail.ru`). Resumable, stdlib-only, stops on captcha/session loss.

## License

MIT
