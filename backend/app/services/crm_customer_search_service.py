"""Searchable index over customer fields the database cannot read.

Customer details are encrypted at rest, so no SQL predicate can match them. Decrypting
every customer on every keystroke does work, and it is what this replaces: the cost
grows with the whole base, one unreadable row breaks the search, and paging over a list
filtered in Python is a fiction.

Instead each customer contributes a set of keyed hashes — ``blind_index`` again, the
same construction already used for printer endpoints — and searching hashes the typed
text the same way. Matching becomes an ordinary indexed lookup.

What this gives up, stated plainly: two customers whose names start alike produce the
same token, so a stolen database shows which records share a prefix, and common names
can be confirmed by guessing. Without the key nothing else is recoverable, and the
alternative was reading every record in full on every keystroke.
"""

from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import blind_index
from app.models.crm import CrmCustomer, CrmCustomerSearchToken

TOKEN_CONTEXT = "crm-customer-search"

# Below three characters a prefix matches most of the base and the tokens are pure
# cost; above twelve nobody types the difference.
MIN_PREFIX = 3
MAX_PREFIX = 12
# A ceiling so one pathological record cannot fill the table.
MAX_TOKENS_PER_CUSTOMER = 512
# Below four digits a run matches most numbers; past twenty it is not a phone.
MIN_PHONE_RUN = 4
MAX_PHONE_DIGITS = 20

# Fields whose words people search by.
PREFIX_FIELDS = ("name", "contact_name", "address")
# Fields people type in full, where a prefix would only add noise.
EXACT_FIELDS = ("email", "inn")
# Notes are free text of unbounded length; indexing them would dominate the table for
# a kind of search nobody performs.

# Everything stored encrypted, for callers that need to read a customer in full.
ENCRYPTED_FIELDS = (*PREFIX_FIELDS, *EXACT_FIELDS, "phone", "note")

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_DIGITS_RE = re.compile(r"\D+")


def _normalize(value: str) -> str:
    return value.strip().casefold()


def _prefix_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for word in _WORD_RE.findall(_normalize(value)):
        limit = min(len(word), MAX_PREFIX)
        for size in range(MIN_PREFIX, limit + 1):
            tokens.add(word[:size])
        if len(word) < MIN_PREFIX:
            tokens.add(word)
    return tokens


def _phone_tokens(value: str) -> set[str]:
    """Every run of digits long enough to mean something.

    A phone is looked up by whatever part of it the person remembers — the tail, the
    middle block, the code — so prefixes alone are not enough. A number is short, so
    all of its runs still come to a few dozen terms.
    """
    digits = _DIGITS_RE.sub("", value)[:MAX_PHONE_DIGITS]
    if len(digits) < MIN_PHONE_RUN:
        return {digits} if digits else set()
    return {
        digits[start:end]
        for start in range(len(digits))
        for end in range(start + MIN_PHONE_RUN, len(digits) + 1)
    }


def search_terms(values: dict[str, str | None]) -> set[str]:
    """Every term this customer should be findable by, before hashing."""
    terms: set[str] = set()
    for field_name in PREFIX_FIELDS:
        value = values.get(field_name)
        if value:
            terms |= _prefix_tokens(value)
    for field_name in EXACT_FIELDS:
        value = values.get(field_name)
        if value:
            normalized = _normalize(value)
            terms.add(normalized)
            # An address is looked up by a piece of it — the name before the @ or the
            # company domain after it — at least as often as in full.
            terms |= _prefix_tokens(normalized)
    phone = values.get("phone")
    if phone:
        terms |= _phone_tokens(phone)
    if len(terms) <= MAX_TOKENS_PER_CUSTOMER:
        return terms
    # Shorter terms match more, so they are the ones worth keeping when a record is
    # unusually long. Dropping alphabetically would lose whole letters of the alphabet.
    return set(sorted(terms, key=len)[:MAX_TOKENS_PER_CUSTOMER])


def needle_token(search: str) -> str:
    """Hash typed text the same way the stored terms were hashed."""
    normalized = _normalize(search)
    digits = _DIGITS_RE.sub("", normalized)
    # Typed digits with no letters around them are a phone fragment, not a word.
    if len(digits) >= MIN_PHONE_RUN and not re.search(r"[^\W\d_]", normalized):
        return blind_index(digits[:MAX_PHONE_DIGITS], context=TOKEN_CONTEXT)
    return blind_index(normalized[:MAX_PREFIX], context=TOKEN_CONTEXT)


async def reindex_customer(
    db: AsyncSession,
    customer: CrmCustomer,
    plain_values: dict[str, str | None],
) -> None:
    """Replace this customer's search terms with the ones its current details give."""
    await db.execute(
        delete(CrmCustomerSearchToken).where(
            CrmCustomerSearchToken.customer_id == customer.id
        )
    )
    db.add_all(
        [
            CrmCustomerSearchToken(
                customer_id=customer.id,
                user_id=customer.user_id,
                token=blind_index(term, context=TOKEN_CONTEXT),
            )
            for term in search_terms(plain_values)
        ]
    )


async def matching_customer_ids(
    db: AsyncSession,
    *,
    user_id: int,
    search: str,
) -> list[int]:
    """Customers whose indexed terms contain the typed text."""
    term = search.strip()
    if not term:
        return []
    rows = await db.scalars(
        select(CrmCustomerSearchToken.customer_id).where(
            CrmCustomerSearchToken.user_id == user_id,
            CrmCustomerSearchToken.token == needle_token(term),
        )
    )
    return list(dict.fromkeys(rows.all()))
