import re
from models import Listing, SearchFilters


def normalize(text: str | None) -> str:
    return str(text or "").strip().lower().replace("ё", "е")


def model_matches(listing: Listing, filters: SearchFilters) -> bool:
    if not filters.models:
        return True
    haystack = normalize(f"{listing.model} {listing.title}")
    return any(normalize(model) in haystack for model in filters.models)


def price_matches(listing: Listing, filters: SearchFilters) -> bool:
    if filters.min_price is not None and listing.price < filters.min_price:
        return False
    if filters.max_price is not None and listing.price > filters.max_price:
        return False
    return True


def storage_matches(listing: Listing, filters: SearchFilters) -> bool:
    return not filters.storage or listing.storage_gb in filters.storage


def battery_matches(listing: Listing, filters: SearchFilters) -> bool:
    return filters.min_battery is None or (
        listing.battery_percent is not None and listing.battery_percent >= filters.min_battery
    )


def condition_matches(listing: Listing, filters: SearchFilters) -> bool:
    if not filters.conditions:
        return True
    text = normalize(listing.condition)
    aliases = {
        "new": ["нов", "new"],
        "excellent": ["отлич", "идеал", "как новый", "excellent"],
        "good": ["хорош", "good"],
        "used": ["б/у", "бу", "использ", "used"],
    }
    wanted = []
    for item in filters.conditions:
        wanted.extend(aliases.get(item, [normalize(item)]))
    return any(x in text for x in wanted)


def repair_matches(listing: Listing, filters: SearchFilters) -> bool:
    policy = filters.repair_policy or "any"
    if policy == "any":
        return True
    text = normalize(f"{listing.repair_info or ''} {listing.description}")
    no_repair = ["без ремонта", "без ремонт", "не ремонтиров", "не вскрывал", "родн", "оригинал", "не менял"]
    if policy == "none":
        return any(x in text for x in no_repair)
    if policy == "changed":
        return not any(x in text for x in no_repair)
    return True


def screen_matches(listing: Listing, filters: SearchFilters) -> bool:
    policy = filters.screen_policy or "any"
    if policy == "any":
        return True
    text = normalize(f"{listing.screen_info or ''} {listing.description}")
    if policy == "original":
        return any(x in text for x in ["оригинал", "родной", "оригинальный"])
    if policy == "no_damage":
        return not any(x in text for x in ["трещ", "скол", "разбит", "битый", "царап"])
    return True


def city_matches(listing: Listing, filters: SearchFilters) -> bool:
    return not filters.city or (
        listing.city and normalize(filters.city) in normalize(listing.city)
    )


def seller_matches(listing: Listing, filters: SearchFilters) -> bool:
    return filters.seller_rating_min is None or (
        listing.seller_rating is not None and listing.seller_rating >= filters.seller_rating_min
    )


def accessories_match(listing: Listing, filters: SearchFilters) -> bool:
    if not filters.accessories_required:
        return True
    text = normalize(" ".join(listing.accessories) + " " + listing.description)
    return all(normalize(x) in text for x in filters.accessories_required)


def filter_listing(listing: Listing, filters: SearchFilters) -> bool:
    return all((
        model_matches(listing, filters),
        price_matches(listing, filters),
        storage_matches(listing, filters),
        battery_matches(listing, filters),
        condition_matches(listing, filters),
        repair_matches(listing, filters),
        screen_matches(listing, filters),
        city_matches(listing, filters),
        seller_matches(listing, filters),
        accessories_match(listing, filters),
    ))


def preliminary_score(listing: Listing, filters: SearchFilters) -> float:
    score = 0.0

    if filters.max_price and listing.price:
        ratio = min(1.0, listing.price / filters.max_price)
        score += 30 * (1 - ratio * 0.65)
    else:
        score += 15

    if listing.battery_percent is not None:
        b = listing.battery_percent
        score += 25 if b >= 95 else 22 if b >= 90 else 17 if b >= 85 else 10 if b >= 80 else 3
    else:
        score += 8

    if listing.storage_gb:
        score += 10 if listing.storage_gb >= 512 else 8 if listing.storage_gb >= 256 else 5

    repair = normalize(f"{listing.repair_info or ''} {listing.description}")
    if any(x in repair for x in ["без ремонта", "без ремонт", "не вскрывал", "родн", "оригинал"]):
        score += 20
    elif listing.repair_info:
        score += 6
    else:
        score += 8

    if listing.seller_rating is not None:
        score += min(15, listing.seller_rating / 5 * 15)
    else:
        score += 7

    return round(score, 2)


def prepare_candidates(listings: list[Listing], filters: SearchFilters) -> list[Listing]:
    result = [x for x in listings if filter_listing(x, filters)]
    result.sort(key=lambda x: preliminary_score(x, filters), reverse=True)
    return result


def sort_by_ai(listings: list[Listing]) -> list[Listing]:
    return sorted(
        listings,
        key=lambda x: (
            x.ai_analysis.score if x.ai_analysis else 0,
            preliminary_score(x, SearchFilters(max_price=x.price or None)),
        ),
        reverse=True,
    )
