import asyncio
import html
import os
from dataclasses import asdict

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
from avito import APIAvitoProvider
from models import Listing, SearchFilters
from ranking import (
    prepare_candidates,
    sort_by_ai,
)
from storage import JSONStorage


load_dotenv()


BOT_TOKEN = os.getenv(
    "BOT_TOKEN"
)

MAX_RESULTS = int(
    os.getenv(
        "MAX_RESULTS",
        "10",
    )
)

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не установлен"
    )


bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML,
    ),
)

dp = Dispatcher()

storage = JSONStorage(
    os.getenv(
        "DATA_DIR",
        "data",
    )
)

ai = AIAnalyzer()

avito = APIAvitoProvider()


# ============================================================
# USER STATE
# ============================================================

user_states: dict[int, dict] = {}


def get_state(
    user_id: int,
) -> dict:

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

def esc(
    value,
) -> str:

    if value is None:
        return ""

    return html.escape(
        str(value)
    )


def money(
    value: int | None,
) -> str:

    if value is None:
        return "—"

    return (
        f"{value:,}"
        .replace(",", " ")
        + " ₽"
    )


def verdict(
    value: str,
) -> str:

    return {
        "BUY":
            "🟢 ПОКУПАТЬ",

        "GOOD":
            "🟢 ХОРОШИЙ ВАРИАНТ",

        "CAUTION":
            "🟡 ОСТОРОЖНО",

        "AVOID":
            "🔴 НЕ БРАТЬ",
    }.get(
        value,
        "🟡 ПРОВЕРИТЬ",
    )


def tier_emoji(
    tier: str,
) -> str:

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
                ),
                InlineKeyboardButton(
                    text="⭐ Избранное",
                    callback_data="favorites",
                ),
            ],
        ]
    )


# ============================================================
# MODEL KEYBOARD
# ============================================================

MODELS = [
    "iPhone 13",
    "iPhone 13 Pro",
    "iPhone 13 Pro Max",
    "iPhone 14",
    "iPhone 14 Pro",
    "iPhone 14 Pro Max",
    "iPhone 15",
    "iPhone 15 Pro",
    "iPhone 15 Pro Max",
    "iPhone 16",
    "iPhone 16 Plus",
    "iPhone 16 Pro",
    "iPhone 16 Pro Max",
]


def models_keyboard(
    selected: list[str],
):

    rows = []

    for i in range(
        0,
        len(MODELS),
        2,
    ):

        row = []

        for model in MODELS[i:i + 2]:

            mark = (
                "✅ "
                if model in selected
                else ""
            )

            row.append(
                InlineKeyboardButton(
                    text=mark + model,
                    callback_data=(
                        "model:"
                        + model
                    ),
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
# BUDGET
# ============================================================

def budget_keyboard():

    values = [
        30000,
        40000,
        50000,
        60000,
        70000,
        100000,
    ]

    rows = []

    for i in range(
        0,
        len(values),
        2,
    ):

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"до {money(values[i])}",
                    callback_data=(
                        f"budget:{values[i]}"
                    ),
                ),
                InlineKeyboardButton(
                    text=f"до {money(values[i + 1])}",
                    callback_data=(
                        f"budget:{values[i + 1]}"
                    ),
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
# FILTERS
# ============================================================

def filters_keyboard(
    filters: SearchFilters,
):

    storage = (
        ", ".join(
            str(x)
            for x in filters.storage
        )
        if filters.storage
        else "любая"
    )

    battery = (
        f"{filters.min_battery}%+"
        if filters.min_battery
        else "любая"
    )

    repair = {
        "any": "любой",
        "none": "без ремонта",
    }.get(
        filters.repair_policy,
        filters.repair_policy,
    )

    city = (
        filters.city
        if filters.city
        else "любой"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💾 Память: {storage}",
                    callback_data="filter:storage",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔋 АКБ: {battery}",
                    callback_data="filter:battery",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔧 Ремонт: {repair}",
                    callback_data="filter:repair",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🏙 Город: {city}",
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
                    callback_data="home",
                )
            ],
        ]
    )


# ============================================================
# START
# ============================================================

