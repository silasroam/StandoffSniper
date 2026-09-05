"""
Standoff Chacker v3.8.1
Telegram bot for Standoff 2 skin tracking and market monitoring.
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime

import aiosqlite

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
    URLInputFile,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ID, BOT_TOKEN, DB_PATH


# ============================================================
# BOT
# ============================================================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher(
    storage=MemoryStorage()
)

router = Router()


# ============================================================
# CONSTANTS
# ============================================================

FREE_TIME_DEFAULT = 3600
PREMIUM_PRICE = 100
HUNT_TICK_SECONDS = 30

WITHDRAW_PROCESSING_HOURS = 72

PRICE_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "price.json",
)


# ============================================================
# FSM
# ============================================================

class WithdrawStates(StatesGroup):
    waiting_id = State()


# ============================================================
# RUNTIME STATE
# ============================================================

active_hunts: dict[int, dict] = {}


# ============================================================
# MARKET DATA
# ============================================================

KNIFE_KEYWORDS = [
    "knife",
    "karambit",
    "butterfly",
    "m9",
    "kunai",
    "jcommando",
    "jkommando",
    "fang",
    "scorpion",
    "bayonet",
    "tanto",
    "stiletto",
    "kukri",
    "daggers",
    "flip",
    "dual dagger",
    "sting",
]

GLOVE_KEYWORDS = [
    "glove",
    "перчатки",
]

KNIFE_ESTIMATED_PRICE = (
    12000.0,
    35000.0,
)

GLOVE_ESTIMATED_PRICE = (
    8000.0,
    22000.0,
)

ARCANE_ESTIMATED_PRICE = (
    1500.0,
    4500.0,
)

LEGENDARY_ESTIMATED_PRICE = (
    400.0,
    1200.0,
)

BASIC_ESTIMATED_PRICE = (
    5.0,
    500.0,
)

RARITY_ESTIMATED_RANGES = {
    "Common": (5, 20),
    "Uncommon": (25, 80),
    "Rare": (100, 300),
    "Epic": (400, 1200),
    "Legendary": (400, 1200),
    "Arcane": (1500, 4500),
    "Arcane-Glove": (8000, 22000),
}


ARCANE_KNIVES = [
    "Arcane Karambit",
    "Arcane Stiletto",
    "Arcane Butterfly",
    "Arcane M9 Bayonet",
    "Arcane Talon",
    "Arcane Falchion",
    "Arcane Bowie",
    "Arcane Flip",
    "Arcane Bayonet",
    "Arcane Huntsman",
]

ARCANE_GLOVES = [
    "Arcane Gloves Crimson",
    "Arcane Gloves Vise",
    "Arcane Gloves Gold Rush",
    "Arcane Gloves Motosport",
    "Arcane Gloves Amphibious",
    "Arcane Gloves Specialist",
    "Arcane Gloves Night",
]


# ============================================================
# HELPERS
# ============================================================

def format_time_left(seconds: int) -> str:
    if seconds <= 0:
        return "0 мин"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes} мин"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    if remaining_minutes:
        return f"{hours} ч {remaining_minutes} мин"

    return f"{hours} ч"


def format_datetime(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime(
        "%d.%m.%Y %H:%M"
    )


def escape_html(value: str) -> str:
    value = str(value or "")

    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _is_knife_skin(name: str) -> bool:
    lowered = (name or "").lower()

    return any(
        keyword in lowered
        for keyword in KNIFE_KEYWORDS
    )


def _is_gloves_skin(skin: dict) -> bool:
    haystack = " ".join(
        [
            skin.get("type") or "",
            skin.get("Collection")
            or skin.get("collection")
            or "",
            skin.get("name") or "",
        ]
    ).lower()

    return any(
        keyword in haystack
        for keyword in GLOVE_KEYWORDS
    )


def _estimated_market_price(skin: dict) -> float:
    """
    Returns an estimated price only when the price feed
    does not contain an actual market_price value.
    """

    name = skin.get("name") or ""
    rarity = (skin.get("rare") or "").strip()

    if _is_gloves_skin(skin):
        low, high = GLOVE_ESTIMATED_PRICE

    elif _is_knife_skin(name):
        low, high = KNIFE_ESTIMATED_PRICE

    elif rarity.lower() == "arcane":
        low, high = ARCANE_ESTIMATED_PRICE

    elif rarity.lower() == "legendary":
        low, high = LEGENDARY_ESTIMATED_PRICE

    else:
        low, high = BASIC_ESTIMATED_PRICE

    return round(
        random.uniform(low, high),
        2,
    )


def _get_market_price(skin: dict) -> tuple[float, bool]:
    """
    Returns:
        price,
        is_from_feed
    """

    price = skin.get("market_price")

    if price is not None:
        try:
            return float(price), True
        except (TypeError, ValueError):
            pass

    return _estimated_market_price(skin), False


def _is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ============================================================
# PRICE FEED
# ============================================================

def _load_price_feed() -> dict | None:
    try:
        if not os.path.exists(PRICE_JSON_PATH):
            return None

        with open(
            PRICE_JSON_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except (
        OSError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        pass

    return None


# ============================================================
# DATABASE
# ============================================================

async def init_db() -> None:

    db_directory = os.path.dirname(DB_PATH)

    if db_directory:
        os.makedirs(
            db_directory,
            exist_ok=True,
        )

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'FREE',
                premium_until INTEGER NOT NULL DEFAULT 0,
                free_time_left INTEGER NOT NULL DEFAULT 3600,
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
                estimated_price REAL NOT NULL,
                capture_time INTEGER NOT NULL
            )
            """
        )

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
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                game_id TEXT NOT NULL,
                items_count INTEGER NOT NULL DEFAULT 0,
                total_value REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'PENDING',
                created_at INTEGER NOT NULL,
                estimated_completion INTEGER NOT NULL
            )
            """
        )

        await db.commit()

        # ----------------------------------------------------
        # Legacy inventory migration
        # ----------------------------------------------------

        inventory_columns_result = await db.execute(
            "PRAGMA table_info(inventory)"
        )

        inventory_columns = await inventory_columns_result.fetchall()

        existing_inventory_columns = {
            row[1]
            for row in inventory_columns
        }

        if (
            "estimated_price"
            not in existing_inventory_columns
        ):
            await db.execute(
                """
                ALTER TABLE inventory
                ADD COLUMN estimated_price
                REAL NOT NULL DEFAULT 0
                """
            )

        await db.commit()


async def get_user(
    user_id: int,
) -> dict | None:

    async with aiosqlite.connect(DB_PATH) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cursor:

            row = await cursor.fetchone()

            if row:
                return dict(row)

        await db.execute(
            """
            INSERT INTO users (user_id)
            VALUES (?)
            """,
            (user_id,),
        )

        await db.commit()

        async with db.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cursor:

            row = await cursor.fetchone()

            return dict(row) if row else None


async def update_user(
    user_id: int,
    **kwargs,
) -> None:

    if not kwargs:
        return

    allowed_fields = {
        "status",
        "premium_until",
        "free_time_left",
        "last_daily_reset",
    }

    invalid_fields = set(kwargs) - allowed_fields

    if invalid_fields:
        raise ValueError(
            f"Unsupported user fields: "
            f"{', '.join(sorted(invalid_fields))}"
        )

    set_clause = ", ".join(
        f"{field} = ?"
        for field in kwargs
    )

    values = list(kwargs.values())
    values.append(user_id)

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            f"""
            UPDATE users
            SET {set_clause}
            WHERE user_id = ?
            """,
            values,
        )

        await db.commit()


# ============================================================
# USER STATUS
# ============================================================

async def get_user_status(
    user_data: dict,
) -> str:

    premium_until = int(
        user_data.get(
            "premium_until",
            0,
        )
        or 0
    )

    if premium_until > int(time.time()):
        return "PREMIUM"

    if user_data.get("status") != "FREE":
        await update_user(
            user_data["user_id"],
            status="FREE",
        )

    return "FREE"


async def check_and_reset_daily_time(
    user_data: dict,
) -> dict:

    current_time = int(time.time())

    last_reset = int(
        user_data.get(
            "last_daily_reset",
            0,
        )
        or 0
    )

    current_day_start = (
        datetime.now()
        .replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )

    current_day_timestamp = int(
        current_day_start.timestamp()
    )

    if last_reset < current_day_timestamp:

        await update_user(
            user_data["user_id"],
            free_time_left=FREE_TIME_DEFAULT,
            last_daily_reset=current_time,
        )

        user_data["free_time_left"] = (
            FREE_TIME_DEFAULT
        )

        user_data["last_daily_reset"] = (
            current_time
        )

    return user_data


# ============================================================
# INVENTORY
# ============================================================

async def get_inventory_summary(
    user_id: int,
) -> tuple[float, int]:

    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT
                COALESCE(
                    SUM(estimated_price),
                    0
                ),
                COUNT(*)
            FROM inventory
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cursor:

            row = await cursor.fetchone()

    if not row:
        return 0.0, 0

    return (
        float(row[0] or 0),
        int(row[1] or 0),
    )


async def get_inventory_items(
    user_id: int,
) -> list:

    async with aiosqlite.connect(DB_PATH) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT
                id,
                skin_name,
                estimated_price,
                capture_time
            FROM inventory
            WHERE user_id = ?
            ORDER BY estimated_price DESC
            """,
            (user_id,),
        ) as cursor:

            return await cursor.fetchall()


