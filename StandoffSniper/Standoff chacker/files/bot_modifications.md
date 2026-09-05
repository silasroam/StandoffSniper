# Модификации для bot.py

## Изменение в конце файла (строки 2402-2419)

### БЫЛО:
```python
async def main() -> None:

    await init_db()

    await bot.delete_webhook(
        drop_pending_updates=False
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
```

### СТАЛО:
```python
async def main() -> None:
    """Режим для локального запуска (polling)"""
    await init_db()

    await bot.delete_webhook(
        drop_pending_updates=False
    )

    await dp.start_polling(
        bot
    )


async def webhook_main(update_data: dict) -> None:
    """Режим для Vercel (webhook)"""
    from aiogram.types import Update
    
    await init_db()
    update = Update(**update_data)
    await dp.feed_update(bot, update)


if __name__ == "__main__":
    # Локальный режим - используется при запуске из командной строки
    asyncio.run(
        main()
    )
```

---

## Почему эти изменения минимальны?

1. **Сохранен старый `main()`** - можно тестировать локально с polling
2. **Добавлена новая `webhook_main()`** - используется webhook handler'ом (`api/webhook.py`)
3. **Вся логика команд и обработчиков остается неизменной** - они хранятся в `router`
4. **Структура проекта не нарушена** - все файлы остаются на месте

Webhook handler (`api/webhook.py`) использует `router` из основного `bot.py`, поэтому никаких дублирований кода!

---

## Дополнительно (опционально)

Если хотите автоматически использовать webhook на Vercel:

### В начало `bot.py` добавить:
```python
import os

# Автоматически выбрать режим в зависимости от окружения
WEBHOOK_MODE = os.getenv("WEBHOOK_MODE", "false").lower() == "true"
```

### В `main()` добавить проверку:
```python
async def main() -> None:
    await init_db()
    
    if WEBHOOK_MODE:
        # На Vercel webhook уже активирован
        print("Running in webhook mode (Vercel)")
        return
    else:
        # Локально используем polling
        print("Running in polling mode (local)")
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
```

Но это **опционально** - старый `main()` работает как есть!