@dp.message(
    CommandStart()
)
async def start(
    message: Message,
):

    get_state(
        message.from_user.id
    )

    await storage.get_user(
        message.from_user.id
    )

    await message.answer(
        "📱 <b>iPhone Finder</b>\n\n"
        "Найду интересные iPhone "
        "по твоему бюджету.\n\n"
        "После поиска ИИ сравнит "
        "объявления и составит "
        "тир-лист.",
        reply_markup=main_keyboard(),
    )


# ============================================================
# HOME
# ============================================================

@dp.callback_query(
    F.data == "home"
)
async def home(
    callback: CallbackQuery,
):

    await callback.message.edit_text(
        "📱 <b>iPhone Finder</b>\n\n"
        "Что делаем?",
        reply_markup=main_keyboard(),
    )

    await callback.answer()


# ============================================================
# NEW SEARCH
# ============================================================

@dp.callback_query(
    F.data == "search:new"
)
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
        "📱 <b>Выбери iPhone</b>\n\n"
        "Можно выбрать несколько моделей.",
        reply_markup=models_keyboard([]),
    )

    await callback.answer()


# ============================================================
# MODEL
# ============================================================

@dp.callback_query(
    F.data.startswith("model:")
)
async def model_select(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    model = callback.data[
        len("model:")
    ]

    selected = (
        state["filters"].models
    )

    if model in selected:

        selected.remove(
            model
        )

    else:

        selected.append(
            model
        )

    await callback.message.edit_reply_markup(
        reply_markup=models_keyboard(
            selected
        )
    )

    await callback.answer()


# ============================================================
# MODELS DONE
# ============================================================

@dp.callback_query(
    F.data == "models:done"
)
async def models_done(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    if not state["filters"].models:

        await callback.answer(
            "Выбери хотя бы одну модель.",
            show_alert=True,
        )

        return

    await callback.message.edit_text(
        "💰 <b>Максимальный бюджет</b>",
        reply_markup=budget_keyboard(),
    )

    await callback.answer()


# ============================================================
# BUDGET
# ============================================================

@dp.callback_query(
    F.data.startswith("budget:")
)
async def budget_select(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    value = callback.data[
        len("budget:")
    ]

    if value == "custom":

        state["awaiting"] = (
            "budget"
        )

        await callback.message.edit_text(
            "💰 <b>Введи максимальный бюджет</b>\n\n"
            "Например:\n"
            "<code>65000</code>",
        )

        await callback.answer()

        return

    amount = int(value)

    state[
        "filters"
    ].max_price = amount

    await show_filters(
        callback,
        state["filters"],
    )


# ============================================================
# FILTER MENU
# ============================================================

async def show_filters(
    callback: CallbackQuery,
    filters: SearchFilters,
):

    models = ", ".join(
        filters.models
    )

    budget = money(
        filters.max_price
    )

    text = (
        "⚙️ <b>ПАРАМЕТРЫ ПОИСКА</b>\n\n"
        f"📱 {esc(models)}\n"
        f"💰 до {budget}\n\n"
        "Настрой дополнительные фильтры."
    )

    await callback.message.edit_text(
        text,
        reply_markup=filters_keyboard(
            filters
        ),
    )


# ============================================================
# STORAGE FILTER
# ============================================================

@dp.callback_query(
    F.data == "filter:storage"
)
async def storage_menu(
    callback: CallbackQuery,
):

    keyboard = InlineKeyboardMarkup(
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
    )

    await callback.message.edit_text(
        "💾 <b>ПАМЯТЬ</b>\n\n"
        "Можно выбрать несколько.",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("storage:")
)
async def storage_select(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    value = callback.data[
        len("storage:")
    ]

    if value == "reset":

        state[
            "filters"
        ].storage = []

    else:

        gb = int(value)

        if gb in state[
            "filters"
        ].storage:

            state[
                "filters"
            ].storage.remove(
                gb
            )

        else:

            state[
                "filters"
            ].storage.append(
                gb
            )

    await callback.answer(
        "Фильтр обновлён"
    )


# ============================================================
# BATTERY
# ============================================================

@dp.callback_query(
    F.data == "filter:battery"
)
async def battery_menu(
    callback: CallbackQuery,
):

    keyboard = InlineKeyboardMarkup(
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
    )

    await callback.message.edit_text(
        "🔋 <b>АККУМУЛЯТОР</b>\n\n"
        "Выбери минимальный процент.",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("battery:")
)
async def battery_select(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    value = callback.data[
        len("battery:")
    ]

    if value == "reset":

        state[
            "filters"
        ].min_battery = None

    else:

        state[
            "filters"
        ].min_battery = int(
            value
        )

    await callback.answer(
        "Фильтр обновлён"
    )


# ============================================================
# REPAIR
# ============================================================

@dp.callback_query(
    F.data == "filter:repair"
)
async def repair_menu(
    callback: CallbackQuery,
):

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔧 Без ремонта",
                    callback_data="repair:none",
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
    )

    await callback.message.edit_text(
        "🔧 <b>РЕМОНТ</b>",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("repair:")
)
async def repair_select(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    state[
        "filters"
    ].repair_policy = (
        callback.data.split(":")[1]
    )

    await callback.answer(
        "Фильтр обновлён"
    )


# ============================================================
# CITY
# ============================================================

@dp.callback_query(
    F.data == "filter:city"
)
async def city_menu(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    state["awaiting"] = "city"

    await callback.message.edit_text(
        "🏙 <b>ГОРОД</b>\n\n"
        "Напиши город.\n\n"
        "Например:\n"
        "<code>Москва</code>",
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

    state = get_state(
        callback.from_user.id
    )

    await show_filters(
        callback,
        state["filters"],
    )

    await callback.answer()


# ============================================================
# TEXT INPUT
# ============================================================

@dp.message(
    F.text
)
async def text_input(
    message: Message,
):

    state = get_state(
        message.from_user.id
    )

    awaiting = state.get(
        "awaiting"
    )

    if awaiting == "budget":

        raw = (
            message.text
            .replace(" ", "")
            .replace("₽", "")
        )

        try:

            amount = int(raw)

            if amount <= 0:
                raise ValueError

        except ValueError:

            await message.answer(
                "❌ Введи бюджет числом.\n\n"
                "Например: "
                "<code>65000</code>"
            )

            return

        state[
            "filters"
        ].max_price = amount

        state["awaiting"] = None

        await message.answer(
            f"💰 Бюджет: "
            f"<b>{money(amount)}</b>"
        )

        keyboard = filters_keyboard(
            state["filters"]
        )

        await message.answer(
            "⚙️ Теперь настрой фильтры.",
            reply_markup=keyboard,
        )

        return

    if awaiting == "city":

        city = message.text.strip()

        if len(city) < 2:

            await message.answer(
                "❌ Напиши нормальное название города."
            )

            return

        state[
            "filters"
        ].city = city

        state["awaiting"] = None

        await message.answer(
            f"🏙 Город: <b>{esc(city)}</b>",
            reply_markup=filters_keyboard(
                state["filters"]
            ),
        )


# ============================================================
# START SEARCH
# ============================================================

@dp.callback_query(
    F.data == "search:start"
)
async def start_search(
    callback: CallbackQuery,
):

    state = get_state(
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
        "🔎 <b>Ищу объявления...</b>\n\n"
        "Сначала получаю варианты, "
        "затем отбираю лучшие.",
    )

    await callback.answer()

    try:

        listings = await avito.search(
            filters
        )

        if not listings:

            await callback.message.edit_text(
                "😕 <b>Ничего не найдено.</b>\n\n"
                "Попробуй увеличить бюджет "
                "или убрать часть фильтров.",
                reply_markup=main_keyboard(),
            )

            return

        candidates = prepare_candidates(
            listings,
            filters,
        )

        if not candidates:

            await callback.message.edit_text(
                "😕 Объявления получены, "
                "но ни одно не прошло "
                "твои фильтры.",
                reply_markup=main_keyboard(),
            )

            return

        candidates = candidates[
            :MAX_RESULTS
        ]

        await callback.message.edit_text(
            "🤖 <b>Анализирую варианты...</b>\n\n"
            f"Проверяю: {len(candidates)}",
        )

        results = []

        for number, listing in enumerate(
            candidates,
            start=1,
        ):

            try:

                await callback.message.edit_text(
                    "🤖 <b>Анализирую объявления...</b>\n\n"
                    f"Объявление {number}/"
                    f"{len(candidates)}",
                )

                await ai.analyze(
                    listing,
                    filters,
                )

                results.append(
                    listing
                )

            except Exception as error:

                print(
                    "AI listing error:",
                    error,
                )

        results = sort_by_ai(
            results
        )

        state["results"] = results

        await save_search(
            callback.from_user.id,
            filters,
            results,
        )

        await callback.message.edit_text(
            build_results(
                results
            ),
            reply_markup=results_keyboard(
                results
            ),
        )

    except Exception as error:

        print(
            "SEARCH ERROR:",
            error,
        )

        await callback.message.edit_text(
            "❌ <b>Ошибка поиска</b>\n\n"
            f"<code>{esc(str(error)[:800])}</code>\n\n"
            "Проверь настройки источника "
            "объявлений.",
            reply_markup=main_keyboard(),
        )


# ============================================================
# SAVE SEARCH
# ============================================================

async def save_search(
    user_id: int,
    filters: SearchFilters,
    results: list[Listing],
):

    await storage.set_search(
        user_id,
        {
            "filters":
                filters.to_dict(),

            "results": [
                {
                    "id":
                        item.id,

                    "title":
                        item.title,

                    "price":
                        item.price,

                    "url":
                        item.url,

                    "score":
                        (
                            item.ai_analysis.score
                            if item.ai_analysis
                            else 0
                        ),
                }
                for item in results
            ],
        },
    )


# ============================================================
# RESULTS KEYBOARD
# ============================================================

def results_keyboard(
    listings: list[Listing],
):

    rows = []

    for index, listing in enumerate(
        listings
    ):

        analysis = (
            listing.ai_analysis
        )

        score = (
            analysis.score
            if analysis
            else 0
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{index + 1}️⃣ "
                        f"{score}/100 • "
                        f"{money(listing.price)}"
                    ),
                    callback_data=(
                        f"listing:{index}"
                    ),
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

    if not listings:

        return (
            "😕 <b>Ничего не найдено.</b>"
        )

    lines = [
        "🏆 <b>ТОП ВАРИАНТОВ</b>",
        "",
        f"Найдено: <b>{len(listings)}</b>",
        "",
    ]

    current_tier = None

    for index, listing in enumerate(
        listings,
        start=1,
    ):

        analysis = (
            listing.ai_analysis
        )

        if not analysis:
            continue

        if analysis.tier != current_tier:

            current_tier = analysis.tier

            lines.append(
                f"{tier_emoji(current_tier)} "
                f"<b>{current_tier} TIER</b>"
            )

            lines.append("")

        battery = (
            f"{listing.battery_percent}%"
            if listing.battery_percent
            else "—"
        )

        lines.extend(
            [
                f"<b>{index}. "
                f"{esc(listing.title)}</b>",

                f"💰 {money(listing.price)}",

                f"🔋 {battery}",

                f"🤖 "
                f"<b>{analysis.score}/100</b>",

                verdict(
                    analysis.verdict
                ),

                "",
            ]
        )

    lines.append(
        "Нажми на вариант, чтобы "
        "посмотреть подробности."
    )

    return "\n".join(lines)


# ============================================================
# LISTING DETAILS
# ============================================================

@dp.callback_query(
    F.data.startswith("listing:")
)
async def listing_details(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    try:

        index = int(
            callback.data.split(":")[1]
        )

    except (
        ValueError,
        IndexError,
    ):

        await callback.answer(
            "Ошибка."
        )

        return

    results = state.get(
        "results",
        [],
    )

    if index < 0 or index >= len(
        results
    ):

        await callback.answer(
            "Объявление уже недоступно."
        )

        return

    listing = results[index]

    analysis = (
        listing.ai_analysis
    )

    # ФОТО
    if listing.photos:

        photos = [
            InputMediaPhoto(
                media=url
            )
            for url in listing.photos[:10]
            if isinstance(
                url,
                str,
            )
            and url.startswith(
                "http"
            )
        ]

        if photos:

            try:

                await callback.message.answer_media_group(
                    photos
                )

            except Exception as error:

                print(
                    "PHOTO ERROR:",
                    error,
                )

    text = build_listing_details(
        listing
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Открыть объявление",
                    url=listing.url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ В избранное",
                    callback_data=(
                        f"favorite:{index}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к результатам",
                    callback_data="results:back",
                )
            ],
        ]
    )

    await callback.message.answer(
        text,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )

    await callback.answer()


# ============================================================
# LISTING DETAILS TEXT
# ============================================================

def build_listing_details(
    listing: Listing,
) -> str:

    analysis = (
        listing.ai_analysis
        or None
    )

    lines = [
        f"📱 <b>{esc(listing.title)}</b>",
        "",
    ]

    if analysis:

        lines.extend(
            [
                f"🤖 <b>AI SCORE: "
                f"{analysis.score}/100</b>",

                verdict(
                    analysis.verdict
                ),

                "",
                "━━━━━━━━━━━━",
                "",
            ]
        )

    lines.extend(
        [
            f"💰 <b>{money(listing.price)}</b>",
            f"📱 Модель: {esc(listing.model)}",
        ]
    )

    if listing.storage_gb:

        lines.append(
            f"💾 Память: "
            f"{listing.storage_gb} GB"
        )

    if listing.battery_percent:

        lines.append(
            f"🔋 АКБ: "
            f"{listing.battery_percent}%"
        )

    if listing.condition:

        lines.append(
            f"📱 Состояние: "
            f"{esc(listing.condition)}"
        )

    if listing.color:

        lines.append(
            f"🎨 Цвет: "
            f"{esc(listing.color)}"
        )

    if listing.city:

        lines.append(
            f"🏙 Город: "
            f"{esc(listing.city)}"
        )

    if listing.seller_name:

        lines.append(
            f"👤 Продавец: "
            f"{esc(listing.seller_name)}"
        )

    if listing.seller_rating:

        lines.append(
            f"⭐ Рейтинг: "
            f"{listing.seller_rating}"
        )

    if listing.repair_info:

        lines.extend(
            [
                "",
                "🔧 <b>РЕМОНТ</b>",
                esc(
                    listing.repair_info
                ),
            ]
        )

    if listing.screen_info:

        lines.extend(
            [
                "",
                "📺 <b>ЭКРАН</b>",
                esc(
                    listing.screen_info
                ),
            ]
        )

    if listing.accessories:

        lines.extend(
            [
                "",
                "📦 <b>КОМПЛЕКТ</b>",
                esc(
                    ", ".join(
                        listing.accessories
                    )
                ),
            ]
        )

    if analysis:

        lines.extend(
            [
                "",
                "━━━━━━━━━━━━",
                "",
                "🤖 <b>АНАЛИЗ ИИ</b>",
                "",
                esc(
                    analysis.summary
                ),
            ]
        )

        if analysis.advantages:

            lines.extend(
                [
                    "",
                    "✅ <b>ПЛЮСЫ</b>",
                ]
            )

            for item in analysis.advantages:

                lines.append(
                    f"• {esc(item)}"
                )

        if analysis.risks:

            lines.extend(
                [
                    "",
                    "⚠️ <b>РИСКИ</b>",
                ]
            )

            for item in analysis.risks:

                lines.append(
                    f"• {esc(item)}"
                )

        if analysis.checks:

            lines.extend(
                [
                    "",
                    "🔍 <b>ПРОВЕРИТЬ</b>",
                ]
            )

            for item in analysis.checks:

                lines.append(
                    f"• {esc(item)}"
                )

        lines.extend(
            [
                "",
                "📊 <b>ОЦЕНКИ</b>",
                "",
                f"Цена: "
                f"{analysis.price_score}/10",

                f"Состояние: "
                f"{analysis.condition_score}/10",

                f"АКБ: "
                f"{analysis.battery_score}/10",

                f"Ремонт: "
                f"{analysis.repair_score}/10",

                f"Продавец: "
                f"{analysis.seller_score}/10",
            ]
        )

    if listing.description:

        description = (
            listing.description
        )

        if len(description) > 1800:

            description = (
                description[:1800]
                + "..."
            )

        lines.extend(
            [
                "",
                "📝 <b>ОПИСАНИЕ ОБЪЯВЛЕНИЯ</b>",
                "",
                esc(description),
            ]
        )

    return "\n".join(lines)


# ============================================================
# BACK RESULTS
# ============================================================

@dp.callback_query(
    F.data == "results:back"
)
async def back_results(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    results = state.get(
        "results",
        [],
    )

    await callback.message.edit_text(
        build_results(
            results
        ),
        reply_markup=results_keyboard(
            results
        ),
    )

    await callback.answer()


# ============================================================
# FAVORITE
# ============================================================

@dp.callback_query(
    F.data.startswith("favorite:")
)
async def favorite(
    callback: CallbackQuery,
):

    state = get_state(
        callback.from_user.id
    )

    try:

        index = int(
            callback.data.split(":")[1]
        )

    except (
        ValueError,
        IndexError,
    ):

        await callback.answer(
            "Ошибка."
        )

        return

    results = state.get(
        "results",
        [],
    )

    if index < 0 or index >= len(
        results
    ):

        await callback.answer(
            "Объявление не найдено."
        )

        return

    listing = results[index]

    await storage.add_favorite(
        callback.from_user.id,
        listing.to_dict(
            include_raw=False
        ),
    )

    await callback.answer(
        "⭐ Добавлено в избранное",
        show_alert=True,
    )


# ============================================================
# FAVORITES
# ============================================================

@dp.callback_query(
    F.data == "favorites"
)
async def favorites(
    callback: CallbackQuery,
):

    items = await storage.get_favorites(
        callback.from_user.id
    )

    if not items:

        await callback.message.edit_text(
            "⭐ <b>Избранное пусто</b>",
            reply_markup=main_keyboard(),
        )

        await callback.answer()

        return

    lines = [
        "⭐ <b>ИЗБРАННОЕ</b>",
        "",
    ]

    for index, item in enumerate(
        items,
        start=1,
    ):

        score = item.get(
            "ai_analysis",
            {},
        )

        if isinstance(
            score,
            dict,
        ):
            score = score.get(
                "score",
                0,
            )
        else:
            score = 0

        title = esc(
            item.get(
                "title",
                "iPhone",
            )
        )

        price = money(
            item.get(
                "price",
                0,
            )
        )

        url = item.get(
            "url",
            "",
        )

        lines.append(
            f"{index}. "
            f"<a href=\"{esc(url)}\">"
            f"{title}"
            f"</a>\n"
            f"💰 {price} "
            f"🤖 {score}/100\n"
        )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
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

    data = await storage.get_search(
        callback.from_user.id
    )

    if not data:

        await callback.message.edit_text(
            "💾 <b>Поисков пока нет.</b>\n\n"
            "Создай новый поиск.",
            reply_markup=main_keyboard(),
        )

        await callback.answer()

        return

    filters = SearchFilters.from_dict(
        data.get(
            "filters",
            {},
        )
    )

    models = ", ".join(
        filters.models
    )

    await callback.message.edit_text(
        "💾 <b>ПОСЛЕДНИЙ ПОИСК</b>\n\n"
        f"📱 {esc(models)}\n"
        f"💰 до {money(filters.max_price)}\n"
        f"🔋 "
        f"{filters.min_battery or 'любая'}\n"
        f"🏙 "
        f"{esc(filters.city or 'любой')}\n\n"
        "Нажми «Новый поиск», "
        "чтобы изменить параметры.",
        reply_markup=main_keyboard(),
    )

    await callback.answer()


# ============================================================
# ERROR HANDLER
# ============================================================

@dp.errors()
async def global_error(
    event,
):

    print(
        "GLOBAL ERROR:",
        event.exception,
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "================================"
    )

    print(
        "iPhone Finder started"
    )

    print(
        "Groq:",
        "ON"
        if os.getenv("GROQ_API_KEY")
        else "OFF",
    )

    print(
        "Gemini:",
        "ON"
        if os.getenv("GEMINI_API_KEY")
        else "OFF",
    )

    print(
        "Avito API:",
        "ON"
        if os.getenv("AVITO_API_URL")
        else "OFF",
    )

    print(
        "================================"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