# ============================================================
# SKINS
# ============================================================

async def pick_random_skin() -> dict | None:

    price_feed = _load_price_feed()

    if price_feed:

        items = (
            price_feed.get("skins")
            or price_feed.get("items")
        )

        if isinstance(items, list) and items:

            valid_items = [
                item
                for item in items
                if isinstance(item, dict)
            ]

            if valid_items:

                index = random.randrange(
                    len(valid_items)
                )

                pick = valid_items[index]

                skin_id = (
                    pick.get("id")
                    or index + 1
                )

                return {
                    "id": skin_id,
                    "name": pick.get(
                        "name",
                        "Unknown Skin",
                    ),
                    "rare": pick.get(
                        "rare",
                        "Common",
                    ),
                    "id_img": (
                        pick.get("id_Img")
                        or pick.get(
                            "id_img",
                            "",
                        )
                    ),
                    "type": pick.get(
                        "type",
                        "",
                    ),
                    "collection": (
                        pick.get("Collection")
                        or pick.get(
                            "collection",
                            "",
                        )
                    ),
                    "category": pick.get(
                        "Category",
                        "",
                    ),
                    "description": pick.get(
                        "description",
                        "",
                    ),
                    "market_price": pick.get(
                        "market_price"
                    ),
                }

    async with aiosqlite.connect(DB_PATH) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT *
            FROM skins
            WHERE rare IN (
                'Common',
                'Uncommon',
                'Rare',
                'Epic'
            )
            ORDER BY RANDOM()
            LIMIT 1
            """
        ) as cursor:

            row = await cursor.fetchone()

            return dict(row) if row else None


# ============================================================
# MAIN KEYBOARD
# ============================================================

def get_main_keyboard(
    status: str,
    time_left: int,
) -> InlineKeyboardMarkup:

    builder = InlineKeyboardBuilder()

    if (
        status == "PREMIUM"
        or time_left > 0
    ):

        builder.row(
            InlineKeyboardButton(
                text="🎯 ЗАПУСТИТЬ ОХОТУ",
                callback_data="start_hunt",
            )
        )

    else:

        builder.row(
            InlineKeyboardButton(
                text="❌ ОХОТА НЕДОСТУПНА",
                callback_data="hunt_blocked",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🎒 МОЙ ИНВЕНТАРЬ",
            callback_data="view_inv",
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=(
                f"👑 PREMIUM "
                f"({PREMIUM_PRICE} 🌟)"
            ),
            callback_data="activate_premium",
        )
    )

    return builder.as_markup()


# ============================================================
# MAIN PANEL
# ============================================================

async def build_main_panel(
    user_id: int,
) -> tuple[
    str,
    InlineKeyboardMarkup,
]:

    user_data = await get_user(
        user_id
    )

    if not user_data:
        raise RuntimeError(
            "Unable to create user"
        )

    user_data = (
        await check_and_reset_daily_time(
            user_data
        )
    )

    status = await get_user_status(
        user_data
    )

    balance, items_count = (
        await get_inventory_summary(
            user_id
        )
    )

    price_feed = _load_price_feed()

    if price_feed:
        source_text = (
            "📊 Источник цен: "
            "локальный прайс-фид"
        )
    else:
        source_text = (
            "📊 Источник цен: "
            "оценочный режим"
        )

    text = (
        "🎯 <b>STANDOFF CHACKER "
        "v3.8.1</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{source_text}\n"
        f"🔑 <b>Статус:</b> {status}\n"
    )

    if status == "FREE":

        time_left = int(
            user_data.get(
                "free_time_left",
                0,
            )
            or 0
        )

        text += (
            f"⏱ <b>Бесплатное время:</b> "
            f"{format_time_left(time_left)} "
            "в день\n"
        )

    else:

        premium_until = int(
            user_data.get(
                "premium_until",
                0,
            )
            or 0
        )

        remaining_seconds = max(
            0,
            premium_until - int(time.time()),
        )

        text += (
            "👑 <b>Premium активен</b>\n"
            f"⏱ До: "
            f"{format_datetime(premium_until)}\n"
            f"⌛ Осталось: "
            f"{format_time_left(remaining_seconds)}\n"
        )

    text += (
        "\n🎒 <b>Инвентарь:</b> "
        f"{items_count} предметов\n"
        f"💰 <b>Оценочная стоимость:</b> "
        f"{balance:.2f} G"
    )

    keyboard = get_main_keyboard(
        status,
        int(
            user_data.get(
                "free_time_left",
                0,
            )
            or 0
        ),
    )

    return text, keyboard


# ============================================================
# FREE TIME
# ============================================================

async def _deduct_free_time(
    user_id: int,
    seconds: int,
) -> int:

    user_data = await get_user(
        user_id
    )

    if not user_data:
        return 0

    status = await get_user_status(
        user_data
    )

    if status == "PREMIUM":
        return int(
            user_data.get(
                "free_time_left",
                FREE_TIME_DEFAULT,
            )
            or FREE_TIME_DEFAULT
        )

    remaining = int(
        user_data.get(
            "free_time_left",
            0,
        )
        or 0
    )

    remaining = max(
        0,
        remaining - seconds,
    )

    await update_user(
        user_id,
        free_time_left=remaining,
    )

    return remaining


async def _free_time_worker(
    user_id: int,
    chat_id: int,
) -> None:

    try:

        while active_hunts.get(
            user_id,
            {},
        ).get(
            "running",
            False,
        ):

            await asyncio.sleep(
                HUNT_TICK_SECONDS
            )

            if not active_hunts.get(
                user_id,
                {},
            ).get(
                "running",
                False,
            ):
                break

            remaining = (
                await _deduct_free_time(
                    user_id,
                    HUNT_TICK_SECONDS,
                )
            )

            user_data = await get_user(
                user_id
            )

            if not user_data:
                break

            status = await get_user_status(
                user_data
            )

            if (
                status == "FREE"
                and remaining <= 0
            ):

                active_hunts[
                    user_id
                ]["running"] = False

                await bot.send_message(
                    chat_id,
                    (
                        "⏱ <b>Бесплатное "
                        "время завершено</b>\n\n"
                        "Лимит обновится "
                        "в начале следующего дня.\n\n"
                        "👑 Premium позволяет "
                        "продолжить использование "
                        "охоты без дневного "
                        "ограничения."
                    ),
                    parse_mode="HTML",
                )

                break

    except asyncio.CancelledError:
        pass

    except Exception:
        active_hunts.get(
            user_id,
            {},
        )["running"] = False


# ============================================================
# MARKET LOT
# ============================================================

async def _fire_interception(
    user_id: int,
    chat_id: int,
) -> None:

    user_data = await get_user(
        user_id
    )

    if not user_data:
        return

    await check_and_reset_daily_time(
        user_data
    )

    skin = await pick_random_skin()

    if not skin:
        await bot.send_message(
            chat_id,
            (
                "⚠️ <b>Нет доступных "
                "предметов</b>\n\n"
                "Добавьте данные о скинах "
                "в price.json или таблицу skins."
            ),
            parse_mode="HTML",
        )
        return

    skin_name = escape_html(
        skin.get(
            "name",
            "Unknown Skin",
        )
    )

    rarity = escape_html(
        skin.get(
            "rare",
            "Common",
        )
    )

    id_img = skin.get(
        "id_img",
        "",
    )

    market_price, is_from_feed = (
        _get_market_price(skin)
    )

    price_source = (
        "Цена из прайс-фида"
        if is_from_feed
        else "Оценочная цена"
    )

    buy_price = round(
        market_price
        * random.uniform(
            0.75,
            0.95,
        ),
        2,
    )

    potential_difference = round(
        market_price - buy_price,
        2,
    )

    lot_id = str(
        skin.get(
            "id",
            random.randint(
                100000,
                999999,
            ),
        )
    )

    if user_id in active_hunts:

        active_hunts[
            user_id
        ]["current_lot"] = {
            "lot_id": lot_id,
            "skin": skin,
            "market_price": market_price,
            "buy_price": buy_price,
            "potential_difference": (
                potential_difference
            ),
        }

        active_hunts[
            user_id
        ]["captured_this_lot"] = False

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎒 СОХРАНИТЬ В ИНВЕНТАРЬ",
                    callback_data=(
                        f"capture:{lot_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎒 ОТКРЫТЬ ИНВЕНТАРЬ",
                    callback_data="view_inv",
                )
            ],
        ]
    )

    caption = (
        "🎯 <b>НАЙДЕН ЛОТ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔫 <b>Предмет:</b> "
        f"{skin_name}\n"
        f"💎 <b>Редкость:</b> "
        f"{rarity}\n\n"
        f"💰 <b>Цена лота:</b> "
        f"{buy_price:.2f} G\n"
        f"📊 <b>Рыночная оценка:</b> "
        f"{market_price:.2f} G\n"
        f"📈 <b>Разница:</b> "
        f"+{potential_difference:.2f} G\n\n"
        f"ℹ️ {price_source}"
    )

    await _send_lot_message(
        chat_id,
        caption,
        id_img,
        keyboard,
    )


async def _send_lot_message(
    chat_id: int,
    caption: str,
    id_img: str,
    keyboard: InlineKeyboardMarkup,
) -> None:

    if id_img:

        if (
            id_img.startswith("http://")
            or id_img.startswith("https://")
        ):

            try:

                photo = URLInputFile(
                    id_img
                )

                await bot.send_photo(
                    chat_id,
                    photo,
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )

                return

            except Exception:
                pass

    await bot.send_message(
        chat_id,
        caption,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ============================================================
# HUNT WORKER
# ============================================================

async def _interception_worker(
    user_id: int,
    chat_id: int,
) -> None:

    try:

        while active_hunts.get(
            user_id,
            {},
        ).get(
            "running",
            False,
        ):

            user_data = await get_user(
                user_id
            )

            if not user_data:
                break

            status = await get_user_status(
                user_data
            )

            if status == "PREMIUM":

                delay = random.uniform(
                    60,
                    120,
                )

            else:

                delay = random.uniform(
                    150,
                    240,
                )

            await asyncio.sleep(
                delay
            )

            if not active_hunts.get(
                user_id,
                {},
            ).get(
                "running",
                False,
            ):
                break

            await _fire_interception(
                user_id,
                chat_id,
            )

    except asyncio.CancelledError:
        pass

    except Exception:
        active_hunts.get(
            user_id,
            {},
        )["running"] = False


# ============================================================
# HUNT ANIMATION
# ============================================================

async def _run_hunt_animation(
    message: Message,
) -> None:

    steps = [
        "⌛ Подготовка мониторинга рынка...",
        "📡 Загрузка доступных данных...",
        "🟢 Мониторинг рынка запущен.",
    ]

    try:

        sent = await message.answer(
            steps[0],
            parse_mode="HTML",
        )

        for step in steps[1:]:

            await asyncio.sleep(1.2)

            try:

                await sent.edit_text(
                    step,
                    parse_mode="HTML",
                )

            except Exception:

                sent = await message.answer(
                    step,
                    parse_mode="HTML",
                )

    except Exception:

        await message.answer(
            steps[-1],
            parse_mode="HTML",
        )


# ============================================================
# START
# ============================================================

@router.message(
    CommandStart()
)
async def cmd_start(
    message: Message,
) -> None:

    user_id = message.from_user.id

    text, keyboard = (
        await build_main_panel(
            user_id
        )
    )

    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ============================================================
# START HUNT
# ============================================================

@router.callback_query(
    F.data == "start_hunt"
)
async def start_hunt(
    callback: CallbackQuery,
) -> None:

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    user_data = await get_user(
        user_id
    )

    if not user_data:
        await callback.answer(
            "Ошибка профиля.",
            show_alert=True,
        )
        return

    user_data = (
        await check_and_reset_daily_time(
            user_data
        )
    )

    status = await get_user_status(
        user_data
    )

    time_left = int(
        user_data.get(
            "free_time_left",
            0,
        )
        or 0
    )

    if (
        status == "FREE"
        and time_left <= 0
    ):

        await callback.answer(
            (
                "⛔ Бесплатное время "
                "на сегодня завершено. "
                "Активируйте Premium "
                "для продолжения."
            ),
            show_alert=True,
        )

        return

    if active_hunts.get(
        user_id,
        {},
    ).get(
        "running",
        False,
    ):

        await callback.answer(
            "🟢 Мониторинг уже запущен.",
            show_alert=True,
        )

        return

    await callback.answer()

    await _run_hunt_animation(
        callback.message
    )

    active_hunts[user_id] = {
        "running": True,
        "chat_id": chat_id,
        "current_lot": None,
        "captured_this_lot": False,
    }

    asyncio.create_task(
        _free_time_worker(
            user_id,
            chat_id,
        )
    )

    asyncio.create_task(
        _interception_worker(
            user_id,
            chat_id,
        )
    )


# ============================================================
# HUNT BLOCKED
# ============================================================

@router.callback_query(
    F.data == "hunt_blocked"
)
async def hunt_blocked(
    callback: CallbackQuery,
) -> None:

    await callback.answer(
        (
            "⛔ Бесплатное время "
            "на сегодня завершено.\n"
            "Активируйте Premium "
            "для продолжения."
        ),
        show_alert=True,
    )


# ============================================================
# SAVE INVENTORY
# ============================================================

async def _save_to_inventory(
    user_id: int,
    skin: dict,
    estimated_price: float,
) -> None:

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            INSERT INTO inventory (
                user_id,
                skin_name,
                estimated_price,
                capture_time
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                skin.get(
                    "name",
                    "Unknown Skin",
                ),
                estimated_price,
                int(time.time()),
            ),
        )

        await db.commit()


# ============================================================
# CAPTURE
# ============================================================

@router.callback_query(
    F.data.startswith("capture:")
)
async def capture_lot(
    callback: CallbackQuery,
) -> None:

    user_id = callback.from_user.id

    hunt = active_hunts.get(
        user_id
    )

    if not hunt or not hunt.get(
        "running",
        False,
    ):

        await callback.answer(
            (
                "⛔ Мониторинг "
                "не запущен."
            ),
            show_alert=True,
        )

        return

    lot = hunt.get(
        "current_lot"
    )

    if not lot:

        await callback.answer(
            "⚠️ Лот больше недоступен.",
            show_alert=True,
        )

        return

    lot_id = callback.data[
        len("capture:")
    :]

    if str(
        lot.get("lot_id")
    ) != lot_id:

        await callback.answer(
            "⚠️ Лот больше недоступен.",
            show_alert=True,
        )

        return

    if hunt.get(
        "captured_this_lot",
        False,
    ):

        await callback.answer(
            "⚠️ Лот уже сохранён.",
            show_alert=True,
        )

        return

    skin = lot["skin"]

    market_price = float(
        lot.get(
            "market_price",
            0,
        )
        or 0
    )

    await _save_to_inventory(
        user_id,
        skin,
        market_price,
    )

    hunt[
        "captured_this_lot"
    ] = True

    hunt[
        "current_lot"
    ] = None

    await callback.answer(
        "✅ Предмет сохранён в инвентарь.",
        show_alert=True,
    )

    try:

        await callback.message.answer(
            (
                "🎯 <b>ПРЕДМЕТ СОХРАНЁН</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔫 Предмет: "
                f"{escape_html(skin.get('name'))}\n"
                f"💎 Редкость: "
                f"{escape_html(skin.get('rare'))}\n"
                f"📊 Оценочная стоимость: "
                f"{market_price:.2f} G\n\n"
                "Предмет добавлен в ваш "
                "внутренний инвентарь."
            ),
            parse_mode="HTML",
        )

    except Exception:
        pass


# ============================================================
# INVENTORY
# ============================================================

@router.callback_query(
    F.data == "view_inv"
)
async def view_inv(
    callback: CallbackQuery,
) -> None:

    user_id = callback.from_user.id

    balance, items_count = (
        await get_inventory_summary(
            user_id
        )
    )

    items = await get_inventory_items(
        user_id
    )

    lines = []

    for index, item in enumerate(
        items,
        start=1,
    ):

        name = escape_html(
            item["skin_name"]
            or "Unknown Skin"
        )

        price = float(
            item["estimated_price"]
            or 0
        )

        lines.append(
            f"{index}. {name} — "
            f"{price:.2f} G"
        )

    text = (
        "🎒 <b>ВАШ ИНВЕНТАРЬ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Предметов:</b> "
        f"{items_count}\n"
        f"💰 <b>Оценочная стоимость:</b> "
        f"{balance:.2f} G\n\n"
    )

    if lines:

        text += (
            "<b>Предметы:</b>\n"
            + "\n".join(lines)
        )

    else:

        text += (
            "Инвентарь пуст.\n\n"
            "Запустите мониторинг рынка "
            "для поиска доступных лотов."
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 ВЫВЕСТИ СКИНЫ",
                    callback_data=(
                        "start_withdraw"
                    ),
                )
            ],
        ]
    )

    await callback.message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# WITHDRAW
# ============================================================

@router.callback_query(
    F.data == "start_withdraw"
)
async def start_withdraw(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    user_id = callback.from_user.id

    user_data = await get_user(
        user_id
    )

    if not user_data:
        await callback.answer(
            "Ошибка профиля.",
            show_alert=True,
        )
        return

    status = await get_user_status(
        user_data
    )

    if status != "PREMIUM":

        await callback.answer(
            (
                "👑 Для вывода скинов "
                "необходимо активировать "
                "Premium."
            ),
            show_alert=True,
        )

        await callback.message.answer(
            (
                "👑 <b>ВЫВОД СКИНОВ</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Для создания заявки на вывод "
                "необходимо активировать "
                f"<b>PREMIUM</b> за "
                f"<b>{PREMIUM_PRICE} 🌟</b>.\n\n"
                "После активации Premium "
                "вы сможете создать заявку "
                "на вывод предметов."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=(
                                f"👑 PREMIUM "
                                f"({PREMIUM_PRICE} 🌟)"
                            ),
                            callback_data=(
                                "activate_premium"
                            ),
                        )
                    ],
                ]
            ),
            parse_mode="HTML",
        )

        return

    items = await get_inventory_items(
        user_id
    )

    if not items:

        await callback.answer(
            "Инвентарь пуст.",
            show_alert=True,
        )

        return

    await callback.answer()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ ОТМЕНА",
                    callback_data=(
                        "cancel_withdraw"
                    ),
                )
            ]
        ]
    )

    await callback.message.answer(
        (
            "📦 <b>ЗАЯВКА НА ВЫВОД</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Введите ваш <b>игровой ID</b> "
            "Standoff 2.\n\n"
            "После создания заявки она "
            "поступит на обработку.\n\n"
            "⏱ Срок обработки: "
            f"<b>до {WITHDRAW_PROCESSING_HOURS} "
            "часов</b>."
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await state.set_state(
        WithdrawStates.waiting_id
    )


@router.callback_query(
    F.data == "cancel_withdraw"
)
async def cancel_withdraw(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:

    await state.clear()

    await callback.answer(
        "Заявка отменена.",
        show_alert=True,
    )


# ============================================================
# CREATE WITHDRAWAL REQUEST
# ============================================================

@router.message(
    WithdrawStates.waiting_id
)
async def withdraw_id_received(
    message: Message,
    state: FSMContext,
) -> None:

    user_id = message.from_user.id

    game_id = (
        message.text or ""
    ).strip()

    if not game_id:

        await message.answer(
            "⚠️ Игровой ID не может быть пустым."
        )

        return

    if len(game_id) > 100:

        await message.answer(
            "⚠️ Слишком длинный игровой ID."
        )

        return

    user_data = await get_user(
        user_id
    )

    if not user_data:

        await state.clear()

        await message.answer(
            "Ошибка профиля."
        )

        return

    status = await get_user_status(
        user_data
    )

    if status != "PREMIUM":

        await state.clear()

        await message.answer(
            (
                "👑 <b>ВЫВОД НЕДОСТУПЕН</b>\n\n"
                "Для создания заявки "
                "необходимо активировать "
                "Premium."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=(
                                f"👑 PREMIUM "
                                f"({PREMIUM_PRICE} 🌟)"
                            ),
                            callback_data=(
                                "activate_premium"
                            ),
                        )
                    ]
                ]
            ),
            parse_mode="HTML",
        )

        return

    items = await get_inventory_items(
        user_id
    )

    if not items:

        await state.clear()

        await message.answer(
            "🎒 Инвентарь пуст. "
            "Создать заявку на вывод невозможно."
        )

        return

    items_count = len(items)

    total_value = sum(
        float(
            item["estimated_price"]
            or 0
        )
        for item in items
    )

    created_at = int(
        time.time()
    )

    estimated_completion = (
        created_at
        + WITHDRAW_PROCESSING_HOURS
        * 60
        * 60
    )

    async with aiosqlite.connect(DB_PATH) as db:

        cursor = await db.execute(
            """
            INSERT INTO withdrawals (
                user_id,
                game_id,
                items_count,
                total_value,
                status,
                created_at,
                estimated_completion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                game_id,
                items_count,
                total_value,
                "PENDING",
                created_at,
                estimated_completion,
            ),
        )

        withdrawal_id = cursor.lastrowid

        await db.commit()

    await state.clear()

    await message.answer(
        (
            "✅ <b>ЗАЯВКА СОЗДАНА</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 Номер заявки: "
            f"<code>#{withdrawal_id}</code>\n"
            f"🎮 Игровой ID: "
            f"<code>{escape_html(game_id)}</code>\n"
            f"📦 Предметов: "
            f"<b>{items_count}</b>\n"
            f"💰 Оценочная стоимость: "
            f"<b>{total_value:.2f} G</b>\n\n"
            "📋 <b>Статус:</b> В очереди\n"
            f"⏱ <b>Срок обработки:</b> "
            f"до {WITHDRAW_PROCESSING_HOURS} часов\n\n"
            "Заявка зарегистрирована. "
            "Срок обработки является "
            "максимальным ориентиром и "
            "может изменяться в зависимости "
            "от обработки заявки."
        ),
        parse_mode="HTML",
    )


