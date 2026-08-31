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

    accessories_required: list[str] = field(
        default_factory=list
    )

    sort_by: str = "ai"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: Optional[dict[str, Any]],
    ) -> "SearchFilters":
        if not data:
            return cls()

        allowed = {
            "models",
            "min_price",
            "max_price",
            "storage",
            "min_battery",
            "conditions",
            "repair_policy",
            "screen_policy",
            "city",
            "radius_km",
            "seller_rating_min",
            "accessories_required",
            "sort_by",
        }

        clean = {
            key: value
            for key, value in data.items()
            if key in allowed
        }

        return cls(**clean)


@dataclass
class AIAnalysis:
    score: int = 0
    tier: str = "D"
    verdict: str = "CAUTION"

    summary: str = ""

    advantages: list[str] = field(
        default_factory=list
    )

    risks: list[str] = field(
        default_factory=list
    )

    checks: list[str] = field(
        default_factory=list
    )

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
    def from_dict(
        cls,
        data: Optional[dict[str, Any]],
    ) -> "AIAnalysis":
        if not data:
            return cls()

        return cls(
            score=int(data.get("score", 0)),
            tier=str(data.get("tier", "D")),
            verdict=str(
                data.get(
                    "verdict",
                    "CAUTION",
                )
            ),
            summary=str(
                data.get("summary", "")
            ),
            advantages=list(
                data.get("advantages", [])
            ),
            risks=list(
                data.get("risks", [])
            ),
            checks=list(
                data.get("checks", [])
            ),
            price_score=int(
                data.get("price_score", 0)
            ),
            condition_score=int(
                data.get("condition_score", 0)
            ),
            battery_score=int(
                data.get("battery_score", 0)
            ),
            repair_score=int(
                data.get("repair_score", 0)
            ),
            seller_score=int(
                data.get("seller_score", 0)
            ),
            price_comment=str(
                data.get("price_comment", "")
            ),
            condition_comment=str(
                data.get("condition_comment", "")
            ),
            repair_comment=str(
                data.get("repair_comment", "")
            ),
        )


@dataclass
class Listing:
    id: str

    title: str
    model: str

    price: int
    url: str

    description: str = ""

    photos: list[str] = field(
        default_factory=list
    )

    storage_gb: Optional[int] = None
    battery_percent: Optional[int] = None

    condition: Optional[str] = None
    color: Optional[str] = None

    repair_info: Optional[str] = None
    screen_info: Optional[str] = None

    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None

    city: Optional[str] = None

    accessories: list[str] = field(
        default_factory=list
    )

    posted_at: Optional[str] = None

    views: Optional[int] = None

    raw: dict[str, Any] = field(
        default_factory=dict
    )

    ai_analysis: Optional[AIAnalysis] = None

    def to_dict(
        self,
        include_raw: bool = True,
    ) -> dict[str, Any]:

        data = {
            "id": self.id,
            "title": self.title,
            "model": self.model,
            "price": self.price,
            "url": self.url,
            "description": self.description,
            "photos": self.photos,
            "storage_gb": self.storage_gb,
            "battery_percent": self.battery_percent,
            "condition": self.condition,
            "color": self.color,
            "repair_info": self.repair_info,
            "screen_info": self.screen_info,
            "seller_name": self.seller_name,
            "seller_rating": self.seller_rating,
            "city": self.city,
            "accessories": self.accessories,
            "posted_at": self.posted_at,
            "views": self.views,
            "ai_analysis": (
                self.ai_analysis.to_dict()
                if self.ai_analysis
                else None
            ),
        }

        if include_raw:
            data["raw"] = self.raw

        return data

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "Listing":

        return cls(
            id=str(data.get("id", "")),
            title=str(
                data.get("title", "iPhone")
            ),
            model=str(
                data.get("model", "")
            ),
            price=int(
                data.get("price", 0)
            ),
            url=str(
                data.get("url", "")
            ),
            description=str(
                data.get("description", "")
            ),
            photos=list(
                data.get("photos", [])
            ),
            storage_gb=data.get(
                "storage_gb"
            ),
            battery_percent=data.get(
                "battery_percent"
            ),
            condition=data.get(
                "condition"
            ),
            color=data.get("color"),
            repair_info=data.get(
                "repair_info"
            ),
            screen_info=data.get(
                "screen_info"
            ),
            seller_name=data.get(
                "seller_name"
            ),
            seller_rating=data.get(
                "seller_rating"
            ),
            city=data.get("city"),
            accessories=list(
                data.get("accessories", [])
            ),
            posted_at=data.get(
                "posted_at"
            ),
            views=data.get("views"),
            raw=dict(
                data.get("raw", {})
            ),
            ai_analysis=AIAnalysis.from_dict(
                data.get("ai_analysis")
            ),
        )
