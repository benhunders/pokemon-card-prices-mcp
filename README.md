# Pokémon card prices

A small MCP server for Cardmarket Pokémon prices, plus graded comps when you have a key.

Official Cardmarket is not accepting new API applications, and existing credentials must not be shared. This server does not pretend to use that API.

## What is real with no key

Cardmarket publishes a daily price guide and product catalogue. The server downloads those files, caches them for about 20 hours, and searches them locally.

You get, in EUR:

- trend
- low
- average sell
- 7-day and 30-day averages
- the same figures for reverse / holo when Cardmarket publishes them

That is the daily guide, not live seller stock and not seller ratings.

## What needs a key

| Data | Env var | Provider |
| --- | --- | --- |
| PSA 10, ACE 10, BGS, CGC | `POKETRACE_API_KEY` | [PokeTrace](https://www.poketrace.com). Pro for graded and EU. Free is US raw only. |
| Live offers and seller ratings | `CARDMARKET_API_KEY` | [cardmarketapi.com](https://www.cardmarketapi.com) |
| Same, pay as you go | `APISH_API_KEY` | [API.SH Cardmarket](https://api.sh/cardmarket-api). 1,000 free credits a month. |

If a key is missing or the plan does not include the data, the tool says so. It does not fill in a price.

## Tools

- `search_cards` — guide search
- `get_card_price` — one card, raw by default
- `compare_graded` — PokeTrace grades
- `get_listings` — live offers when a listings key is set, otherwise the guide plus a clear refusal

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py              # stdio
python server.py --http       # http://127.0.0.1:8000/mcp
```

Copy `.env.example` to `.env` if you have keys. Do not commit `.env`.

Claude Free can attach one remote MCP connector, and it has to be a public HTTPS URL. This repo is the server. Host `python server.py --http` somewhere that serves HTTPS, then in Claude use Customize → Connectors. ChatGPT Free cannot add a custom MCP server. This Grok chat cannot attach one either.

## Cache

Files land in `~/.cache/pokemon-card-prices/` unless `PRICE_CACHE_DIR` is set. The first search downloads about 30 MB.
