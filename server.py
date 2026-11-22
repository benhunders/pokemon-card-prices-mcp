"""Pokémon card price MCP.

Raw EUR prices come from Cardmarket's public daily price guide and product
catalogue. No key. Live seller offers need CARDMARKET_API_KEY (cardmarketapi.com)
or APISH_API_KEY. Graded PSA / ACE / BGS / CGC prices need POKETRACE_API_KEY.
PokeTrace Pro is required for graded tiers and EU comps. Free is US raw only.

Nothing here invents a price. Missing data is reported as missing.

Run:
  python server.py                 # stdio, for Claude Desktop / local agents
  python server.py --http          # streamable HTTP on 0.0.0.0:8000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import httpx
from fastmcp import FastMCP

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

mcp = FastMCP("pokemon-card-prices")

GAME = 6
SINGLES_URL = f"https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_{GAME}.json"
NONSINGLES_URL = f"https://downloads.s3.cardmarket.com/productCatalog/productList/products_nonsingles_{GAME}.json"
GUIDE_URL = f"https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_{GAME}.json"
CACHE_DIR = Path(os.environ.get("PRICE_CACHE_DIR", Path.home() / ".cache" / "pokemon-card-prices"))
MAX_AGE = int(os.environ.get("CACHE_TTL_SECONDS", "72000"))

POKETRACE_BASE = "https://api.poketrace.com/v2"
CARDMARKET_API_BASE = "https://cardmarketapi.com/api/v1"
APISH_BASE = "https://api.api.sh/cardmarket/v1"

TAILS = (
    "booster box case",
    "booster display case",
    "booster case",
    "booster box",
    "booster pack",
    "booster",
    "elite trainer box",
    "trainer box",
    "build & battle stadium",
    "build & battle box",
    "build and battle box",
    "theme deck",
    "battle deck",
    "ultra premium collection",
    "premium collection",
    "special collection",
    "collection box",
    "blister pack",
    "blister",
    "bundle",
)

_INDEX: dict[str, Any] | None = None


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = Request(url, headers={"User-Agent": "pokemon-card-prices-mcp"})
    with urlopen(req, timeout=180) as response, tmp.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            handle.write(chunk)
    tmp.replace(dest)


def _fresh(path: Path) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < MAX_AGE


def _ensure(name: str, url: str) -> Path:
    path = CACHE_DIR / name
    if not _fresh(path):
        _download(url, path)
    return path


def _clean_price(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0 or number >= 99999:
        return None
    return round(number, 2)


def _strip_set(name: str) -> str:
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    for _ in range(6):
        lower = cleaned.lower()
        matched = False
        for tail in TAILS:
            if lower.endswith(" " + tail):
                cleaned = cleaned[: -(len(tail) + 1)].strip(" -–:")
                matched = True
                break
        if not matched:
            break
    return cleaned


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFD", value.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def _split_name(raw: str) -> tuple[str, str | None]:
    if raw.endswith("]") and " [" in raw:
        title, printing = raw.split(" [", 1)
        return title, printing[:-1].strip() or None
    return raw, None


def _kind(category: str) -> str:
    lowered = category.lower()
    if "single" in lowered:
        return "single"
    if any(hint in lowered for hint in ("booster", "display", "box", "tin", "deck", "collection", "blister", "bundle", "case")):
        return "sealed"
    return "other"


def _load_index() -> dict[str, Any]:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    singles = json.loads(_ensure("singles.json", SINGLES_URL).read_text())
    nons = json.loads(_ensure("nonsingles.json", NONSINGLES_URL).read_text())
    guide = json.loads(_ensure("price_guide.json", GUIDE_URL).read_text())
    prices: dict[int, dict[str, float | None]] = {}
    for row in guide["priceGuides"]:
        item = {
            "trend": _clean_price(row.get("trend")),
            "low": _clean_price(row.get("low")),
            "avg": _clean_price(row.get("avg")),
            "avg7": _clean_price(row.get("avg7")),
            "avg30": _clean_price(row.get("avg30")),
            "holoTrend": _clean_price(row.get("trend-holo")),
            "holoLow": _clean_price(row.get("low-holo")),
        }
        if item["low"] and item["trend"] and item["low"] > max(item["trend"] * 25, 5000):
            item["low"] = None
        if any(item.values()):
            prices[row["idProduct"]] = item

    votes: dict[int, dict[str, int]] = {}
    booster_votes: dict[int, dict[str, int]] = {}
    for product in nons["products"]:
        base = _strip_set(product["name"])
        if not 2 <= len(base) <= 60:
            continue
        votes.setdefault(product["idExpansion"], {})
        votes[product["idExpansion"]][base] = votes[product["idExpansion"]].get(base, 0) + 1
        category = (product.get("categoryName") or "").lower()
        if "booster" in category or "display" in category or "elite trainer" in category:
            booster_votes.setdefault(product["idExpansion"], {})
            booster_votes[product["idExpansion"]][base] = booster_votes[product["idExpansion"]].get(base, 0) + 1
    expansions = {
        exp_id: max((booster_votes.get(exp_id) or counts).items(), key=lambda item: item[1])[0]
        for exp_id, counts in votes.items()
    }

    cards = []
    for product in singles["products"]:
        cards.append(_card(product, "single", prices, expansions))
    for product in nons["products"]:
        cards.append(_card(product, _kind(product.get("categoryName") or ""), prices, expansions))
    _INDEX = {"updated": guide.get("createdAt"), "catalogUpdated": singles.get("createdAt"), "cards": cards}
    return _INDEX


def _card(product: dict[str, Any], kind: str, prices: dict[int, dict[str, float | None]], expansions: dict[int, str]) -> dict[str, Any]:
    title, printing = _split_name(product["name"])
    quote = prices.get(product["idProduct"], {})
    expansion = expansions.get(product["idExpansion"])
    hay = _norm(f"{product['name']} {expansion or ''}")
    return {
        "id": product["idProduct"],
        "name": product["name"],
        "title": title,
        "printing": printing,
        "expansion": expansion,
        "kind": kind,
        "hay": hay,
        "trend": quote.get("trend"),
        "low": quote.get("low"),
        "avg": quote.get("avg"),
        "avg7": quote.get("avg7"),
        "avg30": quote.get("avg30"),
        "holoTrend": quote.get("holoTrend"),
        "holoLow": quote.get("holoLow"),
    }


def _search(query: str, kind: str, limit: int) -> list[dict[str, Any]]:
    index = _load_index()
    phrase = _norm(query)
    tokens = [token for token in phrase.split() if token][:8]
    if not tokens:
        return []
    found = []
    for card in index["cards"]:
        if kind in ("single", "sealed") and card["kind"] != kind:
            continue
        padded = f" {card['hay']} "
        matched = sum(1 for token in tokens if f" {token}" in padded)
        phrase_hit = phrase in card["hay"]
        if matched == 0 and not phrase_hit:
            continue
        title = _norm(card["title"])
        score = matched * 10
        if matched == len(tokens):
            score += 14
        if phrase_hit:
            score += 16
        if title == phrase:
            score += 40
        elif title.startswith(phrase):
            score += 22
        if card["trend"] is not None:
            score += 2
        found.append((score, card))
    found.sort(key=lambda item: (item[0], item[1]["trend"] or -1), reverse=True)
    return [_public(card) | {"score": score} for score, card in found[:limit]]


def _public(card: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in card.items() if key != "hay"}


def _eur(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"€{value:,.2f}"


def _format_card(card: dict[str, Any]) -> str:
    where = card.get("expansion") or "set not named in the public catalogue"
    printing = f" [{card['printing']}]" if card.get("printing") else ""
    lines = [
        f"{card['title']}{printing}",
        f"{card['kind']} · {where} · product {card['id']}",
        f"trend {_eur(card.get('trend'))} · low {_eur(card.get('low'))} · avg {_eur(card.get('avg'))}",
        f"7-day {_eur(card.get('avg7'))} · 30-day {_eur(card.get('avg30'))}",
    ]
    if card.get("holoTrend") is not None or card.get("holoLow") is not None:
        lines.append(f"holo trend {_eur(card.get('holoTrend'))} · holo low {_eur(card.get('holoLow'))}")
    lines.append("Source: Cardmarket public price guide (daily, not live seller stock).")
    return "\n".join(lines)


@mcp.tool
async def search_cards(query: str, kind: str = "all", limit: int = 8) -> str:
    """Search the Cardmarket Pokémon price guide by card or product name.

    kind: all, single, or sealed. Prices are daily guide EUR figures, not live offers.
    """
    safe_limit = max(1, min(int(limit), 20))
    safe_kind = kind if kind in ("all", "single", "sealed") else "all"
    hits = _search(query, safe_kind, safe_limit)
    if not hits:
        return f"No Cardmarket guide match for {query!r}."
    updated = _load_index()["updated"]
    blocks = [_format_card(hit) for hit in hits]
    return f"Guide updated {updated}.\n\n" + "\n\n".join(blocks)


@mcp.tool
async def get_card_price(card_name: str, set_name: str = "", grade: str = "raw") -> str:
    """Get a price for one Pokémon card.

    grade raw uses the Cardmarket daily guide (no key).
    PSA_10, ACE_10, BGS_10, CGC_10 and similar call PokeTrace when POKETRACE_API_KEY is set.
    Graded numbers are never invented.
    """
    if grade.lower() not in ("raw", "ungraded", ""):
        return await compare_graded(card_name, grade)
    query = f"{card_name} {set_name}".strip()
    hits = _search(query, "all", 1)
    if not hits:
        return f"No Cardmarket guide price for {query!r}."
    return _format_card(hits[0])


@mcp.tool
async def compare_graded(card_name: str, grades: str = "PSA_10,ACE_10,BGS_10") -> str:
    """Compare graded prices for one card via PokeTrace.

    grades is comma-separated, for example PSA_10,ACE_10,BGS_9.5.
    Requires POKETRACE_API_KEY. Pro is required for graded and EU data.
    """
    key = os.environ.get("POKETRACE_API_KEY", "").strip()
    wanted = [part.strip().upper().replace(" ", "_") for part in grades.split(",") if part.strip()]
    if not key:
        return (
            "No graded price. Set POKETRACE_API_KEY. "
            "PSA 10 and ACE 10 need a PokeTrace Pro plan. The free plan is US raw only. "
            "This server does not invent graded numbers."
        )
    params = {"search": card_name, "limit": "8", "game": "pokemon"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{POKETRACE_BASE}/cards", params=params, headers={"X-API-Key": key})
    if response.status_code in (401, 403):
        return "PokeTrace rejected POKETRACE_API_KEY, or this plan cannot read graded / EU prices."
    if response.status_code >= 400:
        return f"PokeTrace returned {response.status_code}. No graded price shown."
    payload = response.json()
    cards = _extract_cards(payload)
    if not cards:
        return f"PokeTrace had no card named {card_name!r}."
    card = cards[0]
    prices = card.get("prices") if isinstance(card, dict) else None
    lines = []
    if isinstance(prices, dict):
        for grade, markets in prices.items():
            label = str(grade).upper()
            if wanted and label not in wanted and not any(label.startswith(item) for item in wanted):
                continue
            if not isinstance(markets, dict):
                continue
            for market, sources in markets.items():
                if not isinstance(sources, dict):
                    continue
                for source, quote in sources.items():
                    if not isinstance(quote, dict):
                        continue
                    avg = quote.get("avg")
                    low = quote.get("low")
                    if avg is None and low is None:
                        continue
                    lines.append(f"{label} · {market} · {source}: avg {avg} · low {low}")
    name = card.get("name") if isinstance(card, dict) else card_name
    if not lines:
        return (
            f"PokeTrace returned {name}, but none of {', '.join(wanted) or 'the requested grades'} had a price. "
            "Free plans do not include PSA/ACE/BGS/CGC."
        )
    return f"Graded prices for {name} from PokeTrace:\n" + "\n".join(lines[:30])


def _extract_cards(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "cards", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = _extract_cards(value)
                if nested:
                    return nested
        if "prices" in payload or "name" in payload:
            return [payload]
    return []


def _offers(payload: Any) -> list[dict[str, Any]]:
    rows: list[Any] = []
    if isinstance(payload, dict):
        for key in ("listings", "offers", "articles", "results"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        if not rows and isinstance(payload.get("data"), (dict, list)):
            return _offers(payload["data"])
    elif isinstance(payload, list):
        rows = payload
    offers = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        price = row.get("price", row.get("price_eur"))
        try:
            amount = float(price)
        except (TypeError, ValueError):
            continue
        seller = row.get("seller") if isinstance(row.get("seller"), str) else None
        seller_obj = row.get("seller") if isinstance(row.get("seller"), dict) else {}
        seller = seller or row.get("seller_name") or row.get("username") or seller_obj.get("username") or seller_obj.get("name")
        rating = row.get("seller_rating") or row.get("rating") or seller_obj.get("rating") or seller_obj.get("reputation")
        offers.append(
            {
                "price": amount,
                "seller": seller,
                "rating": rating,
                "condition": row.get("condition"),
                "language": row.get("language"),
                "country": row.get("country") or row.get("seller_country"),
            }
        )
    return offers[:12]


@mcp.tool
async def get_listings(
    card_name: str,
    product_id: int = 0,
    language: str = "",
    condition: str = "",
    limit: int = 8,
) -> str:
    """Live Cardmarket seller offers. Not part of the free price guide.

    Uses CARDMARKET_API_KEY against cardmarketapi.com, else APISH_API_KEY against API.SH.
    Seller ratings are shown only when the provider includes them.
    """
    cm_key = os.environ.get("CARDMARKET_API_KEY", "").strip()
    api_key = os.environ.get("APISH_API_KEY", "").strip()
    if not cm_key and not api_key:
        guide = _search(card_name, "all", 3)
        extra = ""
        if guide:
            extra = " Closest guide prices:\n\n" + "\n\n".join(_format_card(hit) for hit in guide)
        return (
            "No live listings. Official Cardmarket is not issuing new API apps. "
            "Set CARDMARKET_API_KEY (cardmarketapi.com) or APISH_API_KEY (API.SH, 1,000 free credits/month). "
            "Seller ratings are not in the public price guide."
            + extra
        )
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        if cm_key:
            headers["X-API-Key"] = cm_key
            url = f"{CARDMARKET_API_BASE}/card/{product_id}" if product_id else None
            if url is None:
                search = await client.get(
                    f"{CARDMARKET_API_BASE}/search",
                    params={"q": card_name, "game": "pokemon", "limit": 5},
                    headers=headers,
                )
                if search.status_code in (401, 403):
                    return "cardmarketapi.com rejected CARDMARKET_API_KEY."
                search.raise_for_status()
                results = _offers(search.json()) or _extract_cards(search.json())
                if not results:
                    return f"cardmarketapi.com had no match for {card_name!r}."
                found = results[0].get("id")
                url = f"{CARDMARKET_API_BASE}/card/{found}"
            response = await client.get(url, headers=headers)
            provider = "cardmarketapi.com"
        else:
            headers["x-api-key"] = api_key
            params: dict[str, Any] = {"game": "pokemon"}
            if product_id:
                params["idProduct"] = product_id
            else:
                params["q"] = card_name
            path = "offers" if product_id else "marketplace-search"
            response = await client.get(f"{APISH_BASE}/{path}", params=params, headers=headers)
            provider = "API.SH"
    if response.status_code in (401, 403):
        return f"{provider} rejected the API key."
    if response.status_code >= 400:
        return f"{provider} returned {response.status_code}. No listings shown."
    offers = _offers(response.json())[: max(1, min(int(limit), 20))]
    if language:
        offers = [offer for offer in offers if language.lower() in str(offer.get("language") or "").lower()] or offers
    if condition:
        offers = [offer for offer in offers if condition.lower() in str(offer.get("condition") or "").lower()] or offers
    if not offers:
        return f"{provider} answered for {card_name!r}, but the payload had no seller rows."
    lines = [f"Live offers for {card_name} via {provider}:"]
    for offer in offers:
        bits = [f"€{offer['price']:,.2f}"]
        if offer.get("seller"):
            bits.append(str(offer["seller"]))
        if offer.get("rating") not in (None, ""):
            bits.append(f"rating {offer['rating']}")
        else:
            bits.append("rating not in payload")
        for field in ("condition", "language", "country"):
            if offer.get(field):
                bits.append(str(offer[field]))
        lines.append(" · ".join(bits))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="Serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
