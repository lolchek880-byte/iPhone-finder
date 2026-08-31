import asyncio
import os
from dataclasses import asdict

from aiogram import (
    Bot,
    Dispatcher,
    F,
)
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from dotenv import load_dotenv

from ai import AIAnalyzer
from avito import APIAvitoProvider
from models import SearchFilters, Listing
from ranking import prepare_candidates
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
    token=BOT_TOKEN
)

dp = Dispatcher()

storage = JSONStorage()

ai = AIAnalyzer()

avito = APIAvitoProvider()


# ============================================================
# TEMP USER SEARCH STATE
# ============================================================

user_states: dict[int, dict] = {}


# ============================================================
# KEYBOARDS
# ============================================================

def main_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🔎 Новый поиск",
                    callback_data="new_search",
                )
            ],

            [
                InlineKeyboardButton(
                    text="💾 Мой поиск",
                    callback_data="my_search",
                ),

                InlineKeyboardButton(
                    text="⭐ Избранное",
                    callback_data="favorites",
                ),
            ],

            [
                InlineKeyboardButton(
                    text="⚙️ Фильтры",
                    callback_data="filters",
                )
            ],

        ]
    )


def models_keyboard():

    models = [
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
        "iPhone 16 Pro",
        "iPhone 16 Pro Max",
    ]

    rows = []

    for i in range(
        0,
        len(models),
        2,
    ):

        row = []

        for model in models[i:i+2]:

            row.append(
                InlineKeyboardButton(
                    text=model,
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
                callback_data="model_done",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def budget_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="до 30 000 ₽",
                    callback_data="budget:30000",
                ),

                InlineKeyboardButton(
                    text="до 40 000 ₽",
                    callback_data="budget:40000",
                ),
            ],

            [
                InlineKeyboardButton(
                    text="до 50 000 ₽",
                    callback_data="budget:50000",
                ),

                InlineKeyboardButton(
                    text="до 60 000 ₽",
                    callback_data="budget:60000",
                ),
            ],

            [
                InlineKeyboardButton(
                    text="до 70 000 ₽",
                    callback_data="budget:70000",
                ),

                InlineKeyboardButton(
                    text="до 100 000 ₽",
                    callback_data="budget:100000",
                ),
            ],

            [
                InlineKeyboardButton(
                    text="💰 Ввести самому",
                    callback_data="budget_custom",
                )
            ],

        ]
    )


def filters_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="💾 Память",
                    callback_data="filter_storage",
                )
            ],

            [
                InlineKeyboardButton(
                    text="🔋 Аккумулятор",
                    callback_data="filter_battery",
                )
            ],

            [
                InlineKeyboardButton(
                    text="🔧 Ремонт",
                    callback_data="filter_repair",
                )
            ],

            [
                InlineKeyboardButton(
                    text="📱 Состояние",
                    callback_data="filter_condition",
                )
            ],

            [
                InlineKeyboardButton(
                    text="🏙 Город",
                    callback_data="filter_city",
                )
            ],

            [
                InlineKeyboardButton(
                    text="🔎 Начать поиск",
                    callback_data="start_search",
                )
            ],

        ]
    )


