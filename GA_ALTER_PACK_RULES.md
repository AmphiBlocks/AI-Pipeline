# GA Alter Pack Rules

Use these rules for GA first-edition/alter product collation.

## Default Alter Model
- Standard slots use the base-set pool.
- CSR is product-specific:
  - First-ed CSR appears in first-ed packs.
  - Alter CSR appears in alter packs.
- Alter includes an `ALTER_SLOT` directly behind the Rare+ slot.
- `ALTER_SLOT` is for alter-exclusive non-CSR cards.
- Alter product keeps the same total card count as first-ed by replacing one common with `ALTER_SLOT`.

## Exceptions
- `DOA Alter` does not use an `ALTER_SLOT` pattern in this pipeline.
- `FTC` has no alter product.

## Current Size Rules In Pipeline
- 8-card first/alter model:
  - `MRC`
- 12-card first/alter model:
  - `ALC`
  - `DOA` (exception: no alter-slot model)
- 15/12 model:
  - `AMB 1st` = 15 cards
  - `AMB Alter` = 12 cards

## Source Of Truth
- `Grand Archive/Grand-Archive-TTS/build_ga_collation_data.py`
