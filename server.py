"""
Pokémon Card Prices MCP Server

Exposes tools for Cardmarket listings/prices and graded card prices (PSA, ACE, etc.).
Uses third-party APIs since official Cardmarket API is closed to new apps.

Run:
  uv run server.py          # stdio
  python server.py          # streamable-http on :8000
"""

import os
import httpx
from typing import Optional
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("pokemon-card-prices")

CARDMARKET_API_KEY = os.getenv("CARDMARKET_API_KEY")
POKETRACE_API_KEY = os.getenv("POKETRACE_API_KEY")

# Placeholder base URLs — swap for real ones from cardmarketapi.com / API.SH / PokeTrace
CARDMARKET_BASE = "https://cardmarketapi.com/api/v1"
POKETRACE_BASE = "https://api.poketrace.com/v1"  # example


async def _fetch(url: str, headers: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers or {})
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_card_price(
    card_name: str,
    set_name: Optional[str] = None,
    grade: str = "raw",
) -> str:
    """
    Get current price for a Pokémon card.
    grade examples: raw, PSA_10, ACE_10, BGS_9.5, CGC_10
    """
    # TODO: Implement real search + price lookup against chosen provider
    # Example flow:
    # 1. Search card to get product id
    # 2. Fetch listings or trend price
    # 3. If graded, hit PokeTrace or equivalent

    if grade.lower() != "raw" and POKETRACE_API_KEY:
        # graded path
        return f"[placeholder] {grade} {card_name}{f' ({set_name})' if set_name else ''}: €X.XX (graded)"

    return f"[placeholder] {card_name}{f' ({set_name})' if set_name else ''}: €Y.YY (Cardmarket trend)"


@mcp.tool()
async def get_listings(
    card_name: str,
    set_name: Optional[str] = None,
    language: str = "English",
    condition: str = "Near Mint",
    limit: int = 10,
) -> str:
    """
    Get live Cardmarket listings for a card, including seller ratings when available.
    """
    # TODO: Call cardmarketapi.com or API.SH listings endpoint
    return f"[placeholder] Top {limit} listings for {card_name} ({condition}, {language})"


@mcp.tool()
async def compare_graded(
    card_name: str,
    grades: str = "PSA_10,ACE_10,BGS_10",
) -> str:
    """
    Compare prices across different grades for the same card.
    grades: comma-separated, e.g. PSA_10,ACE_10,CGC_9.5
    """
    grade_list = [g.strip() for g in grades.split(",")]
    lines = [f"{g}: €??" for g in grade_list]
    return f"Graded comparison for {card_name}:\n" + "\n".join(lines)


if __name__ == "__main__":
    # Default: streamable-http for remote use (Claude/ChatGPT custom connectors)
    # Change to transport="stdio" for local Claude Desktop
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
