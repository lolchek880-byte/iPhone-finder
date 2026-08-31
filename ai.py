import json
import os
import re
from typing import Any

from openai import AsyncOpenAI
from google import genai

from models import Listing, SearchFilters


class AIAnalyzer:

    def __init__(self):

        self.groq = AsyncOpenAI(
            api_key=os.getenv(
                "GROQ_API_KEY"
            ),
            base_url=(
                "https://api.groq.com/openai/v1"
            ),
        )

        self.gemini = genai.Client(
            api_key=os.getenv(
                "GEMINI_API_KEY"
            )
        )

        self.groq_model = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-120b",
        )

        self.gemini_model = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.7-flash",
        )

    @staticmethod
    def _prompt(
        listing: Listing,
        filters: SearchFilters,
    ) -> str:

        return f"""
Ты — эксперт по покупке б/у iPhone.

Твоя задача — оценить объявление максимально
консервативно.

НИКОГДА не выдумывай характеристики,
которых нет в объявлении.

Если продавец не указал ремонт —
пиши "не указано", а не "ремонта нет".

Если фотография позволяет только предположить
дефект — обозначай это как предположение.

Параметры пользователя:

Модели:
{filters.models}

Бюджет:
{filters.min_price} - {filters.max_price}

Память:
{filters.storage}

Минимальная батарея:
{filters.min_battery}

Состояние:
{filters.conditions}

Ремонт:
{filters.repair_policy}

Экран:
{filters.screen_policy}

Город:
{filters.city}

ОБЪЯВЛЕНИЕ:

Название:
{listing.title}

Модель:
{listing.model}

Цена:
{listing.price}

Память:
{listing.storage_gb}

Аккумулятор:
{listing.battery_percent}

Состояние:
{listing.condition}

Цвет:
{listing.color}

Ремонт:
{listing.repair_info}

Экран:
{listing.screen_info}

Продавец:
{listing.seller_name}

Рейтинг продавца:
{listing.seller_rating}

Город:
{listing.city}

Комплект:
{listing.accessories}

Описание:
{listing.description}

Верни ТОЛЬКО JSON:

{{
  "score": 0,
  "tier": "S",
  "verdict": "BUY",
  "summary": "",
  "advantages": [],
  "risks": [],
  "checks": [],
  "price_score": 0,
  "condition_score": 0,
  "battery_score": 0,
  "repair_score": 0,
  "seller_score": 0
}}

score:
0-100.

tier:
S, A, B, C или D.

verdict:
BUY,
GOOD,
CAUTION,
AVOID.

S:
90-100

A:
80-89

B:
70-79

C:
60-69

D:
0-59
"""

    @staticmethod
    def _extract_json(text: str) -> dict:

        text = text.strip()

        if text.startswith("```"):
            text = re.sub(
                r"^```(?:json)?",
                "",
                text,
                flags=re.I,
            )

            text = re.sub(
                r"```$",
                "",
                text,
            )

        match = re.search(
            r"\{.*\}",
            text,
            flags=re.S,
        )

        if not match:
            raise ValueError(
                "AI не вернул JSON"
            )

        return json.loads(
            match.group(0)
        )

    async def analyze_with_groq(
        self,
        listing: Listing,
        filters: SearchFilters,
    ) -> dict:

        response = await self.groq.chat.completions.create(
            model=self.groq_model,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты эксперт по "
                        "рынку б/у iPhone."
                    ),
                },
                {
                    "role": "user",
                    "content": self._prompt(
                        listing,
                        filters,
                    ),
                },
            ],

            temperature=0.15,

            response_format={
                "type": "json_object"
            },
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        return self._extract_json(
            content
        )

    async def analyze_with_gemini(
        self,
        listing: Listing,
        filters: SearchFilters,
    ) -> dict:

        response = (
            self.gemini.models.generate_content(
                model=self.gemini_model,

                contents=self._prompt(
                    listing,
                    filters,
                ),
            )
        )

        return self._extract_json(
            response.text
        )

    async def analyze(
        self,
        listing: Listing,
        filters: SearchFilters,
    ) -> dict:

        try:

            return await self.analyze_with_groq(
                listing,
                filters,
            )

        except Exception as groq_error:

            print(
                "Groq error:",
                groq_error,
            )

            try:

                return await self.analyze_with_gemini(
                    listing,
                    filters,
                )

            except Exception as gemini_error:

                print(
                    "Gemini error:",
                    gemini_error,
                )

                return {
                    "score": 0,
                    "tier": "D",
                    "verdict": "CAUTION",
                    "summary": (
                        "ИИ-анализ временно "
                        "недоступен."
                    ),
                    "advantages": [],
                    "risks": [
                        "Не удалось выполнить AI-анализ."
                    ],
                    "checks": [],
                }
