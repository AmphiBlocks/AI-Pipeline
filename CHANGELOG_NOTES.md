# Changelog Notes

## 2026-02-13

### Notes Cleanup
- Reworked agent-facing documentation to remove stale implementation details and oversized object dumps.
- Updated:
  - `aipipeline/AI_WORKFLOW.md`
  - `aipipeline/GA_ALTER_PACK_RULES.md`
  - `aipipeline/GA_API_USAGE_NOTES.md`
  - `Grand Archive/Grand-Archive-TTS/AI_LAYOUT_NOTES.md`

### Current Booster/Collation Design (Documented)
- Pipeline-first save editing (`extract -> context -> edit -> pack`).
- `GA_CollationLibrary` holds booster collation data; `GA_EffectLibrary` remains effect lookup source.
- Collation payload optimizations are now baseline:
  - pool comment lines removed
  - sparse card records
  - DFC orientation data only where needed
  - identical pools deduplicated via Lua aliasing
- API usage guidance now emphasizes filtered queries (`prefix` + `rarity`) and controlled prefix-variant fallback for legacy tagging.

