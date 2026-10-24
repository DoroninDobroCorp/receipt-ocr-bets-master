# Receipt OCR Bets

Сервис принимает **изображение чека ставки** (фото/скриншот) и извлекает данные в **строго фиксированном JSON**.

```json
{
  "bet_time": "YYYY-MM-DD HH:MM:SS | HH:MM:SS | null",
  "match": "string|null",
  "outcome": "string|null",
  "odds": 1.23,
  "stake": null,
  "source_image_id": "string"
}
```

- Порядок и набор ключей **строго фиксирован**.
- Если поле не извлечено или нечитаемо — значение **`null`**.
- `odds` и `stake` — числа с плавающей точкой (`float` или `null`).
- `bet_time` нормализуется в формат `YYYY-MM-DD HH:MM:SS`. Если на фото видна только временная отметка без даты — `HH:MM:SS`.
- `source_image_id` — номер билета / штрихкод, напечатанный на чеке (если отсутствует, используется имя файла).

---

## Требования

- **Python** 3.11+
- **Poetry** 1.6+ (или Poetry 2+)
- **OpenAI API key**

---

## Установка

```bash
# из корня проекта
poetry install
```

Создайте `.env` в корне (на основе `.env_sample`):

```ini
OPENAI_API_KEY=sk-proj-ВАШ_КЛЮЧ_ЦЕЛИКОМ
OPENAI_REQUEST_TIMEOUT=30
OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MAX_RETRIES=3
```

Проверка, что ключ подхватился:

```bash
poetry run python - <<'PY'
from pathlib import Path
from dotenv import load_dotenv
import os
load_dotenv(dotenv_path=Path.cwd()/".env", override=True)
print("HasKey:", bool(os.getenv("OPENAI_API_KEY", "")))
PY
```

---

## Структура проекта

```
receipt-ocr-bets/
  ├─ src/
  │   ├─ cli.py                 # CLI-точка входа
  │   ├─ config.py              # Конфигурация / переменные окружения
  │   ├─ image_processor.py     # Предобработка: EXIF-ротация, автоконтраст, base64
  │   ├─ models.py              # Pydantic-схема и валидация
  │   └─ receipt_extractor.py   # Работа с Vision API + нормализация + ретраи
  ├─ samples/                   # Примеры чеков (jpg/png)
  ├─ outputs/                   # Результаты работы CLI (создаётся автоматически)
  ├─ tests/                     # Юнит-тесты (моки, без расхода API-токенов)
  ├─ .env_sample
  ├─ pyproject.toml
  └─ README.md
```

---

## Запуск (CLI)

**Синтаксис:**
```bash
poetry run python -m src.cli <путь_к_изображению> [путь_к_json]
```

- Результат **всегда печатается в stdout в виде чистого JSON**.
- Если указан второй аргумент — результат **сохраняется** в указанный файл (папка создаётся автоматически).
- Информационные сообщения (например, путь сохранения) направляются в `stderr`, сохраняя `stdout` пригодным для конвейеров (`jq`, `grep` и т.д.).

**Примеры запуска:**
```bash
poetry run python -m src.cli samples/photo_2025-03-08_20-26-20.jpg outputs/check_1.json
poetry run python -m src.cli samples/photo_2025-03-08_20-48-40.jpg outputs/check_2.json
poetry run python -m src.cli samples/photo_2025-03-12_13-54-53.jpg outputs/check_3.json
```

---

## Примеры ответов

### `photo_2025-03-08_20-26-20.jpg`
```json
{
  "bet_time": "2025-03-08 20:25:36",
  "match": "Delfines U.G.M. - Tlapa",
  "outcome": "HANDICAP 0:3 2",
  "odds": 2.1,
  "stake": 100.0,
  "source_image_id": "8255cf7b0be3b687ad10"
}
```

### `photo_2025-03-08_20-48-40.jpg`
```json
{
  "bet_time": "2025-03-08 20:47:01",
  "match": "AA Portuguesa Santista SP - CA Votuporanguense SP",
  "outcome": "1",
  "odds": 2.6,
  "stake": 100.0,
  "source_image_id": "3fc7aa441eed7076ec10"
}
```

### `photo_2025-03-12_13-54-53.jpg`
```json
{
  "bet_time": "2025-03-12 13:54:12",
  "match": "Espoirs Guediawaye - RS Yoff",
  "outcome": "1",
  "odds": 3.76,
  "stake": 100.0,
  "source_image_id": "photo_2025-03-12_13-54-53.jpg"
}
```

---

## Обработка ошибок (stdout и exit codes)

- **Файл не найден** (exit code `2`):
  ```json
  {"status":"error","message":"Image not found: ..."}
  ```
- **Таймаут или ошибка соединения** (exit code `3`):
  ```json
  {"status":"timeout","message":"AI request timeout/connection error: ..."}
  ```
- **Ошибка ключа / квоты / валидации** (exit code `1`):
  ```json
  {"status":"error","message":"..."}
  ```

При указании второго аргумента файл ошибки записывается безопасно, создавая все вложенные папки.

---

## Тестирование

Все тесты изолированы, используют моки и не расходуют баланс OpenAI:

```bash
poetry run pytest -v
```

---

## Ключевые улучшения и особенности реализации

1. **Pydantic Data Models**: строгая схема с гарантированным порядком ключей и автоматической конвертацией типов (`float`, запятые в точках, стрип строк).
2. **EXIF Transposition**: автоматический учет угла съемки со смартфонов (`ImageOps.exif_transpose`), предотвращающий отправку перевернутых чеков.
3. **Smart Downscaling**: безопасное сжатие гигантских фото до 2048px без потери читаемости шрифтов, что существенно ускоряет отклик и экономит токены.
4. **Умная нормализация дат**: извлечение дат из форматов `DD/MM/YYYY`, `DD.MM.YYYY`, `DD.MM.YY`, с днями недели, а также fallback из имени файла, если в чеке присутствует только время.
5. **Tenacity Retries**: встроенный механизм повторных попыток с экспоненциальной задержкой при сетевых таймаутах и ошибках rate-limit (429).
6. **Чистый stdout**: сервисные сообщения направляются в `stderr`, что обеспечивает валидный JSON-поток на `stdout`.
