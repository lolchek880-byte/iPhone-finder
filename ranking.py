from models import Listing, SearchFilters


def filter_listing(
    listing: Listing,
    filters: SearchFilters,
) -> bool:

    if filters.models:

        if not any(
            model.lower()
            in listing.model.lower()
            for model in filters.models
        ):
            return False


    if (
        filters.min_price is not None
        and listing.price < filters.min_price
    ):
        return False


    if (
        filters.max_price is not None
        and listing.price > filters.max_price
    ):
        return False


    if filters.storage:

        if (
            listing.storage_gb
            and listing.storage_gb
            not in filters.storage
        ):
            return False


    if (
        filters.min_battery is not None
    ):

        if (
            listing.battery_percent
            and
            listing.battery_percent
            < filters.min_battery
        ):
            return False


    if filters.city:

        if (
            listing.city
            and
            listing.city.lower()
            != filters.city.lower()
        ):
            return False


    return True


def preliminary_score(
    listing: Listing,
    filters: SearchFilters,
) -> float:

    score = 0


    if filters.max_price:

        if listing.price <= filters.max_price:

            difference = (
                filters.max_price -
                listing.price
            )

            score += min(
                30,
                difference /
                max(
                    filters.max_price,
                    1,
                ) *
                100
            )


    if listing.battery_percent:

        score += min(
            25,
            listing.battery_percent /
            100 *
            25
        )


    if listing.storage_gb:

        score += 10


    if listing.repair_info:

        if "нет" in (
            listing.repair_info
            .lower()
        ):

            score += 20

        else:

            score += 5

    else:

        score += 5


    if listing.seller_rating:

        score += min(
            15,
            listing.seller_rating /
            5 *
            15
        )


    return score


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
        key=lambda x:
            preliminary_score(
                x,
                filters,
            ),
        reverse=True,
    )


    return filtered
