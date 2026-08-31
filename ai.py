import asyncio
import json
import os
import re
from typing import Any

from google import genai
from openai import AsyncOpenAI

from models import AIAnalysis, Listing, SearchFilters


class AIAnalyzer:
    def __init__(self):
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

        self.groq = (
            AsyncOpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
            )
            if groq_key else None
        )
        self.gemini = genai.Client(api_key=gemini_key) if gemini_key else None

        self.groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def build_prompt(self, listing: Listing, filters: SearchFilters) -> str:
        return f"""
Ты строгий эксперт по покупке подержанных iPhone на российском рынке.
Анализируй только информацию из объявления. НИЧЕГО не выдумывай.
Если данных нет — пиши "не указано". Не утверждай отсутствие ремонта,
оригинальность деталей или исправность, если это не подтверждено.

Покупатель:
модели={filters.models}
бюджет={filters.min_price}..{filters.max_price}
память={filters.storage}
АКБ>={filters.min_battery}
состояние={filters.conditions}
ремонт={filters.repair_policy}
экран={filters.screen_policy}
город={filters.city}

Объявление:
id={listing.id}
title={listing.title}
model={listing.model}
price={listing.price}
storage={listing.storage_gb}
battery={listing.battery_percent}
condition={listing.condition}
color={listing.color}
repair={listing.repair_info}
screen={listing.screen_info}
seller={listing.seller_name}
seller_rating={listing.seller_rating}
city={listing.city}
accessories={listing.accessories}
posted_at={listing.posted_at}
description={listing.description}

Оцени цену, состояние, АКБ, ремонт, экран, память, продавца, полноту данных
и риски. Итог — не гарантия покупки.

Верни ТОЛЬКО JSON:
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

Шкала: S 90+, A 80+, B 70+, C 60+, D ниже 60.
verdict: BUY, GOOD, CAUTION, AVOID.
"""

    @staticmethod
    def extract_json(text: str) -> dict[str, Any]:
        text = re.sub(r"```(?:json)?|```", "", text or "", flags=re.I).strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("ИИ не вернул JSON")
        return json.loads(text[start:end + 1])

    @staticmethod
    def normalize_result(data: dict[str, Any]) -> AIAnalysis:
        def i(key):
            try:
                return int(data.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0

        score = max(0, min(100, i("score")))
        tier = "S" if score >= 90 else "A" if score >= 80 else "B" if score >= 70 else "C" if score >= 60 else "D"
        verdict = str(data.get("verdict", "CAUTION")).upper()
        if verdict not in {"BUY", "GOOD", "CAUTION", "AVOID"}:
            verdict = "CAUTION"

        def ls(key):
            value = data.get(key, [])
            return [str(x) for x in value if x][:10] if isinstance(value, list) else []

        return AIAnalysis(
            score=score,
            tier=tier,
            verdict=verdict,
            summary=str(data.get("summary", ""))[:1500],
            advantages=ls("advantages"),
            risks=ls("risks"),
            checks=ls("checks"),
            price_score=max(0, min(10, i("price_score"))),
            condition_score=max(0, min(10, i("condition_score"))),
            battery_score=max(0, min(10, i("battery_score"))),
            repair_score=max(0, min(10, i("repair_score"))),
            seller_score=max(0, min(10, i("seller_score"))),
            price_comment=str(data.get("price_comment", ""))[:500],
            condition_comment=str(data.get("condition_comment", ""))[:500],
            repair_comment=str(data.get("repair_comment", ""))[:500],
        )

    async def analyze_groq(self, listing: Listing, filters: SearchFilters) -> AIAnalysis:
        if not self.groq:
            raise RuntimeError("GROQ_API_KEY не установлен")
        response = await self.groq.chat.completions.create(
            model=self.groq_model,
            messages=[
                {"role": "system", "content": "Ты эксперт по б/у iPhone. Отвечай строго JSON."},
                {"role": "user", "content": self.build_prompt(listing, filters)},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            max_tokens=1800,
        )
        return self.normalize_result(self.extract_json(response.choices[0].message.content))

    async def analyze_gemini(self, listing: Listing, filters: SearchFilters) -> AIAnalysis:
        if not self.gemini:
            raise RuntimeError("GEMINI_API_KEY не установлен")
        response = await asyncio.to_thread(
            self.gemini.models.generate_content,
            model=self.gemini_model,
            contents=self.build_prompt(listing, filters),
        )
        if not getattr(response, "text", None):
            raise RuntimeError("Gemini вернул пустой ответ")
        return self.normalize_result(self.extract_json(response.text))

    async def analyze(self, listing: Listing, filters: SearchFilters) -> AIAnalysis:
        errors = []
        for provider in (self.analyze_groq, self.analyze_gemini):
            try:
                result = await provider(listing, filters)
                listing.ai_analysis = result
                return result
            except Exception as exc:
                errors.append(str(exc))
                print("AI:", exc)
        listing.ai_analysis = AIAnalysis(
            score=50,
            tier="D",
            verdict="CAUTION",
            summary="ИИ-анализ недоступен. Оценка построена без подтверждения ИИ.",
            risks=["Не удалось получить анализ Groq/Gemini."],
        )
        return listing.ai_analysis