# ============================================================
# PREMIUM
# ============================================================

@router.callback_query(
    F.data == "activate_premium"
)
async def activate_premium(
    callback: CallbackQuery,
) -> None:

    await callback.answer()

    user_id = callback.from_user.id

    await bot.send_invoice(
        chat_id=user_id,
        title="👑 PREMIUM на 24 часа",
        description=(
            "Premium-доступ на 24 часа.\n"
            "• Продолжение мониторинга\n"
            "• Доступ к Premium-функциям\n"
            "• Возможность создавать заявки "
            "на вывод предметов"
        ),
        payload="premium_24h",
        provider_token="",
        currency="XTR",
        prices=[
            {
                "label": "PREMIUM на 24 часа",
                "amount": PREMIUM_PRICE,
            }
        ],
    )


@router.pre_checkout_query()
async def pre_checkout_query_handler(
    query: PreCheckoutQuery,
) -> None:

    await query.answer(
        ok=True
    )


@router.message(
    F.successful_payment
)
async def successful_payment_handler(
    message: Message,
) -> None:

    user_id = message.from_user.id

    payment = message.successful_payment

    if (
        payment.invoice_payload
        == "premium_24h"
    ):

        current_time = int(
            time.time()
        )

        user_data = await get_user(
            user_id
        )

        current_premium_until = int(
            user_data.get(
                "premium_until",
                0,
            )
            or 0
        ) if user_data else 0

        base_time = max(
            current_time,
            current_premium_until,
        )

        premium_until = (
            base_time
            + 24 * 60 * 60
        )

        await update_user(
            user_id,
            status="PREMIUM",
            premium_until=premium_until,
        )

        await message.answer(
            (
                "👑 <b>PREMIUM АКТИВИРОВАН</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "✅ Доступ активирован.\n"
                "⏱ Срок: <b>24 часа</b>.\n"
                "🎯 Мониторинг доступен.\n"
                "📦 Доступно создание заявок "
                "на вывод.\n\n"
                "Вы можете продолжить "
                "мониторинг рынка."
            ),
            parse_mode="HTML",
        )

    else:

        await message.answer(
            "✅ Оплата получена.",
            parse_mode="HTML",
        )


