import asyncio
import html
import os
import re
from typing import Optional

import sys
import subprocess

try:
    import aiogram
except ModuleNotFoundError:
    print("📦 aiogram не найден. Устанавливаю...")
    subprocess.check_call([
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        "aiogram==3.22.0",
    ])

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from dotenv import load_dotenv

from ai import AIAnalyzer
from avito import PublicAvitoProvider
from models import Listing, SearchFilters
from ranking import prepare_candidates, sort_by_ai
from storage import JSONStorage


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не установлен. Добавь BOT_TOKEN в Variables Railway."
    )

try:
    MAX_RESULTS = max(
        1,
        int(os.getenv("MAX_RESULTS", "10")),
    )
except ValueError:
    MAX_RESULTS = 10

DATA_DIR = os.getenv("DATA_DIR", "data")


# ============================================================
# BOT
# ============================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML,
    ),
)

dp = Dispatcher()

storage = JSONStorage(DATA_DIR)
ai = AIAnalyzer()
avito = PublicAvitoProvider()


# ============================================================
# USER STATE
# ============================================================

user_states: dict[int, dict] = {}


def state_for(user_id: int) -> dict:
    if user_id not in user_states:
        user_states[user_id] = {
            "filters": SearchFilters(),
            "results": [],
            "awaiting": None,
        }

    return user_states[user_id]


# ============================================================
# HELPERS
# ============================================================

def esc(value) -> str:
    if value is None:
        return ""

    return html.escape(str(value))


def money(value: Optional[int]) -> str:
    if value is None:
        return "—"

    return f"{int(value):,}".replace(",", " ") + " ₽"


def parse_budget(value: str) -> int:
    """
    Поддерживает:

    80000
    80 000
    80к
    80k
    80 000 ₽
    """

    if not value:
        raise ValueError

    s = value.lower().strip()

    s = s.replace("\xa0", " ")
    s = s.replace("₽", "")
    s = s.replace("руб.", "")
    s = s.replace("руб", "")

    s = re.sub(r"\s+", "", s)

    if s.endswith("к"):
        number = s[:-1].replace(",", ".")

        amount = int(float(number) * 1000)

        if amount <= 0:
            raise ValueError

        return amount

    if s.endswith("k"):
        number = s[:-1].replace(",", ".")

        amount = int(float(number) * 1000)

        if amount <= 0:
            raise ValueError

        return amount

    digits = re.sub(r"[^\d]", "", s)

    if not digits:
        raise ValueError

    amount = int(digits)

    if amount <= 0:
        raise ValueError

    return amount


def tier_emoji(tier: str) -> str:
    return {
        "S": "🏆",
        "A": "🥇",
        "B": "🥈",
        "C": "🥉",
        "D": "⚠️",
    }.get(
        tier,
        "📱",
    )


def verdict(value: str) -> str:
    return {
        "BUY": "🟢 ПОКУПАТЬ",
        "GOOD": "🟢 ХОРОШИЙ ВАРИАНТ",
        "CAUTION": "🟡 ОСТОРОЖНО",
        "AVOID": "🔴 НЕ БРАТЬ",
    }.get(
        value,
        "🟡 ПРОВЕРИТЬ",
    )


# ============================================================
# IPHONE MODELS
# ============================================================

MODELS = [
    "iPhone 11",
    "iPhone 11 Pro",
    "iPhone 11 Pro Max",

    "iPhone 12",
    "iPhone 12 mini",
    "iPhone 12 Pro",
    "iPhone 12 Pro Max",

    "iPhone 13",
    "iPhone 13 mini",
    "iPhone 13 Pro",
    "iPhone 13 Pro Max",

    "iPhone 14",
    "iPhone 14 Plus",
    "iPhone 14 Pro",
    "iPhone 14 Pro Max",

    "iPhone 15",
    "iPhone 15 Plus",
    "iPhone 15 Pro",
    "iPhone 15 Pro Max",

    "iPhone 16",
    "iPhone 16 Plus",
    "iPhone 16 Pro",
    "iPhone 16 Pro Max",

    "iPhone 17",
    "iPhone 17 Pro",
    "iPhone 17 Pro Max",

    "iPhone Air",
]


# ============================================================
# MAIN KEYBOARD
# ============================================================

def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔎 Новый поиск",
                    callback_data="search:new",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💾 Последний поиск",
                    callback_data="search:last",
                )
            ],
        ]
    )


# ============================================================
# MODELS KEYBOARD
# ============================================================

