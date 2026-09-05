"""
Скрипт инициализации базы данных для Telegram-бота "Standoff chacker".
Считывает skins.json и импортирует данные в таблицу skins.
Создаёт таблицы users и inventory для хранения данных пользователей
и перехваченных скинов.
"""

import asyncio
import json
import os

import aiosqlite

from config import DB_PATH, SKINS_JSON_PATH


async def create_tables(db: aiosqlite.Connection) -> None:
    """Создаёт все необходимые таблицы в базе данных."""

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS skins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            rare TEXT NOT NULL,
            collection TEXT NOT NULL,
            id_img TEXT NOT NULL,
            description TEXT NOT NULL
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'FREE',
            premium_until INTEGER NOT NULL DEFAULT 0,
            free_time_left INTEGER NOT NULL DEFAULT 1800,
            last_daily_reset INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            skin_name TEXT NOT NULL,
            fake_price REAL NOT NULL,
            capture_time INTEGER NOT NULL
        )
        """
    )

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_user_id ON inventory (user_id)"
    )

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_skins_name ON skins (name)"
    )

    await db.commit()


async def import_skins(db: aiosqlite.Connection, json_path: str) -> int:
    """Импортирует скины из JSON-файла в таблицу skins.
    Возвращает количество импортированных записей.
    """

    if not os.path.exists(json_path):
        print(f"Файл {json_path} не найден. Импорт скинов пропущен.")
        return 0

    with open(json_path, "r", encoding="utf-8") as f:
        skins = json.load(f)

    if not skins:
        print("Файл skins.json пуст. Импорт скинов пропущен.")
        return 0

    await db.executemany(
        """
        INSERT INTO skins (name, type, rare, collection, id_img, description)
        VALUES (:name, :type, :rare, :Collection, :id_Img, :description)
        """,
        skins,
    )
    await db.commit()

    return len(skins)


async def main() -> None:
    """Точка входа: создаёт таблицы и импортирует данные."""

    print(f"Инициализация базы данных: {DB_PATH}")

    async with aiosqlite.connect(DB_PATH) as db:
        await create_tables(db)
        print("Таблицы skins, users, inventory созданы.")

        imported = await import_skins(db, SKINS_JSON_PATH)
        if imported > 0:
            print(f"Импортировано скинов: {imported}")

    print("Структура БД готова. Инициализация завершена.")


if __name__ == "__main__":
    asyncio.run(main())
