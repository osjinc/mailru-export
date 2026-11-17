# imap-upload — загрузка выгрузки на IMAP-сервер

Читает структуру, созданную `light_dump.py` (`eml/<аккаунт>/<папка>/*.eml`),
создаёт на целевом IMAP-сервере папки и заливает письма через `APPEND`
как оригинальные RFC822-сообщения. Ведёт журнал `uploaded_<login>.txt` —
перезапуск докачивает только недостающее.

## Быстрый старт

```bash
# Gmail (нужен App Password: Google Account -> Security -> 2FA -> App passwords)
./upload.sh eml/you@mail.ru imap.gmail.com you@gmail.com 'app-password' --prefix mailru

# сухой прогон (план без загрузки)
python3 -I imap_upload.py --src eml/you@mail.ru --host imap.gmail.com \
    --login you@gmail.com --password 'app-password' --dry-run

# всё в один INBOX, без папок
./upload.sh eml/you@mail.ru imap.gmail.com you@gmail.com 'app-password' --flat
```

## Параметры

| Параметр | Значение |
|---|---|
| `--src` | каталог аккаунта (`eml/<login>`) или общий (`eml/`) |
| `--host` / `--port` | IMAP-сервер (по умолчанию порт 993) |
| `--no-ssl` | без TLS (порт 143) |
| `--prefix` | префикс папок на сервере (`mailru/Sent`, ...) |
| `--flat` | всё в один INBOX |
| `--dry-run` | показать план без загрузки |
| `--sleep` | пауза между письмами, сек (по умолчанию 0.1) |

## Маппинг папок

| локальная папка | IMAP |
|---|---|
| inbox | INBOX |
| sent | Sent |
| drafts | Drafts |
| spam | Junk |
| trash | Trash |
| archive | Archive |
| folder_N | folder_N |

## Безопасность

Пароль/App Password передаётся аргументом командной строки и попадает
в историю shell. Для разового использования это приемлемо; иначе
используйте переменные окружения или поправьте скрипт под `getpass`
(как сделано в `mailru2imap.py`).

## Notes

- Gmail: включите 2FA и создайте App Password — обычный пароль IMAP
  не примет.
- Не синхронизируйте из Gmail папку `[Gmail]/All Mail` обратно в
  архиватор — получите дубли.
