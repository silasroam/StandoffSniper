# 🚀 Настройка Telegram Bot Webhook на Vercel

## 📋 Текущая ситуация
Ваш бот использует **polling mode** (строка 2410 в `bot.py`):
```python
await dp.start_polling(bot)
```

Vercel требует **webhook mode** для длительных процессов. Polling на serverless функциях неэффективен.

---

## ✅ Решение: Webhook Mode на Vercel

### Файловая структура (СОХРАНЯЕТСЯ):
```
project/
├── config.py              # ← Ваш конфиг (сохраняется)
├── bot.py                 # ← Основной бот (модифицируется минимально)
├── init_db.py            # ← Инициализация БД (сохраняется)
├── price.json            # ← Данные цен (сохраняется)
├── standoff_checker.db   # ← БД (в /tmp на Vercel)
├── .env.local            # ← Переменные окружения
├── .gitignore            # ← Gitignore
├── requirements.txt      # ← NEW: зависимости
└── api/
    └── webhook.py        # ← NEW: точка входа Vercel
```

---

## 🔧 Шаг 1: Создать requirements.txt

```
aiogram==3.4.0
aiosqlite==3.1.0
```

---

## 🔧 Шаг 2: Создать `api/webhook.py` (ГЛАВНОЕ)

Это - точка входа для Vercel. Ниже полный код:

```python
# api/webhook.py
import json
import os
import sys
from pathlib import Path

# Добавить корневую директорию в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.fsm.storage.memory import MemoryStorage

from bot import router, init_db, PRICE_JSON_PATH
from config import BOT_TOKEN, DB_PATH

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================

# Использовать /tmp для БД на Vercel (serverless)
DB_PATH_RUNTIME = os.getenv("DB_PATH", "/tmp/standoff_checker.db")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

_initialized = False

async def _init_once():
    """Инициализация БД при первом запросе"""
    global _initialized
    if not _initialized:
        # Заменить DB_PATH на runtime путь
        import bot as bot_module
        original_db_path = bot_module.DB_PATH
        bot_module.DB_PATH = DB_PATH_RUNTIME
        
        await init_db()
        _initialized = True

# ============================================================
# VERCEL SERVERLESS HANDLER
# ============================================================

async def handler(request):
    """
    Webhook handler для Vercel Functions.
    Получает обновления от Telegram и обрабатывает их.
    """
    
    # Инициализация при первом запросе
    await _init_once()
    
    # Обработать POST запрос от Telegram
    if request.method == "POST":
        try:
            data = await request.json()
            update = Update(**data)
            
            # Обработать обновление
            await dp.feed_update(bot, update)
            
            return {"ok": True}
            
        except Exception as e:
            print(f"Error: {e}")
            return {"ok": False, "error": str(e)}
    
    # GET для проверки здоровья (health check)
    if request.method == "GET":
        return {"ok": True, "status": "Bot is running"}
    
    return {"ok": False}


# ============================================================
# EXPORT для Vercel
# ============================================================

# Для Vercel Functions (ASGI)
async def webhook(request):
    return await handler(request)
```

---

## 🔧 Шаг 3: Модифицировать `bot.py` (МИНИМАЛЬНО)

Изменить только **точку входа** (конец файла):

```python
# В конце bot.py (строки 2402-2419), заменить на:

async def main() -> None:
    """Для локального polling режима"""
    await init_db()
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


# Точка входа для webhook на Vercel (используется через api/webhook.py)
async def webhook_main(update_data: dict) -> None:
    """Для webhook режима на Vercel"""
    await init_db()
    update = Update(**update_data)
    await dp.feed_update(bot, update)


if __name__ == "__main__":
    # Локальный режим polling
    asyncio.run(main())
```

**Важно:** сохранить старую `main()` для локального тестирования!

---

## 🔧 Шаг 4: Создать `vercel.json`

```json
{
  "buildCommand": "pip install -r requirements.txt",
  "outputDirectory": "",
  "functions": {
    "api/webhook.py": {
      "runtime": "python3.12",
      "memory": 1024,
      "maxDuration": 10
    }
  },
  "env": {
    "BOT_TOKEN": "@BOT_TOKEN",
    "ADMIN_ID": "@ADMIN_ID",
    "DB_PATH": "/tmp/standoff_checker.db"
  }
}
```

---

## 🔧 Шаг 5: Обновить `.env.local` / Vercel Dashboard

Перейти в **Settings → Environment Variables** вашего проекта на Vercel и добавить:

| Ключ | Значение |
|------|----------|
| `BOT_TOKEN` | `8811143217:AAEPeOh0RwaOSlNJS4FOl8sY9S35aTzppX8` |
| `ADMIN_ID` | `7969090536` |
| `PRICE_JSON_PATH` | `price.json` |

**⚠️ ВАЖНО:** Никогда не коммитьте токены! Используйте только Vercel Environment Variables.

---

## 🔧 Шаг 6: Установить Webhook в Telegram

После деплоя на Vercel запустить команду (один раз):

```bash
curl -X POST https://api.telegram.org/bot<BOT_TOKEN>/setWebhook \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<your-vercel-domain>/api/webhook",
    "allowed_updates": ["message", "callback_query", "pre_checkout_query", "successful_payment"]
  }'
```

**Где:**
- `<BOT_TOKEN>` → ваш токен бота
- `<your-vercel-domain>` → `standoff-sniper-xy.vercel.app` (или ваш домен)

### Проверить статус webhook:
```bash
curl https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo
```

Должно вернуть:
```json
{
  "ok": true,
  "result": {
    "url": "https://standoff-sniper-xy.vercel.app/api/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

---

## 📝 Важные моменты

### ✅ Что сохраняется:
- ✓ `config.py` - без изменений
- ✓ `bot.py` - минимальные изменения (только точка входа)
- ✓ `init_db.py` - без изменений
- ✓ `price.json` - без изменений
- ✓ Вся логика обработки команд и callback'ов

### ⚠️ Особенности Vercel:
1. **Временное хранилище:** БД живет в `/tmp`, исчезает при перезагрузке
   - Решение: использовать внешнюю БД (PostgreSQL, MongoDB) или сохранять в облако

2. **Максимальное время выполнения:** 10 сек на hobby плане
   - Решение: разделить длительные операции на задачи

3. **Холодный старт:** первый запрос может быть медленным
   - Решение: использовать Vercel Cron для прогрева

### 🗄️ Для постоянной БД (рекомендуется):

Добавить в `config.py`:
```python
DATABASE_URL = os.getenv("DATABASE_URL")  # PostgreSQL на Supabase/Railway

if DATABASE_URL:
    # Использовать PostgreSQL
    import asyncpg
else:
    # Использовать локальный SQLite
    DB_PATH = "/tmp/standoff_checker.db"
```

---

## 🚀 Деплой

```bash
# 1. Установить Vercel CLI
npm i -g vercel

# 2. Залогиниться
vercel login

# 3. Залить проект
vercel --prod
```

---

## 📞 Чек-лист

- [ ] Создан `api/webhook.py`
- [ ] Создан `requirements.txt`
- [ ] Создан `vercel.json`
- [ ] Переменные окружения добавлены в Vercel Dashboard
- [ ] `bot.py` модифицирован (сохранена `main()` для локального тестирования)
- [ ] Webhook установлен через API Telegram
- [ ] Webhook статус проверен (`getWebhookInfo`)
- [ ] Проект залит на Vercel (`vercel --prod`)

---

## 🧪 Локальное тестирование

Пока что используется старый polling режим:
```bash
python bot.py
```

Это сохраняет обратную совместимость! 🎉
