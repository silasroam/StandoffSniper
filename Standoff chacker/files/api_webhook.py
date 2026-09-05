# api/webhook.py
"""
Webhook handler для Telegram Bot на Vercel.
Обрабатывает входящие обновления от Telegram API.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Добавить корневую директорию в path для импорта модулей проекта
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Update
from aiogram.fsm.storage.memory import MemoryStorage

# Импортируем роутер и функцию инициализации из основного бота
from bot import router, init_db
from config import BOT_TOKEN, ADMIN_ID

# ============================================================
# КОНФИГУРАЦИЯ RUNTIME
# ============================================================

# На Vercel используем /tmp для БД (временное хранилище)
# В продакшене нужно использовать внешнюю БД
DB_PATH_RUNTIME = os.getenv("DB_PATH", "/tmp/standoff_checker.db")

# ============================================================
# ИНИЦИАЛИЗАЦИЯ БОТА
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Подключить роутер из основного бота
dp.include_router(router)

# Флаг инициализации БД
_db_initialized = False

# ============================================================
# ИНИЦИАЛИЗАЦИЯ БД (один раз)
# ============================================================

async def initialize_database_once() -> None:
    """
    Инициализирует БД при первом запросе.
    На Vercel это выполняется один раз за время жизни контейнера.
    """
    global _db_initialized
    
    if _db_initialized:
        return
    
    try:
        # Переопределить путь БД на runtime путь
        import bot as bot_module
        original_db_path = bot_module.DB_PATH
        bot_module.DB_PATH = DB_PATH_RUNTIME
        
        # Инициализировать БД
        await init_db()
        
        _db_initialized = True
        print(f"Database initialized at {DB_PATH_RUNTIME}")
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise


# ============================================================
# WEBHOOK HANDLER
# ============================================================

async def webhook_handler(request) -> Dict[str, Any]:
    """
    Основной webhook handler для Vercel Functions.
    
    POST: Обрабатывает входящие обновления от Telegram
    GET: Проверка здоровья (health check)
    """
    
    # Инициализировать БД при первом запросе
    await initialize_database_once()
    
    # ========== POST запрос от Telegram ==========
    if request.method == "POST":
        try:
            # Получить JSON из тела запроса
            request_body = await request.json()
            
            # Преобразовать в объект Update
            update = Update(**request_body)
            
            # Обработать обновление через dispatcher
            await dp.feed_update(bot, update)
            
            return {"ok": True, "status": "processed"}
            
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}")
            return {"ok": False, "error": "Invalid JSON"}
            
        except Exception as e:
            print(f"Error processing update: {e}")
            return {"ok": False, "error": str(e)}
    
    # ========== GET запрос (health check) ==========
    elif request.method == "GET":
        return {
            "ok": True,
            "status": "Bot webhook is running",
            "bot_initialized": _db_initialized,
            "timestamp": str(Path(__file__).stat().st_mtime)
        }
    
    # ========== Неподдерживаемый метод ==========
    else:
        return {"ok": False, "error": "Method not allowed"}


# ============================================================
# EXPORT ДЛЯ VERCEL
# ============================================================

# Для Vercel Functions (ASGI)
# Vercel автоматически найдет функцию с названием,
# совпадающим с названием файла (webhook.py -> webhook)
async def webhook(request):
    """
    Точка входа для Vercel.
    Vercel передает объект request.
    """
    return await webhook_handler(request)


# Для локального тестирования (опционально)
if __name__ == "__main__":
    import asyncio
    from unittest.mock import Mock
    
    async def test():
        """Простой тест webhook'а"""
        mock_request = Mock()
        mock_request.method = "GET"
        
        result = await webhook(mock_request)
        print(result)
    
    asyncio.run(test())
