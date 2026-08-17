"""Currency reference: the list itself, and lookups over it.

The list lives here rather than inside the migration that first created the table so
that one place answers "which currencies exist and who prices in them". The migration
seeds from this list, and tests seed from it too.
"""

from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import Currency


class CurrencyReference(NamedTuple):
    """One currency: how to write it, how to round it, and who bills in it."""

    code: str
    symbol: str
    # ISO 4217 minor units: yen and won have none, and "1400.00 ¥" is wrong.
    decimals: int
    # Smallest sensible "round the quote to" step. Ten roubles is small change; ten
    # dollars is a noticeable part of a small order.
    rounding_step: int
    countries: list[str]


# Ordered the way a person sees it in a dropdown: by how likely the currency is to be
# the one they want, not by alphabet. A list starting at AED buries the roubles,
# dollars and euros most of the audience actually prices in.
CURRENCY_REFERENCE: list[CurrencyReference] = [
    CurrencyReference("USD", "$", 2, 1, ["US", "EC", "SV", "PA", "TL", "ZW", "BQ", "MH",
                                         "FM", "PW", "TC", "VG", "VI", "GU", "AS", "MP", "PR"]),
    CurrencyReference("EUR", "€", 2, 1, ["AD", "AT", "BE", "CY", "DE", "EE", "ES", "FI",
                                         "FR", "GR", "HR", "IE", "IT", "LT", "LU", "LV",
                                         "MC", "ME", "MT", "NL", "PT", "SI", "SK", "SM",
                                         "VA", "XK"]),
    CurrencyReference("RUB", "₽", 2, 10, ["RU"]),
    CurrencyReference("CNY", "¥", 2, 1, ["CN"]),
    CurrencyReference("GBP", "£", 2, 1, ["GB", "GG", "IM", "JE"]),
    CurrencyReference("JPY", "¥", 0, 50, ["JP"]),
    CurrencyReference("INR", "₹", 2, 10, ["IN"]),
    CurrencyReference("CAD", "$", 2, 1, ["CA"]),
    CurrencyReference("AUD", "$", 2, 1, ["AU", "CX", "CC", "NF", "KI", "NR", "TV"]),
    CurrencyReference("BRL", "R$", 2, 1, ["BR"]),
    CurrencyReference("UAH", "₴", 2, 5, ["UA"]),
    CurrencyReference("KZT", "₸", 2, 50, ["KZ"]),
    CurrencyReference("PLN", "zł", 2, 1, ["PL"]),
    CurrencyReference("TRY", "₺", 2, 5, ["TR"]),
    CurrencyReference("KRW", "₩", 0, 200, ["KR"]),
    CurrencyReference("MXN", "$", 2, 5, ["MX"]),
    CurrencyReference("CHF", "CHF", 2, 1, ["CH", "LI"]),
    CurrencyReference("SEK", "kr", 2, 5, ["SE"]),
    CurrencyReference("CZK", "Kč", 2, 5, ["CZ"]),
    CurrencyReference("NOK", "kr", 2, 5, ["NO", "SJ", "BV"]),
    CurrencyReference("DKK", "kr", 2, 2, ["DK", "FO", "GL"]),
    CurrencyReference("ILS", "₪", 2, 1, ["IL"]),
    CurrencyReference("ZAR", "R", 2, 2, ["ZA", "LS", "NA", "SZ"]),
    CurrencyReference("SGD", "$", 2, 1, ["SG"]),
    CurrencyReference("HKD", "HK$", 2, 2, ["HK"]),
    CurrencyReference("NZD", "$", 2, 1, ["NZ", "CK", "NU", "PN", "TK"]),
    CurrencyReference("THB", "฿", 2, 5, ["TH"]),
    CurrencyReference("IDR", "Rp", 2, 2000, ["ID"]),
    CurrencyReference("MYR", "RM", 2, 1, ["MY"]),
    CurrencyReference("PHP", "₱", 2, 5, ["PH"]),
    CurrencyReference("VND", "₫", 0, 2000, ["VN"]),
    CurrencyReference("TWD", "NT$", 2, 5, ["TW"]),
    CurrencyReference("AED", "د.إ", 2, 1, ["AE"]),
    CurrencyReference("SAR", "﷼", 2, 1, ["SA"]),
    CurrencyReference("RON", "lei", 2, 1, ["RO"]),
    CurrencyReference("HUF", "Ft", 2, 50, ["HU"]),
    CurrencyReference("BYN", "Br", 2, 1, ["BY"]),
    CurrencyReference("GEL", "₾", 2, 1, ["GE"]),
    CurrencyReference("AMD", "֏", 2, 50, ["AM"]),
    CurrencyReference("AZN", "₼", 2, 1, ["AZ"]),
    CurrencyReference("UZS", "so'm", 2, 1000, ["UZ"]),
    CurrencyReference("KGS", "с", 2, 10, ["KG"]),
    CurrencyReference("MDL", "L", 2, 2, ["MD"]),
    CurrencyReference("RSD", "дин.", 2, 20, ["RS"]),
    CurrencyReference("ARS", "$", 2, 200, ["AR"]),
    CurrencyReference("CLP", "$", 0, 200, ["CL"]),
    CurrencyReference("COP", "$", 2, 500, ["CO"]),
    CurrencyReference("PEN", "S/", 2, 1, ["PE"]),
    CurrencyReference("UYU", "$U", 2, 10, ["UY"]),
    CurrencyReference("EGP", "E£", 2, 2, ["EG"]),
    CurrencyReference("MAD", "د.م.", 2, 1, ["MA", "EH"]),
    CurrencyReference("ISK", "kr", 0, 50, ["IS"]),
    CurrencyReference("IRR", "﷼", 2, 50000, ["IR"]),
]

# Gaps leave room to insert a currency later without renumbering the rest.
SORT_ORDER_STEP = 10

# Used only where nothing is known about the market. It is the platform's own money,
# not a claim about the person, so anything that can tell should tell first.
FALLBACK_CURRENCY = "RUB"


def currency_seed_rows() -> list[dict[str, object]]:
    """The reference as plain rows, for the migration and for tests."""
    return [
        {
            "code": entry.code,
            "symbol": entry.symbol,
            "decimals": entry.decimals,
            "rounding_step": entry.rounding_step,
            "sort_order": (position + 1) * SORT_ORDER_STEP,
            "countries": entry.countries,
            "active": True,
        }
        for position, entry in enumerate(CURRENCY_REFERENCE)
    ]


async def ensure_currency_reference(db: AsyncSession) -> None:
    """Add reference currencies the database does not have yet.

    Existing rows are left alone: an admin may have corrected a symbol or retired a
    currency, and a seed run is not a reason to undo that.
    """
    known = set((await db.scalars(select(Currency.code))).all())
    missing = [row for row in currency_seed_rows() if row["code"] not in known]
    if not missing:
        return
    db.add_all([Currency(**row) for row in missing])
    await db.commit()


async def currency_for_country(db: AsyncSession, country: str | None) -> str | None:
    """What a shop in this country bills in, or ``None`` when we do not know.

    Not knowing is a real answer: guessing a currency for an unrecognised country
    would put someone's rates under the wrong sign without telling them.
    """
    if not country:
        return None
    normalized = country.strip().upper()
    if len(normalized) != 2 or not normalized.isalpha():
        return None

    rows = await db.scalars(
        select(Currency).where(Currency.active.is_(True)).order_by(Currency.sort_order)
    )
    for row in rows:
        if normalized in (row.countries or []):
            return row.code
    return None
