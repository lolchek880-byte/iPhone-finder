import json
import os
import re
from typing import Any

from google import genai
from openai import AsyncOpenAI

from models import AIAnalysis, Listing, SearchFilters


class AIAnalyzer:

    def __init__(self):

        groq_key = os.getenv(
            "GROQ_API_KEY",
            "",
        )

        gemini_key = os.getenv(
            "GEMINI_API_KEY",
            "",
        )

        self.groq = None

        if groq_key:

            self.groq = AsyncOpenAI(
                api_key=groq_key,
                base_url=(
                    "https://api.groq.com/openai/v1"
                ),
            )

        self.gemini = None

        if gemini_key:

            self.gemini = genai.Client(
                api_key=gemini_key
            )

        self.groq_model = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-120b",
        )

        self.gemini_model = os.getenv(
            "GEMINI_MODEL",
            "gemini-2.5-flash",
        )

    @staticmethod
    def build_prompt(
        listing: Listing,
        filters: SearchFilters,
    ) -> str:

        return f"""
Ты — эксперт по покупке подержанных iPhone.

Проанализируй конкретное объявление.

КРИТИЧЕСКИЕ ПРАВИЛА:

1. Никогда не выдумывай информацию.
2. Если характеристика отсутствует — напиши
   "не указано".
3. Не утверждай, что телефон оригинальный,
   если это не подтверждается данными.
4. Не утверждай, что ремонта не было,
   если продавец этого не указал.
5. Фотографии могут использоваться только
   для визуальной оценки.
6. Если дефект нельзя уверенно определить,
   обозначь его как возможный риск.
7. Цена должна оцениваться относительно
   параметров самого объявления.
8. Не выдавай финансовую гарантию.
9. Итог "ПОКУПАТЬ" означает только
   "выглядит выгодно при проверке",
   а не гарантию исправности.

ПАРАМЕТРЫ ПОКУПАТЕЛЯ:

Модели:
{filters.models}

Минимальная цена:
{filters.min_price}

Максимальная цена:
{filters.max_price}

Память:
{filters.storage}

Минимальный аккумулятор:
{filters.min_battery}

Состояние:
{filters.conditions}

Ремонт:
{filters.repair_policy}

Экран:
{filters.screen_policy}

Город:
{filters.city}

МИНУСЫ/РИСКИ ОСОБЕННО ВАЖНЫ.

ОБЪЯВЛЕНИЕ:

ID:
{listing.id}

Название:
{listing.title}

Модель:
{listing.model}

Цена:
{listing.price} ₽

Память:
{listing.storage_gb}

Аккумулятор:
{listing.battery_percent}%

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

Дата:
{listing.posted_at}

Описание:

{listing.description}

Верни ТОЛЬКО JSON следующего вида:

{{
  "score": 0,
  "tier": "D",
  "verdict": "CAUTION",

  "summary": "",

  "advantages": [],
  "risks": [],
  "checks": [],

  "price_score": 0,
  "condition_score": 0,
  "battery_score": 0,
  "repair_score": 0,
  "seller_score": 0,

  "price_comment": "",
  "condition_comment": "",
  "repair_comment": ""
}}

Шкала:

90-100 = S
80-89 = A
70-79 = B
60-69 = C
0-59 = D

verdict:

BUY
GOOD
CAUTION
AVOID

Оценка должна учитывать:

- цену;
- состояние;
- аккумулятор;
- ремонт;
- экран;
- память;
- продавца;
- соответствие фильтрам;
- риски;
- полноту информации.

Если данных мало — снижай уверенность
и добавляй это в risks/checks.
"""

    @staticmethod
    def extract_json(
        text: str,
    ) -> dict[str, Any]:

        text = (
            text
            .strip()
            .replace(
                "\ufeff",
                "",
            )
        )

        if "```" in text:

            text = re.sub(
                r"```(?:json)?",
                "",
                text,
                flags=re.I,
            )

            text = text.replace(
                "```",
                "",
            )

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:

            raise ValueError(
                "ИИ не вернул JSON"
            )

        raw = text[
            start:end + 1
        ]

        return json.loads(raw)

    @staticmethod
    def normalize_result(
        data: dict[str, Any],
    ) -> AIAnalysis:

        score = int(
            data.get("score", 0)
        )

        score = max(
            0,
            min(
                100,
                score,
            ),
        )

        if score >= 90:
            tier = "S"
        elif score >= 80:
            tier = "A"
        elif score >= 70:
            tier = "B"
        elif score >= 60:
            tier = "C"
        else:
            tier = "D"

        verdict = str(
            data.get(
                "verdict",
                "CAUTION",
            )
        ).upper()

        allowed_verdicts = {
            "BUY",
            "GOOD",
            "CAUTION",
            "AVOID",
        }

        if verdict not in allowed_verdicts:
            verdict = "CAUTION"

        def list_value(
            key: str,
        ) -> list[str]:

            value = data.get(
                key,
                [],
            )

            if not isinstance(
                value,
                list,
            ):
                return []

            return [
                str(x)
                for x in value
                if x
            ][:10]

        return AIAnalysis(
            score=score,
            tier=tier,
            verdict=verdict,

            summary=str(
                data.get(
                    "summary",
                    "",
                )
            )[:1500],

            advantages=list_value(
                "advantages"
            ),

            risks=list_value(
                "risks"
            ),

            checks=list_value(
                "checks"
            ),

            price_score=int(
                data.get(
                    "price_score",
                    0,
                )
            ),

            condition_score=int(
                data.get(
                    "condition_score",
                    0,
                )
            ),

            battery_score=int(
                data.get(
                    "battery_score",
                    0,
                )
            ),

            repair_score=int(
                data.get(
                    "repair_score",
                    0,
                )
            ),

            seller_score=int(
                data.get(
                    "seller_score",
                    0,
                )
            ),

            price_comment=str(
                data.get(
                    "price_comment",
                    "",
                )
            ),

            condition_comment=str(
                data.get(
                    "condition_comment",
                    "",
                )
            ),

            repair_comment=str(
                data.get(
                    "repair_comment",
                    "",
                )
            ),
        )

    async def analyze_groq(
        self,
        listing: Listing,
        filters: SearchFilters,
    ) -> AIAnalysis:

        if not self.groq:

            raise RuntimeError(
                "GROQ_API_KEY не установлен"
            )

        response = (
            await self.groq.chat.completions.create(
                model=self.groq_model,

                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты очень строгий "
                            "эксперт по б/у iPhone. "
                            "Отвечай только JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": self.build_prompt(
                            listing,
                            filters,
                        ),
                    },
                ],

                temperature=0.1,

                response_format={
                    "type": "json_object"
                },

                max_tokens=1800,
            )
        )

        content = (
            response
            .choices[0]
            .message
            .content
        )

        data = self.extract_json(
            content
        )

        return self.normalize_result(
            data
        )

    async def analyze_gemini(
        self,
        listing: Listing,
        filters: SearchFilters,
    ) -> AIAnalysis:

        if not self.gemini:

            raise RuntimeError(
                "GEMINI_API_KEY не установлен"
            )

        response = (
            self.gemini.models.generate_content(
                model=self.gemini_model,

                contents=self.build_prompt(
                    listing,
                    filters,
                ),
            )
        )

        if not response.text:

            raise RuntimeError(
                "Gemini вернул пустой ответ"
            )

        data = self.extract_json(
            response.text
        )

        return self.normalize_result(
            data
        )

    async def analyze(
        self,
        listing: Listing,
        filters: SearchFilters,
    ) -> AIAnalysis:

        errors = []

        # 1. Groq
        try:

            result = await self.analyze_groq(
                listing,
                filters,
            )

            listing.ai_analysis = result

            return result

        except Exception as error:

            errors.append(
                f"Groq: {error}"
            )

            print(
                errors[-1]
            )

        # 2. Gemini
        try:

            result = await self.analyze_gemini(
                listing,
                filters,
            )

            listing.ai_analysis = result

            return result

        except Exception as error:

            errors.append(
                f"Gemini: {error}"
            )

            print(
                errors[-1]
            )

        # 3. Не падаем полностью
        fallback = AIAnalysis(
            score=0,
            tier="D",
            verdict="CAUTION",
            summary=(
                "AI-анализ временно "
                "недоступен."
            ),
            risks=[
                "Не удалось получить "
                "ответ от AI."
            ],
            checks=[
                "Проверь объявление "
                "вручную."
            ],
        )

        listing.ai_analysis = fallback

        return fallback
