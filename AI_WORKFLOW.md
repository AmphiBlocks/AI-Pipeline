# AI Workflow For TTS Mods

Use this workflow for all scripted save changes.

## Pipeline Steps
1. Extract:
   - `python aipipeline/tools/tts_pipeline.py extract --save "<path-to-save.json>"`
2. Build context:
   - `python aipipeline/tools/tts_pipeline.py context --workspace "<workspace-dir>"`
3. Edit only extracted scripts under `workspace/scripts/`.
4. Pack back to save:
   - `python aipipeline/tools/tts_pipeline.py pack --workspace "<workspace-dir>" --output "<path-to-save.json>"`
5. If needed, run diagnostics:
   - `python aipipeline/tools/tts_pipeline.py doctor --workspace "<workspace-dir>"`

## Design Choices (Current)
- Keep save editing pipeline-first; avoid hand-editing full `.json` except pipeline debugging.
- Keep booster collation data in `GA_CollationLibrary` and gameplay/effects in `GA_EffectLibrary`.
- Minimize collation payload:
  - No pool-line comments in generated Lua.
  - Sparse card records (booster spawn fields only).
  - DFC orientation data only when needed.
  - Identical pools are deduplicated by Lua aliasing.
- Handle old set tagging with prefix-based filtering and controlled fallback queries.

## GA-Specific References
- Alter product rules: `aipipeline/GA_ALTER_PACK_RULES.md`
- API query rules: `aipipeline/GA_API_USAGE_NOTES.md`

## Maintenance Rules
- After changing generation logic, rebuild collation output and re-inject library object.
- Keep workspace library scripts in sync with generated output.
- Keep notes current when product rules or set behavior changes.