# ============================================================
# WITHDRAWAL STATUS
# ============================================================

async def get_latest_withdrawal(
    user_id: int,
) -> dict | None:

    async with aiosqlite.connect(DB_PATH) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(
            """
            SELECT *
            FROM withdrawals
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ) as cursor:

            row = await cursor.fetchone()

            return dict(row) if row else None


# ============================================================
# ADMIN
# ============================================================

async def _admin_stats() -> dict:

    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        ) as cursor:

            total = (
                await cursor.fetchone()
            )[0]

        async with db.execute(
            """
            SELECT COUNT(*)
            FROM users
            WHERE status = 'PREMIUM'
            AND premium_until > ?
            """,
            (int(time.time()),),
        ) as cursor:

            premium = (
                await cursor.fetchone()
            )[0]

        async with db.execute(
            """
            SELECT COUNT(*)
            FROM withdrawals
            WHERE status = 'PENDING'
            """
        ) as cursor:

            pending_withdrawals = (
                await cursor.fetchone()
            )[0]

    return {
        "total": total,
        "premium": premium,
        "pending_withdrawals": (
            pending_withdrawals
        ),
    }


async def show_admin_panel(
    chat_id: int,
) -> None:

    stats = await _admin_stats()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "🔄 Сбросить "
                        "бесплатное время"
                    ),
                    callback_data=(
                        "admin_reset_time"
                    ),
                )
            ]
        ]
    )

    text = (
        "🛠 <b>ADMIN PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Пользователей: "
        f"{stats['total']}\n"
        f"👑 Активный Premium: "
        f"{stats['premium']}\n"
        f"📦 Заявок на вывод: "
        f"{stats['pending_withdrawals']}\n"
    )

    await bot.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.message(
    Command("admin")
)
async def admin_cmd(
    message: Message,
) -> None:

    if not _is_admin(
        message.from_user.id
    ):

        await message.answer(
            "🚫 Доступ запрещён.",
            parse_mode="HTML",
        )

        return

    await show_admin_panel(
        message.chat.id
    )


@router.callback_query(
    F.data == "admin_reset_time"
)
async def admin_reset_time(
    callback: CallbackQuery,
) -> None:

    if not _is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "🚫 Доступ запрещён.",
            show_alert=True,
        )

        return

    now = int(
        time.time()
    )

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            """
            UPDATE users
            SET free_time_left = ?,
                last_daily_reset = ?
            WHERE status = 'FREE'
            """,
            (
                FREE_TIME_DEFAULT,
                now,
            ),
        )

        await db.commit()

        cursor = await db.execute(
            "SELECT changes()"
        )

        row = await cursor.fetchone()

        affected = (
            row[0]
            if row
            else 0
        )

    await callback.answer(
        (
            f"✅ Бесплатное время "
            f"сброшено у {affected} "
            f"пользователей."
        ),
        show_alert=True,
    )


# ============================================================
# REGISTER ROUTER
# ============================================================

dp.include_router(
    router
)


# ============================================================
# MAIN
# ============================================================

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