def models_keyboard(selected: list[str]):
    rows = []

    for i in range(0, len(MODELS), 2):

        row = []

        for model in MODELS[i:i + 2]:

            mark = "✅ " if model in selected else ""

            row.append(
                InlineKeyboardButton(
                    text=mark + model,
                    callback_data="model:" + model,
                )
            )

        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                text="➡️ Далее",
                callback_data="models:done",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# ============================================================
# BUDGET KEYBOARD
# ============================================================

def budget_keyboard():

    values = [
        30000,
        50000,
        70000,
        90000,
        120000,
        150000,
    ]

    rows = []

    for i in range(0, len(values), 2):

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"до {money(values[i])}",
                    callback_data=f"budget:{values[i]}",
                ),
                InlineKeyboardButton(
                    text=f"до {money(values[i + 1])}",
                    callback_data=f"budget:{values[i + 1]}",
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="💰 Ввести самому",
                callback_data="budget:custom",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# ============================================================
# FILTERS KEYBOARD
# ============================================================

def filters_keyboard(filters: SearchFilters):

    storage_text = (
        ", ".join(
            f"{x} GB" if x < 1024 else "1 TB"
            for x in filters.storage
        )
        or "любая"
    )

    battery_text = (
        f"{filters.min_battery}%+"
        if filters.min_battery
        else "любая"
    )

    repair_text = {
        "any": "любой",
        "none": "без ремонта",
        "changed": "с ремонтом",
    }.get(
        filters.repair_policy,
        "любой",
    )

    screen_text = {
        "any": "любой",
        "original": "оригинальный",
        "no_damage": "без повреждений",
    }.get(
        filters.screen_policy,
        "любой",
    )

    city_text = filters.city or "любой"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💾 Память: {storage_text}",
                    callback_data="filter:storage",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔋 АКБ: {battery_text}",
                    callback_data="filter:battery",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔧 Ремонт: {repair_text}",
                    callback_data="filter:repair",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📺 Экран: {screen_text}",
                    callback_data="filter:screen",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🏙 Город: {city_text}",
                    callback_data="filter:city",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔎 НАЧАТЬ ПОИСК",
                    callback_data="search:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="search:new",
                )
            ],
        ]
    )


# ============================================================
# FILTERS DISPLAY
# ============================================================

async def show_filters_message(
    message: Message,
    filters: SearchFilters,
):

    models = (
        ", ".join(filters.models)
        if filters.models
        else "не выбраны"
    )

    text = (
        "⚙️ <b>ПАРАМЕТРЫ ПОИСКА</b>\n\n"
        f"📱 <b>Модель:</b> {esc(models)}\n"
        f"💰 <b>Бюджет:</b> до {money(filters.max_price)}\n"
        "━━━━━━━━━━━━\n"
        "Настрой дополнительные фильтры."
    )

    await message.answer(
        text,
        reply_markup=filters_keyboard(filters),
    )


