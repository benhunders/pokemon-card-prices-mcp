# Pokémon Card Prices MCP

MCP server that gives AI agents access to Pokémon card prices:
- Cardmarket listings, trend prices, and seller info
- Graded prices (PSA 10, ACE 10, BGS, CGC, etc.)

Official Cardmarket API is closed to new applications, so this uses third-party providers (cardmarketapi.com, API.SH, PokeTrace, etc.).

## Setup

```bash
cp .env.example .env
# fill in your API keys

pip install -r requirements.txt
python server.py
```

## Tools

- `get_card_price(card_name, set_name?, grade?)` — price for raw or graded
- `get_listings(card_name, ...)` — live listings + seller data
- `compare_graded(card_name, grades)` — side-by-side graded prices

## Connect to Claude

1. Deploy this server (or run with a public tunnel)
2. In Claude: Customize → Connectors → Add custom connector
3. Paste the URL (e.g. `https://your-host/mcp`)

Free Claude tier allows 1 custom connector.

## Notes

- Implement the actual API calls in `server.py` (currently placeholders)
- Cache aggressively (1h recommended) to keep costs down
- Respect provider rate limits and terms
