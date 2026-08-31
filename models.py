from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchFilters:

    models: list[str] = field(
        default_factory=list
    )

    min_price: Optional[int] = None
    max_price: Optional[int] = None

    storage: list[int] = field(
        default_factory=list
    )

    min_battery: Optional[int] = None

    conditions: list[str] = field(
        default_factory=list
    )

    repair_policy: str = "any"

    screen_policy: str = "any"

    battery_policy: str = "any"

    city: Optional[str] = None

    radius_km: Optional[int] = None

    accessories: list[str] = field(
        default_factory=list
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

    raw: dict = field(
        default_factory=dict
    )


@dataclass
class AIAnalysis:

    score: int

    tier: str

    verdict: str

    summary: str

    advantages: list[str]

    risks: list[str]

    checks: list[str]

    price_score: int = 0
    condition_score: int = 0
    battery_score: int = 0
    repair_score: int = 0
    seller_score: int = 0
