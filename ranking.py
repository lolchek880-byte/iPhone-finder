from models import Listing, SearchFilters


def normalize(text: str | None) -> str:
    if not text:
        return ""

    return (
        str(text)
        .strip()
        .lower()
        .replace("ё", "е")
    )


def model_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if not filters.models:
        return True

    haystack = normalize(
        f"{listing.model} {listing.title}"
    )

    return any(
        normalize(model) in haystack
        for model in filters.models
    )


def price_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if filters.min_price is not None:
        if listing.price < filters.min_price:
            return False

    if filters.max_price is not None:
        if listing.price > filters.max_price:
            return False

    return True


def storage_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if not filters.storage:
        return True

    if listing.storage_gb is None:
        return False

    return listing.storage_gb in filters.storage


def battery_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if filters.min_battery is None:
        return True

    if listing.battery_percent is None:
        return False

    return (
        listing.battery_percent
        >= filters.min_battery
    )


def condition_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if not filters.conditions:
        return True

    if not listing.condition:
        return False

    condition = normalize(
        listing.condition
    )

    aliases = {
        "new": [
            "новое",
            "новый",
            "как новый",
            "new",
        ],
        "excellent": [
            "отличное",
            "идеальное",
            "excellent",
        ],
        "good": [
            "хорошее",
            "good",
        ],
    }

    requested = []

    for item in filters.conditions:
        requested.extend(
            aliases.get(
                item,
                [item],
            )
        )

    return any(
        value in condition
        for value in requested
    )


def repair_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    policy = (
        filters.repair_policy
        or "any"
    )

    if policy == "any":
        return True

    if not listing.repair_info:
        return False

    repair = normalize(
        listing.repair_info
    )

    no_repair_words = [
        "не ремонт",
        "без ремонт",
        "не вскрывал",
        "не вскрывался",
        "оригинал",
        "родной",
        "не менял",
        "не менялось",
    ]

    if policy == "none":

        return any(
            word in repair
            for word in no_repair_words
        )

    return True


def screen_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    policy = (
        filters.screen_policy
        or "any"
    )

    if policy == "any":
        return True

    if not listing.screen_info:
        return False

    screen = normalize(
        listing.screen_info
    )

    if policy == "original":
        return any(
            word in screen
            for word in [
                "оригинал",
                "родной",
                "оригинальный",
            ]
        )

    if policy == "no_damage":
        return not any(
            word in screen
            for word in [
                "трещ",
                "скол",
                "разбит",
                "бит",
            ]
        )

    return True


def city_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if not filters.city:
        return True

    if not listing.city:
        return False

    return normalize(
        filters.city
    ) in normalize(
        listing.city
    )


def seller_matches(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if filters.seller_rating_min is None:
        return True

    if listing.seller_rating is None:
        return False

    return (
        listing.seller_rating
        >= filters.seller_rating_min
    )


def accessories_match(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if not filters.accessories_required:
        return True

    if not listing.accessories:
        return False

    available = normalize(
        " ".join(
            listing.accessories
        )
    )

    return all(
        normalize(item) in available
        for item in filters.accessories_required
    )


def filter_listing(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    checks = [
        model_matches(
            listing,
            filters,
        ),
        price_matches(
            listing,
            filters,
        ),
        storage_matches(
            listing,
            filters,
        ),
        battery_matches(
            listing,
            filters,
        ),
        condition_matches(
            listing,
            filters,
        ),
        repair_matches(
            listing,
            filters,
        ),
        screen_matches(
            listing,
            filters,
        ),
        city_matches(
            listing,
            filters,
        ),
        seller_matches(
            listing,
            filters,
        ),
        accessories_match(
            listing,
            filters,
        ),
    ]

    return all(checks)


def preliminary_score(
    listing: Listing,
    filters: SearchFilters,
) -> float:

    score = 0.0

    # Цена — до 30 баллов
    if filters.max_price:
        if listing.price <= filters.max_price:

            ratio = (
                listing.price
                / filters.max_price
            )

            score += max(
                0,
                30 * (1 - ratio * 0.7),
            )

    else:
        score += 15


    # АКБ — до 25
    if listing.battery_percent:

        battery = listing.battery_percent

        if battery >= 95:
            score += 25
        elif battery >= 90:
            score += 22
        elif battery >= 85:
            score += 17
        elif battery >= 80:
            score += 10
        else:
            score += 3


    # Память
    if listing.storage_gb:

        if listing.storage_gb >= 512:
            score += 10
        elif listing.storage_gb >= 256:
            score += 8
        else:
            score += 5


    # Ремонт
    if listing.repair_info:

        repair = normalize(
            listing.repair_info
        )

        if any(
            word in repair
            for word in [
                "без ремонт",
                "не ремонт",
                "родной",
                "оригинал",
            ]
        ):
            score += 20
        else:
            score += 6

    else:
        score += 2


    # Продавец
    if listing.seller_rating:

        score += min(
            15,
            (
                listing.seller_rating
                / 5
            ) * 15,
        )


    return round(score, 2)


def prepare_candidates(
    listings: list[Listing],
    filters: SearchFilters,
) -> list[Listing]:

    filtered = [
        listing
        for listing in listings
        if filter_listing(
            listing,
            filters,
        )
    ]

    filtered.sort(
        key=lambda item:
            preliminary_score(
                item,
                filters,
            ),
        reverse=True,
    )

    return filtered


def sort_by_ai(
    listings: list[Listing],
) -> list[Listing]:

    return sorted(
        listings,
        key=lambda item:
            (
                item.ai_analysis.score
                if item.ai_analysis
                else 0
            ),
        reverse=True,
    )