async def show_filters_callback(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    await callback.message.edit_text(
        (
            "⚙️ <b>ПАРАМЕТРЫ ПОИСКА</b>\n\n"
            f"📱 <b>Модель:</b> "
            f"{esc(', '.join(state['filters'].models))}\n"
            f"💰 <b>Бюджет:</b> "
            f"до {money(state['filters'].max_price)}\n"
            "━━━━━━━━━━━━\n"
            "Настрой дополнительные фильтры."
        ),
        reply_markup=filters_keyboard(
            state["filters"]
        ),
    )

    await callback.answer()


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start(message: Message):

    state_for(
        message.from_user.id
    )

    await storage.get_user(
        message.from_user.id
    )

    await message.answer(
        "📱 <b>iPhone Finder</b>\n\n"
        "Найду объявления iPhone, "
        "отфильтрую их по твоим условиям "
        "и дам ИИ-оценку каждого варианта.",
        reply_markup=main_keyboard(),
    )


# ============================================================
# HOME
# ============================================================

@dp.callback_query(F.data == "home")
async def home(callback: CallbackQuery):

    await callback.message.edit_text(
        "📱 <b>iPhone Finder</b>\n\n"
        "Что делаем?",
        reply_markup=main_keyboard(),
    )

    await callback.answer()


# ============================================================
# NEW SEARCH
# ============================================================

@dp.callback_query(F.data == "search:new")
async def new_search(
    callback: CallbackQuery,
):

    user_states[
        callback.from_user.id
    ] = {
        "filters": SearchFilters(),
        "results": [],
        "awaiting": None,
    }

    await callback.message.edit_text(
        "📱 <b>ВЫБОР МОДЕЛИ</b>\n\n"
        "Можно выбрать несколько моделей.",
        reply_markup=models_keyboard([]),
    )

    await callback.answer()


# ============================================================
# MODEL SELECT
# ============================================================

@dp.callback_query(
    F.data.startswith("model:")
)
async def model_select(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    model = callback.data[
        len("model:"):
    ]

    selected = state["filters"].models

    if model in selected:
        selected.remove(model)
        await callback.answer(
            f"Убрано: {model}"
        )
    else:
        selected.append(model)
        await callback.answer(
            f"Добавлено: {model}"
        )

    await callback.message.edit_reply_markup(
        reply_markup=models_keyboard(
            selected
        )
    )


# ============================================================
# MODELS DONE
# ============================================================

@dp.callback_query(F.data == "models:done")
async def models_done(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    if not state["filters"].models:

        await callback.answer(
            "Выбери хотя бы одну модель.",
            show_alert=True,
        )

        return

    await callback.message.edit_text(
        "💰 <b>МАКСИМАЛЬНЫЙ БЮДЖЕТ</b>\n\n"
        "Выбери готовый вариант или "
        "нажми «Ввести самому».",
        reply_markup=budget_keyboard(),
    )

    await callback.answer()


# ============================================================
# BUDGET SELECT
# ============================================================

@dp.callback_query(
    F.data.startswith("budget:")
)
async def budget_select(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    value = callback.data[
        len("budget:"):
    ]

    if value == "custom":

        state["awaiting"] = "budget"

        await callback.message.edit_text(
            "💰 <b>ВВОД БЮДЖЕТА</b>\n\n"
            "Напиши максимальный бюджет.\n\n"
            "Примеры:\n"
            "<code>80000</code>\n"
            "<code>80 000</code>\n"
            "<code>80к</code>"
        )

        await callback.answer()

        return

    state["filters"].max_price = int(
        value
    )

    state["awaiting"] = None

    await show_filters_callback(
        callback
    )


# ============================================================
# STORAGE MENU
# ============================================================

@dp.callback_query(
    F.data == "filter:storage"
)
async def storage_menu(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    await callback.message.edit_text(
        "💾 <b>ПАМЯТЬ</b>\n\n"
        "Можно выбрать несколько.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="128 GB",
                        callback_data="storage:128",
                    ),
                    InlineKeyboardButton(
                        text="256 GB",
                        callback_data="storage:256",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="512 GB",
                        callback_data="storage:512",
                    ),
                    InlineKeyboardButton(
                        text="1 TB",
                        callback_data="storage:1024",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Сбросить",
                        callback_data="storage:reset",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="filter:back",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


# ============================================================
# STORAGE SELECT
# ============================================================

@dp.callback_query(
    F.data.startswith("storage:")
)
async def storage_select(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    value = callback.data[
        len("storage:"):
    ]

    if value == "reset":

        state["filters"].storage = []

    else:

        gb = int(value)

        if gb in state["filters"].storage:
            state["filters"].storage.remove(gb)
        else:
            state["filters"].storage.append(gb)

    await callback.answer(
        "Сохранено"
    )


# ============================================================
# BATTERY MENU
# ============================================================

@dp.callback_query(
    F.data == "filter:battery"
)
async def battery_menu(
    callback: CallbackQuery,
):

    await callback.message.edit_text(
        "🔋 <b>АККУМУЛЯТОР</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="80%+",
                        callback_data="battery:80",
                    ),
                    InlineKeyboardButton(
                        text="85%+",
                        callback_data="battery:85",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="90%+",
                        callback_data="battery:90",
                    ),
                    InlineKeyboardButton(
                        text="95%+",
                        callback_data="battery:95",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Неважно",
                        callback_data="battery:reset",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="filter:back",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


# ============================================================
# BATTERY SELECT
# ============================================================

@dp.callback_query(
    F.data.startswith("battery:")
)
async def battery_select(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    value = callback.data[
        len("battery:"):
    ]

    state["filters"].min_battery = (
        None
        if value == "reset"
        else int(value)
    )

    await callback.answer(
        "Сохранено"
    )

    await show_filters_callback(
        callback
    )


# ============================================================
# REPAIR MENU
# ============================================================

@dp.callback_query(
    F.data == "filter:repair"
)
async def repair_menu(
    callback: CallbackQuery,
):

    await callback.message.edit_text(
        "🔧 <b>РЕМОНТ</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Без ремонта",
                        callback_data="repair:none",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔧 С ремонтом",
                        callback_data="repair:changed",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Любой",
                        callback_data="repair:any",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="filter:back",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


# ============================================================
# REPAIR SELECT
# ============================================================

@dp.callback_query(
    F.data.startswith("repair:")
)
async def repair_select(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    state["filters"].repair_policy = (
        callback.data.split(
            ":",
            1,
        )[1]
    )

    await show_filters_callback(
        callback
    )


# ============================================================
# SCREEN MENU
# ============================================================

@dp.callback_query(
    F.data == "filter:screen"
)
async def screen_menu(
    callback: CallbackQuery,
):

    await callback.message.edit_text(
        "📺 <b>ЭКРАН</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Оригинальный",
                        callback_data="screen:original",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Без повреждений",
                        callback_data="screen:no_damage",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Любой",
                        callback_data="screen:any",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="filter:back",
                    )
                ],
            ]
        ),
    )

    await callback.answer()


# ============================================================
# SCREEN SELECT
# ============================================================

@dp.callback_query(
    F.data.startswith("screen:")
)
async def screen_select(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    state["filters"].screen_policy = (
        callback.data.split(
            ":",
            1,
        )[1]
    )

    await show_filters_callback(
        callback
    )


# ============================================================
# CITY MENU
# ============================================================

@dp.callback_query(
    F.data == "filter:city"
)
async def city_menu(
    callback: CallbackQuery,
):

    state_for(
        callback.from_user.id
    )["awaiting"] = "city"

    await callback.message.edit_text(
        "🏙 <b>ГОРОД</b>\n\n"
        "Напиши город.\n\n"
        "Например:\n"
        "<code>Москва</code>"
    )

    await callback.answer()


# ============================================================
# FILTER BACK
# ============================================================

@dp.callback_query(
    F.data == "filter:back"
)
async def filter_back(
    callback: CallbackQuery,
):

    await show_filters_callback(
        callback
    )


# ============================================================
# TEXT INPUT
# ============================================================

@dp.message(F.text)
async def text_input(
    message: Message,
):

    state = state_for(
        message.from_user.id
    )

    awaiting = state.get(
        "awaiting"
    )

    # --------------------------------------------------------
    # CUSTOM BUDGET
    # --------------------------------------------------------

    if awaiting == "budget":

        try:

            amount = parse_budget(
                message.text
            )

        except ValueError:

            await message.answer(
                "❌ <b>Не понял сумму.</b>\n\n"
                "Примеры:\n"
                "<code>80000</code>\n"
                "<code>80 000</code>\n"
                "<code>80к</code>"
            )

            return

        state["filters"].max_price = amount
        state["awaiting"] = None

        await message.answer(
            f"💰 Бюджет сохранён: "
            f"<b>{money(amount)}</b>"
        )

        await show_filters_message(
            message,
            state["filters"],
        )

        return

    # --------------------------------------------------------
    # CITY
    # --------------------------------------------------------

    if awaiting == "city":

        city = message.text.strip()

        if len(city) < 2:

            await message.answer(
                "❌ Слишком короткое "
                "название города."
            )

            return

        state["filters"].city = city
        state["awaiting"] = None

        await show_filters_message(
            message,
            state["filters"],
        )

        return


# ============================================================
# START SEARCH
# ============================================================

@dp.callback_query(
    F.data == "search:start"
)
async def start_search(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    filters: SearchFilters = (
        state["filters"]
    )

    if not filters.models:

        await callback.answer(
            "Не выбрана модель.",
            show_alert=True,
        )

        return

    if not filters.max_price:

        await callback.answer(
            "Не установлен бюджет.",
            show_alert=True,
        )

        return

    await callback.message.edit_text(
        "🔎 <b>ИЩУ ОБЪЯВЛЕНИЯ...</b>\n\n"
        "Получаю публичные объявления "
        "и отбираю подходящие варианты."
    )

    await callback.answer()

    try:

        # ----------------------------------------------------
        # SEARCH
        # ----------------------------------------------------

        listings = await avito.search(
            filters
        )

        candidates = prepare_candidates(
            listings,
            filters,
        )

        candidates = candidates[
            :MAX_RESULTS
        ]

        if not candidates:

            await callback.message.edit_text(
                "😕 <b>Подходящих объявлений "
                "не найдено.</b>\n\n"
                "Попробуй увеличить бюджет "
                "или убрать фильтры.",
                reply_markup=main_keyboard(),
            )

            return

        # ----------------------------------------------------
        # AI
        # ----------------------------------------------------

        results = []

        for i, listing in enumerate(
            candidates,
            1,
        ):

            try:

                await callback.message.edit_text(
                    f"🤖 <b>Анализирую "
                    f"{i}/{len(candidates)}</b>\n\n"
                    f"{esc(listing.title[:100])}"
                )

                await ai.analyze(
                    listing,
                    filters,
                )

                results.append(
                    listing
                )

            except Exception as exc:

                print(
                    "ANALYZE ERROR:",
                    exc,
                )

        # ----------------------------------------------------
        # SORT
        # ----------------------------------------------------

        results = sort_by_ai(
            results
        )

        state["results"] = results

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        await storage.set_search(
            callback.from_user.id,
            {
                "filters": filters.to_dict(),
                "results": [
                    x.to_dict(
                        include_raw=False
                    )
                    for x in results
                ],
            },
        )

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        await callback.message.edit_text(
            build_results(results),
            reply_markup=results_keyboard(
                results
            ),
        )

    except Exception as exc:

        print(
            "SEARCH ERROR:",
            repr(exc),
        )

        await callback.message.edit_text(
            "❌ <b>Ошибка поиска</b>\n\n"
            f"<code>{esc(str(exc)[:1000])}</code>\n\n"
            "Попробуй повторить поиск позже.",
            reply_markup=main_keyboard(),
        )


# ============================================================
# RESULTS KEYBOARD
# ============================================================

def results_keyboard(
    listings: list[Listing],
):

    rows = []

    for i, item in enumerate(
        listings
    ):

        analysis = item.ai_analysis

        score = (
            analysis.score
            if analysis
            else 0
        )

        tier = (
            analysis.tier
            if analysis
            else "D"
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{i + 1}️⃣ "
                        f"{tier} • "
                        f"{score}/100 • "
                        f"{money(item.price)}"
                    ),
                    callback_data=f"listing:{i}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔎 Новый поиск",
                callback_data="search:new",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# ============================================================
# RESULTS TEXT
# ============================================================

def build_results(
    listings: list[Listing],
) -> str:

    lines = [
        "🏆 <b>ТОП ВАРИАНТОВ</b>",
        "",
        f"Найдено: <b>{len(listings)}</b>",
        "",
    ]

    for i, item in enumerate(
        listings,
        1,
    ):

        analysis = item.ai_analysis

        if not analysis:
            continue

        lines += [
            (
                f"{i}️⃣ "
                f"{tier_emoji(analysis.tier)} "
                f"<b>{esc(item.model or item.title)}</b>"
            ),
            (
                f"💰 {money(item.price)} "
                f"• ⭐ {analysis.score}/100"
            ),
            verdict(
                analysis.verdict
            ),
            (
                f"📝 "
                f"{esc(analysis.summary[:220])}"
            ),
            "",
        ]

    return "\n".join(lines)


# ============================================================
# DETAIL KEYBOARD
# ============================================================

def detail_keyboard(
    item: Listing,
    index: int,
):

    rows = []

    if item.url:

        rows.append(
            [
                InlineKeyboardButton(
                    text="🔗 Открыть объявление",
                    url=item.url,
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад к списку",
                callback_data="results:back",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


# ============================================================
# DETAIL TEXT
# ============================================================

def build_detail(
    item: Listing,
    index: int,
) -> str:

    analysis = item.ai_analysis

    lines = [
        f"📱 <b>{esc(item.title)}</b>",
        f"💰 <b>{money(item.price)}</b>",
        (
            f"🏆 "
            f"{tier_emoji(analysis.tier) if analysis else '📱'} "
            f"<b>{analysis.score if analysis else 0}/100</b>"
        ),
        (
            verdict(analysis.verdict)
            if analysis
            else "🟡 ПРОВЕРИТЬ"
        ),
        "",
        (
            f"💾 Память: "
            f"{item.storage_gb or 'не указано'}"
        ),
        (
            f"🔋 АКБ: "
            f"{str(item.battery_percent) + '%' if item.battery_percent else 'не указано'}"
        ),
        (
            f"📱 Состояние: "
            f"{esc(item.condition or 'не указано')}"
        ),
        (
            f"🎨 Цвет: "
            f"{esc(item.color or 'не указано')}"
        ),
        (
            f"🔧 Ремонт: "
            f"{esc(item.repair_info or 'не указано')}"
        ),
        (
            f"📺 Экран: "
            f"{esc(item.screen_info or 'не указано')}"
        ),
        (
            f"👤 Продавец: "
            f"{esc(item.seller_name or 'не указано')}"
        ),
        (
            f"⭐ Рейтинг: "
            f"{item.seller_rating if item.seller_rating is not None else 'не указано'}"
        ),
        (
            f"🏙 Город: "
            f"{esc(item.city or 'не указано')}"
        ),
        "",
    ]

    if analysis:

        lines += [
            "🤖 <b>АНАЛИЗ ИИ</b>",
            esc(analysis.summary),
            "",
        ]

        if analysis.advantages:

            lines += [
                "✅ <b>ПЛЮСЫ</b>"
            ]

            lines += [
                f"• {esc(x)}"
                for x in analysis.advantages
            ]

            lines.append("")

        if analysis.risks:

            lines += [
                "⚠️ <b>РИСКИ</b>"
            ]

            lines += [
                f"• {esc(x)}"
                for x in analysis.risks
            ]

            lines.append("")

        if analysis.checks:

            lines += [
                "🔍 <b>ПРОВЕРИТЬ</b>"
            ]

            lines += [
                f"• {esc(x)}"
                for x in analysis.checks
            ]

            lines.append("")

    if item.description:

        lines += [
            "📝 <b>ОПИСАНИЕ</b>",
            esc(
                item.description[:3000]
            ),
        ]

    return "\n".join(lines)


# ============================================================
# LISTING DETAIL
# ============================================================

@dp.callback_query(
    F.data.startswith("listing:")
)
async def listing_detail(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    try:

        index = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )

        item = state["results"][index]

    except Exception:

        await callback.answer(
            "Объявление больше недоступно.",
            show_alert=True,
        )

        return

    # --------------------------------------------------------
    # PHOTOS
    # --------------------------------------------------------

    if item.photos:

        media = [
            InputMediaPhoto(
                media=url
            )
            for url in item.photos[:10]
        ]

        try:

            await callback.message.answer_media_group(
                media
            )

        except Exception as exc:

            print(
                "PHOTO ERROR:",
                exc,
            )

    # --------------------------------------------------------
    # DETAIL
    # --------------------------------------------------------

    await callback.message.edit_text(
        build_detail(
            item,
            index,
        ),
        reply_markup=detail_keyboard(
            item,
            index,
        ),
    )

    await callback.answer()


# ============================================================
# RESULTS BACK
# ============================================================

@dp.callback_query(
    F.data == "results:back"
)
async def results_back(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    results = (
        state.get("results")
        or []
    )

    if not results:

        await callback.message.edit_text(
            "📱 <b>Нет результатов.</b>",
            reply_markup=main_keyboard(),
        )

        await callback.answer()

        return

    await callback.message.edit_text(
        build_results(results),
        reply_markup=results_keyboard(
            results
        ),
    )

    await callback.answer()


# ============================================================
# LAST SEARCH
# ============================================================

@dp.callback_query(
    F.data == "search:last"
)
async def last_search(
    callback: CallbackQuery,
):

    state = state_for(
        callback.from_user.id
    )

    results = (
        state.get("results")
        or []
    )

    if results:

        await callback.message.edit_text(
            build_results(results),
            reply_markup=results_keyboard(
                results
            ),
        )

        await callback.answer()

        return

    # Попробуем загрузить сохранённый поиск
    try:

        saved = await storage.get_search(
            callback.from_user.id
        )

    except Exception:

        saved = None

    if saved:

        try:

            saved_results = (
                saved.get("results")
                or []
            )

            results = [
                Listing.from_dict(
                    item
                )
                for item in saved_results
            ]

            state["results"] = results

            if results:

                await callback.message.edit_text(
                    build_results(results),
                    reply_markup=results_keyboard(
                        results
                    ),
                )

                await callback.answer()

                return

        except Exception as exc:

            print(
                "LOAD LAST SEARCH ERROR:",
                exc,
            )

    await callback.answer(
        "Последнего поиска пока нет.",
        show_alert=True,
    )


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.error()
async def global_error(
    event,
):

    print(
        "BOT ERROR:",
        repr(event.exception),
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "================================="
    )

    print(
        "📱 iPhone Finder"
    )

    print(
        "🚀 Bot started"
    )

    print(
        f"MAX_RESULTS={MAX_RESULTS}"
    )

    print(
        f"DATA_DIR={DATA_DIR}"
    )

    print(
        "================================="
    )

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":

    try:
        asyncio.run(
            main()
        )

    except (
        KeyboardInterrupt,
        SystemExit,
    ):

        print(
            "Bot stopped."
        )