def results_keyboard(
    listings: list[Listing],
):

    rows = []

    for index, listing in enumerate(
        listings,
        start=1,
    ):

        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{index}️⃣ Подробнее",
                    callback_data=(
                        f"listing:{index-1}"
                    ),
                )
            ]
        )


    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Новый поиск",
                callback_data="new_search",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
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

    await storage.get_user(
        message.from_user.id
    )


    await message.answer(
        "📱 <b>iPhone Finder</b>\n\n"
        "Найду лучшие варианты iPhone "
        "по твоему бюджету и параметрам.\n\n"
        "ИИ сравнит объявления, "
        "оценит риски и составит "
        "тир-лист.",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


# ============================================================
# NEW SEARCH
# ============================================================

@dp.callback_query(
    F.data == "new_search"
)
async def new_search(
    callback: CallbackQuery,
):

    user_states[
        callback.from_user.id
    ] = {
        "filters":
            SearchFilters()
    }


    await callback.message.edit_text(
        "📱 <b>Выбери модель</b>\n\n"
        "Можно выбрать несколько.",
        reply_markup=models_keyboard(),
        parse_mode="HTML",
    )


    await callback.answer()


# ============================================================
# MODEL
# ============================================================

@dp.callback_query(
    F.data.startswith("model:")
)
async def select_model(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        await callback.answer(
            "Начни новый поиск"
        )
        return


    model = callback.data[
        len("model:")
    ]


    filters: SearchFilters = (
        state["filters"]
    )


    if model not in filters.models:

        filters.models.append(
            model
        )

        await callback.answer(
            f"Добавлено: {model}"
        )

    else:

        filters.models.remove(
            model
        )

        await callback.answer(
            f"Убрано: {model}"
        )


# ============================================================
# MODEL DONE
# ============================================================

@dp.callback_query(
    F.data == "model_done"
)
async def model_done(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        return


    filters: SearchFilters = (
        state["filters"]
    )


    if not filters.models:

        await callback.answer(
            "Выбери хотя бы одну модель",
            show_alert=True,
        )

        return


    await callback.message.edit_text(
        "💰 <b>Выбери максимальный бюджет</b>",
        reply_markup=budget_keyboard(),
        parse_mode="HTML",
    )


    await callback.answer()


# ============================================================
# BUDGET
# ============================================================

@dp.callback_query(
    F.data.startswith("budget:")
)
async def select_budget(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        return


    amount = int(
        callback.data.split(":")[1]
    )


    filters: SearchFilters = (
        state["filters"]
    )

    filters.max_price = amount


    await callback.message.edit_text(
        f"💰 Бюджет: <b>{amount:,} ₽</b>\n\n"
        "Теперь можно настроить дополнительные фильтры.",
        reply_markup=filters_keyboard(),
        parse_mode="HTML",
    )


    await callback.answer()


# ============================================================
# CUSTOM BUDGET
# ============================================================

@dp.callback_query(
    F.data == "budget_custom"
)
async def custom_budget(
    callback: CallbackQuery,
):

    user_states[
        callback.from_user.id
    ]["awaiting_budget"] = True


    await callback.message.edit_text(
        "💰 Напиши максимальный бюджет одним числом.\n\n"
        "Например:\n"
        "<code>65000</code>",
        parse_mode="HTML",
    )


    await callback.answer()


@dp.message()
async def text_handler(
    message: Message,
):

    state = user_states.get(
        message.from_user.id
    )


    if not state:
        return


    if state.get(
        "awaiting_budget"
    ):

        try:

            amount = int(
                message.text
                .replace(" ", "")
                .replace("₽", "")
            )

            state[
                "filters"
            ].max_price = amount

            state[
                "awaiting_budget"
            ] = False

            await message.answer(
                f"💰 Бюджет установлен: "
                f"<b>{amount:,} ₽</b>",
                reply_markup=filters_keyboard(),
                parse_mode="HTML",
            )

        except ValueError:

            await message.answer(
                "Напиши только число.\n"
                "Например: <code>65000</code>",
                parse_mode="HTML",
            )


# ============================================================
# FILTER STORAGE
# ============================================================

@dp.callback_query(
    F.data == "filter_storage"
)
async def filter_storage(
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
                    text="⬅️ Назад",
                    callback_data="filters",
                )
            ],

        ]
    )


    await callback.message.edit_text(
        "💾 <b>Память</b>\n\n"
        "Можно выбрать несколько.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("storage:")
)
async def select_storage(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        return


    value = int(
        callback.data.split(":")[1]
    )


    filters = state["filters"]


    if value in filters.storage:

        filters.storage.remove(
            value
        )

        await callback.answer(
            "Убрано"
        )

    else:

        filters.storage.append(
            value
        )

        await callback.answer(
            "Добавлено"
        )


# ============================================================
# BATTERY
# ============================================================

@dp.callback_query(
    F.data == "filter_battery"
)
async def filter_battery(
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
                    text="Неважно",
                    callback_data="battery:0",
                )
            ],

        ]
    )


    await callback.message.edit_text(
        "🔋 <b>Минимальный аккумулятор</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("battery:")
)
async def select_battery(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        return


    value = int(
        callback.data.split(":")[1]
    )


    state[
        "filters"
    ].min_battery = (
        value
        if value > 0
        else None
    )


    await callback.message.edit_text(
        "⚙️ <b>Фильтры</b>",
        reply_markup=filters_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# REPAIR
# ============================================================

@dp.callback_query(
    F.data == "filter_repair"
)
async def filter_repair(
    callback: CallbackQuery,
):

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="Без ремонта",
                    callback_data="repair:none",
                )
            ],

            [
                InlineKeyboardButton(
                    text="Можно с ремонтом",
                    callback_data="repair:any",
                )
            ],

        ]
    )


    await callback.message.edit_text(
        "🔧 <b>Ремонт</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("repair:")
)
async def select_repair(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        return


    state[
        "filters"
    ].repair_policy = (
        callback.data.split(":")[1]
    )


    await callback.message.edit_text(
        "⚙️ <b>Фильтры</b>",
        reply_markup=filters_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# CONDITION
# ============================================================

@dp.callback_query(
    F.data == "filter_condition"
)
async def filter_condition(
    callback: CallbackQuery,
):

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="Как новый",
                    callback_data="condition:new",
                )
            ],

            [
                InlineKeyboardButton(
                    text="Отличное",
                    callback_data="condition:excellent",
                )
            ],

            [
                InlineKeyboardButton(
                    text="Хорошее",
                    callback_data="condition:good",
                )
            ],

            [
                InlineKeyboardButton(
                    text="Любое",
                    callback_data="condition:any",
                )
            ],

        ]
    )


    await callback.message.edit_text(
        "📱 <b>Состояние</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )

    await callback.answer()


@dp.callback_query(
    F.data.startswith("condition:")
)
async def select_condition(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        return


    value = callback.data.split(":")[1]


    if value == "any":

        state[
            "filters"
        ].conditions = []

    else:

        state[
            "filters"
        ].conditions = [
            value
        ]


    await callback.message.edit_text(
        "⚙️ <b>Фильтры</b>",
        reply_markup=filters_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# CITY
# ============================================================

@dp.callback_query(
    F.data == "filter_city"
)
async def filter_city(
    callback: CallbackQuery,
):

    user_states[
        callback.from_user.id
    ]["awaiting_city"] = True


    await callback.message.edit_text(
        "🏙 Напиши город.\n\n"
        "Например: <code>Москва</code>",
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# FILTER MENU
# ============================================================

@dp.callback_query(
    F.data == "filters"
)
async def filters(
    callback: CallbackQuery,
):

    await callback.message.edit_text(
        "⚙️ <b>Фильтры</b>\n\n"
        "Настрой нужные параметры.",
        reply_markup=filters_keyboard(),
        parse_mode="HTML",
    )

    await callback.answer()


# ============================================================
# START SEARCH
# ============================================================

@dp.callback_query(
    F.data == "start_search"
)
async def start_search(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )

    if not state:
        await callback.answer(
            "Начни новый поиск"
        )
        return


    filters: SearchFilters = (
        state["filters"]
    )


    await callback.message.edit_text(
        "🔎 <b>Ищу объявления...</b>\n\n"
        "Это может занять некоторое время.",
        parse_mode="HTML",
    )

    await callback.answer()


    try:

        listings = await avito.search(
            filters
        )


        candidates =
            prepare_candidates(
                listings,
                filters,
            )


        candidates = candidates[
            :50
        ]


        if not candidates:

            await callback.message.edit_text(
                "😕 По заданным параметрам "
                "ничего не найдено.\n\n"
                "Попробуй увеличить бюджет "
                "или ослабить фильтры."
            )

            return


        await callback.message.edit_text(
            "🤖 <b>ИИ анализирует "
            f"{min(len(candidates), MAX_RESULTS)} "
            "лучших вариантов...</b>",
            parse_mode="HTML",
        )


        analyzed = []


        for listing in candidates[
            :MAX_RESULTS
        ]:

            analysis = await ai.analyze(
                listing,
                filters,
            )

            listing.raw[
                "ai_analysis"
            ] = analysis

            analyzed.append(
                listing
            )


        analyzed.sort(
            key=lambda item:
                int(
                    item.raw
                    .get(
                        "ai_analysis",
                        {}
                    )
                    .get(
                        "score",
                        0,
                    )
                ),
            reverse=True,
        )


        state[
            "results"
        ] = analyzed


        await storage.set_search(
            callback.from_user.id,
            {
                "filters":
                    asdict(filters),

                "results": [
                    {
                        "id":
                            x.id,

                        "title":
                            x.title,

                        "price":
                            x.price,

                        "url":
                            x.url,

                        "score":
                            x.raw
                            .get(
                                "ai_analysis",
                                {}
                            )
                            .get(
                                "score",
                                0,
                            ),
                    }
                    for x in analyzed
                ],
            },
        )


        text = build_results_text(
            analyzed
        )


        await callback.message.edit_text(
            text,
            reply_markup=
                results_keyboard(
                    analyzed
                ),
            parse_mode="HTML",
        )


    except Exception as error:

        print(
            "Search error:",
            error,
        )

        await callback.message.edit_text(
            "❌ Произошла ошибка при поиске.\n\n"
            f"<code>{str(error)[:500]}</code>",
            parse_mode="HTML",
        )


# ============================================================
# RESULTS
# ============================================================

def tier(score: int) -> str:

    if score >= 90:
        return "S"

    if score >= 80:
        return "A"

    if score >= 70:
        return "B"

    if score >= 60:
        return "C"

    return "D"


def verdict_text(
    verdict: str,
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
        verdict,
        "🟡 НУЖНА ПРОВЕРКА",
    )


def build_results_text(
    listings: list[Listing],
) -> str:

    lines = [
        "🔎 <b>РЕЗУЛЬТАТЫ ПОИСКА</b>",
        "",
        f"Найдено: {len(listings)}",
        "",
    ]


    current_tier = None


    for index, listing in enumerate(
        listings,
        start=1,
    ):

        analysis = listing.raw.get(
            "ai_analysis",
            {},
        )


        score = int(
            analysis.get(
                "score",
                0,
            )
        )


        current = tier(score)


        if current != current_tier:

            current_tier = current

            lines.append(
                f"<b>━━ {current} TIER ━━</b>"
            )


        lines.extend(
            [
                "",
                f"<b>{index}. "
                f"{escape(listing.title)}</b>",

                f"💰 {listing.price:,} ₽",

                (
                    f"🔋 "
                    f"{listing.battery_percent}%"
                    if listing.battery_percent
                    else
                    "🔋 АКБ: не указана"
                ),

                f"🤖 <b>{score}/100</b>",

                verdict_text(
                    analysis.get(
                        "verdict",
                        "CAUTION",
                    )
                ),
            ]
        )


    lines.extend(
        [
            "",
            "Нажми номер объявления "
            "для подробностей.",
        ]
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

    state = user_states.get(
        callback.from_user.id
    )


    if not state:

        await callback.answer(
            "Поиск устарел"
        )

        return


    index = int(
        callback.data.split(":")[1]
    )


    results = state.get(
        "results",
        []
    )


    if index >= len(results):

        await callback.answer(
            "Объявление не найдено"
        )

        return


    listing = results[index]


    analysis = listing.raw.get(
        "ai_analysis",
        {},
    )


    # Фото

    photos = listing.photos[:10]


    if photos:

        media_sent = False

        try:

            from aiogram.types import (
                InputMediaPhoto
            )

            media = [
                InputMediaPhoto(
                    media=url
                )
                for url in photos
            ]

            await callback.message.answer_media_group(
                media
            )

            media_sent = True

        except Exception as error:

            print(
                "Photo send error:",
                error,
            )


    text = build_listing_text(
        listing,
        analysis,
    )


    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🔗 Открыть Avito",
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
                    text="⬅️ К результатам",
                    callback_data="back_results",
                )
            ],

        ]
    )


    await callback.message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


    await callback.answer()


# ============================================================
# DETAILS TEXT
# ============================================================

def build_listing_text(
    listing: Listing,
    analysis: dict,
) -> str:

    score = int(
        analysis.get(
            "score",
            0,
        )
    )


    lines = [

        f"📱 <b>{escape(listing.title)}</b>",

        "",

        f"🤖 <b>AI SCORE: {score}/100</b>",

        verdict_text(
            analysis.get(
                "verdict",
                "CAUTION",
            )
        ),

        "",

        "━━━━━━━━━━━━",

        f"💰 Цена: <b>{listing.price:,} ₽</b>",

        f"📱 Модель: "
        f"{escape(listing.model)}",

    ]


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


    if listing.color:

        lines.append(
            f"🎨 Цвет: "
            f"{escape(listing.color)}"
        )


    if listing.condition:

        lines.append(
            f"📱 Состояние: "
            f"{escape(listing.condition)}"
        )


    lines.extend(
        [
            "",
            "━━━━━━━━━━━━",
            "",
            "🤖 <b>ОЦЕНКА ИИ</b>",
            "",
            escape(
                analysis.get(
                    "summary",
                    "",
                )
            ),
        ]
    )


    advantages = analysis.get(
        "advantages",
        [],
    )


    if advantages:

        lines.extend(
            [
                "",
                "✅ <b>ПЛЮСЫ</b>",
            ]
        )

        for item in advantages[:8]:

            lines.append(
                f"• {escape(item)}"
            )


    risks = analysis.get(
        "risks",
        [],
    )


    if risks:

        lines.extend(
            [
                "",
                "⚠️ <b>РИСКИ</b>",
            ]
        )

        for item in risks[:8]:

            lines.append(
                f"• {escape(item)}"
            )


    checks = analysis.get(
        "checks",
        [],
    )


    if checks:

        lines.extend(
            [
                "",
                "🔍 <b>ПРОВЕРИТЬ ПЕРЕД ПОКУПКОЙ</b>",
            ]
        )

        for item in checks[:8]:

            lines.append(
                f"• {escape(item)}"
            )


    if listing.repair_info:

        lines.extend(
            [
                "",
                "🔧 <b>РЕМОНТ</b>",
                escape(
                    listing.repair_info
                ),
            ]
        )


    if listing.screen_info:

        lines.extend(
            [
                "",
                "📺 <b>ЭКРАН</b>",
                escape(
                    listing.screen_info
                ),
            ]
        )


    if listing.description:

        description = (
            listing.description
            .strip()
        )


        if len(description) > 1200:

            description = (
                description[:1200]
                + "..."
            )


        lines.extend(
            [
                "",
                "📝 <b>ОПИСАНИЕ AVITO</b>",
                escape(
                    description
                ),
            ]
        )


    return "\n".join(lines)


# ============================================================
# FAVORITES
# ============================================================

@dp.callback_query(
    F.data.startswith("favorite:")
)
async def favorite(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )


    if not state:

        await callback.answer(
            "Поиск устарел"
        )

        return


    index = int(
        callback.data.split(":")[1]
    )


    results = state.get(
        "results",
        []
    )


    if index >= len(results):

        await callback.answer(
            "Не найдено"
        )

        return


    listing = results[index]


    await storage.add_favorite(
        callback.from_user.id,
        {
            "id":
                listing.id,

            "title":
                listing.title,

            "price":
                listing.price,

            "url":
                listing.url,

            "score":
                listing.raw
                .get(
                    "ai_analysis",
                    {}
                )
                .get(
                    "score",
                    0,
                ),
        },
    )


    await callback.answer(
        "⭐ Добавлено в избранное",
        show_alert=True,
    )


# ============================================================
# BACK RESULTS
# ============================================================

@dp.callback_query(
    F.data == "back_results"
)
async def back_results(
    callback: CallbackQuery,
):

    state = user_states.get(
        callback.from_user.id
    )


    if not state:

        await callback.answer()
        return


    results = state.get(
        "results",
        []
    )


    await callback.message.answer(
        build_results_text(
            results
        ),
        reply_markup=
            results_keyboard(
                results
            ),
        parse_mode="HTML",
    )


    await callback.answer()


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
            parse_mode="HTML",
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

        lines.append(
            f"{index}. "
            f"<a href=\"{item['url']}\">"
            f"{escape(item['title'])}"
            f"</a>\n"
            f"💰 {item['price']:,} ₽"
            f" | 🤖 {item['score']}/100\n"
        )


    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


    await callback.answer()


# ============================================================
# MY SEARCH
# ============================================================

@dp.callback_query(
    F.data == "my_search"
)
async def my_search(
    callback: CallbackQuery,
):

    search = await storage.get_search(
        callback.from_user.id
    )


    if not search:

        await callback.message.edit_text(
            "💾 <b>Поисков пока нет.</b>\n\n"
            "Нажми «Новый поиск».",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )

        await callback.answer()

        return


    filters = search.get(
        "filters",
        {}
    )


    models = ", ".join(
        filters.get(
            "models",
            []
        )
    )


    budget = filters.get(
        "max_price"
    )


    await callback.message.edit_text(
        "💾 <b>Последний поиск</b>\n\n"
        f"📱 {escape(models)}\n"
        f"💰 до {budget:,} ₽\n\n"
        "Нажми «Новый поиск», "
        "если хочешь изменить параметры.",
        reply_markup=main_keyboard(),
        parse_mode="HTML",
    )


    await callback.answer()


# ============================================================
# ESCAPE
# ============================================================

def escape(
    text,
) -> str:

    if text is None:
        return ""

    text = str(text)

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ============================================================
# RUN
# ============================================================

async def main():

    print(
        "iPhone Finder started"
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
