# Receipt OCR Bets

Скрипт принимает **изображение чека ставки** (фото/скрин) и возвращает данные в **строго фиксированном JSON**.

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

- Порядок и набор ключей **не меняется**.  
- Если поле не извлечено — значение **`null`**.  
- `odds`/`stake` — числа с точкой.  
- `bet_time` стараемся нормализовать в `YYYY-MM-DD HH:MM:SS`. Если на фото есть только время, возможно `HH:MM:SS`.

---

## Требования

- **Python** 3.11+  
- **Poetry** 1.6+  
- **OpenAI API key** (формат `sk-proj-…`)

---

## Установка

```bash
# из корня проекта
poetry install
```

Создайте `.env` в корне:

```
OPENAI_API_KEY=sk-proj-ВАШ_КЛЮЧ_ЦЕЛИКОМ
OPENAI_REQUEST_TIMEOUT=30
```

Проверка, что ключ подхватился:

```bash
poetry run python - <<'PY'
from pathlib import Path; from dotenv import load_dotenv; import os
load_dotenv(dotenv_path=Path.cwd()/".env", override=True)
print("HasKey:", bool(os.getenv("OPENAI_API_KEY","")))
PY
```

---

## Структура

```
receipt-ocr-bets/
  ├─ src/
  │   ├─ cli.py                 # CLI-вход
  │   ├─ receipt_extractor.py   # работа с ИИ + нормализация
  │   ├─ image_processor.py     # кодирование изображений в base64
  │   └─ config.py              # конфиг/ключ/таймаут
  ├─ samples/                   # примеры чеков (jpg/png)
  ├─ outputs/                   # результаты работы CLI
  ├─ tests/                     # юнит-тесты (моки, без расхода API)
  ├─ .env
  ├─ pyproject.toml
  └─ README.md
```

---

## Запуск (CLI)

**Синтаксис:**
```bash
poetry run python -m src.cli <путь_к_изображению> [путь_к_json]
```

- Результат **печатается в stdout**.  
- Если указан второй аргумент — результат **сохраняется** в файл.

**Примеры на образцах из `samples/`:**
```bash
poetry run python -m src.cli samples/photo_2025-03-08_20-26-20.jpg outputs/check_1.json
poetry run python -m src.cli samples/photo_2025-03-08_20-48-40.jpg outputs/check_2.json
poetry run python -m src.cli samples/photo_2025-03-12_13-54-53.jpg   outputs/check_3.json
```

---

## Примеры ответов

### `photo_2025-03-08_20-26-20.jpg`
```json
{
  "bet_time": "08/03/2025 20:25:36",
  "match": "Delfines U.G.M. - Tlapa",
  "outcome": "HANDICAP 0:2",
  "odds": 2.1,
  "stake": 100.0,
  "source_image_id": "8255cf7b0be3b687ad10"
}
```

### `photo_2025-03-08_20-48-40.jpg`
```json
{
  "bet_time": "08/03/2025 20:47:01",
  "match": "AA Portuguesa Santista SP - CA Votuporanguense SP",
  "outcome": "1",
  "odds": 2.6,
  "stake": 100.0,
  "source_image_id": "photo_2025-03-08_20-48-40.jpg"
}
```

### `photo_2025-03-12_13-54-53.jpg`
```json
{
  "bet_time": "12.03.2025 13:54:12",
  "match": "Football - Senegal Coupes Nationales",
  "outcome": "Who will win the match?",
  "odds": 3.76,
  "stake": 100.0,
  "source_image_id": "photo_2025-03-12_13-54-53.jpg"
}
```

> Схема и порядок ключей неизменны. При отсутствии данных — `null`.

---

## Обработка ошибок (stdout)

- Файл не найден:
  ```json
  {"status":"error","message":"Image not found: ..."}
  ```
- Таймаут/сеть:
  ```json
  {"status":"timeout","message":"AI request timeout/connection error: ..."}
  ```
- Неверный ключ:
  ```json
  {"status":"error","message":"... invalid_api_key ..."}
  ```
- Нет квоты/биллинга:
  ```json
  {"status":"error","message":"... insufficient_quota ..."}
  ```

> По умолчанию файл результата в `outputs/` создаётся **только при успехе** (если указан второй аргумент).

---

## Тесты (без расхода API)

```bash
poetry run pytest -v
```

## Ограничения и идеи

**Ограничения:** разные макеты чеков, блики/размытость, локализация дат/валют — возможны вариации в `bet_time` и тексте `outcome`.

**Идеи улучшения:** предобработка изображения (контраст/кадрирование), few-shot примеры в подсказке, расширенная пост-нормализация `outcome` до `1/Х/2`, батч-режим, кэширование по хэшу файла.
