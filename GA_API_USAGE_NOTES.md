# Grand Archive API Usage Notes

## Use This Endpoint
- `GET https://api.gatcg.com/cards/search`

## Query Strategy
- Never trawl entire sets for chase cards.
- Query by filter:
  - `prefix=<set-prefix>`
  - `rarity=<id>`
  - `page`, `page_size`
- Use prefix variants when legacy tagging is inconsistent:
  - space and plus forms, e.g. `DTR 1st` and `DTR+1st`.

## Rarity IDs Used By Collation
- `5` = Ultra Rare (UR)
- `7` = Collector Super Rare (CSR)
- `8` = Collector Ultra Rare (CUR)
- `6` = promotional/event-pack path (exclude from normal booster collation)

## Query Templates
- UR:
  - `/cards/search?prefix=<PREFIX>&rarity=5&page=1&page_size=50`
- CSR:
  - `/cards/search?prefix=<PREFIX>&rarity=7&page=1&page_size=50`
- CUR:
  - `/cards/search?prefix=<PREFIX>&rarity=8&page=1&page_size=50`

## Example (DTR first-ed chase)
- `https://api.gatcg.com/cards/search?prefix=DTR+1st&rarity=5&page=1&page_size=50`
- `https://api.gatcg.com/cards/search?prefix=DTR+1st&rarity=7&page=1&page_size=50`
- `https://api.gatcg.com/cards/search?prefix=DTR+1st&rarity=8&page=1&page_size=50`
