from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class SearchFilters:
    models: list[str] = field(default_factory=list)
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    storage: list[int] = field(default_factory=list)
    min_battery: Optional[int] = None
    conditions: list[str] = field(default_factory=list)
    repair_policy: str = "any"
    screen_policy: str = "any"
    city: Optional[str] = None
    radius_km: Optional[int] = None
    seller_rating_min: Optional[float] = None
    accessories_required: list[str] = field(default_factory=list)
    sort_by: str = "ai"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "SearchFilters":
        if not data:
            return cls()
        allowed = set(cls().__dict__.keys())
        clean = {k: v for k, v in data.items() if k in allowed}
        clean["models"] = list(clean.get("models") or [])
        clean["storage"] = [int(x) for x in (clean.get("storage") or [])]
        clean["conditions"] = list(clean.get("conditions") or [])
        clean["accessories_required"] = list(clean.get("accessories_required") or [])
        return cls(**clean)


@dataclass
class AIAnalysis:
    score: int = 0
    tier: str = "D"
    verdict: str = "CAUTION"
    summary: str = ""
    advantages: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    price_score: int = 0
    condition_score: int = 0
    battery_score: int = 0
    repair_score: int = 0
    seller_score: int = 0
    price_comment: str = ""
    condition_comment: str = ""
    repair_comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "AIAnalysis":
        if not data:
            return None
        def integer(key: str) -> int:
            try:
                return int(data.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0
        return cls(
            score=max(0, min(100, integer("score"))),
            tier=str(data.get("tier", "D")),
            verdict=str(data.get("verdict", "CAUTION")).upper(),
            summary=str(data.get("summary", "")),
            advantages=[str(x) for x in (data.get("advantages") or [])][:10],
            risks=[str(x) for x in (data.get("risks") or [])][:10],
            checks=[str(x) for x in (data.get("checks") or [])][:10],
            price_score=integer("price_score"),
            condition_score=integer("condition_score"),
            battery_score=integer("battery_score"),
            repair_score=integer("repair_score"),
            seller_score=integer("seller_score"),
            price_comment=str(data.get("price_comment", "")),
            condition_comment=str(data.get("condition_comment", "")),
            repair_comment=str(data.get("repair_comment", "")),
        )


@dataclass
class Listing:
    id: str
    title: str
    model: str
    price: int
    url: str
    description: str = ""
    photos: list[str] = field(default_factory=list)
    storage_gb: Optional[int] = None
    battery_percent: Optional[int] = None
    condition: Optional[str] = None
    color: Optional[str] = None
    repair_info: Optional[str] = None
    screen_info: Optional[str] = None
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None
    city: Optional[str] = None
    accessories: list[str] = field(default_factory=list)
    posted_at: Optional[str] = None
    views: Optional[int] = None
    raw: dict[str, Any] = field(default_factory=dict)
    ai_analysis: Optional[AIAnalysis] = None

    def to_dict(self, include_raw: bool = True) -> dict[str, Any]:
        data = asdict(self)
        data["ai_analysis"] = self.ai_analysis.to_dict() if self.ai_analysis else None
        if not include_raw:
            data.pop("raw", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Listing":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "iPhone")),
            model=str(data.get("model", "")),
            price=int(data.get("price", 0) or 0),
            url=str(data.get("url", "")),
            description=str(data.get("description", "")),
            photos=list(data.get("photos") or []),
            storage_gb=int(data["storage_gb"]) if data.get("storage_gb") is not None else None,
            battery_percent=int(data["battery_percent"]) if data.get("battery_percent") is not None else None,
            condition=data.get("condition"),
            color=data.get("color"),
            repair_info=data.get("repair_info"),
            screen_info=data.get("screen_info"),
            seller_name=data.get("seller_name"),
            seller_rating=float(data["seller_rating"]) if data.get("seller_rating") is not None else None,
            city=data.get("city"),
            accessories=list(data.get("accessories") or []),
            posted_at=data.get("posted_at"),
            views=int(data["views"]) if data.get("views") is not None else None,
            raw=dict(data.get("raw") or {}),
            ai_analysis=AIAnalysis.from_dict(data.get("ai_analysis")),
        )
