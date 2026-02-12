# AI Workflow For TTS Mods

Use this workflow whenever modifying a TTS save.

1. Extract first.
   - `python aipipeline/tools/tts_pipeline.py extract --save "<path-to-save.json>"`
2. Regenerate context before making changes.
   - `python aipipeline/tools/tts_pipeline.py context --workspace "<workspace-dir>"`
3. Make edits only under `scripts/` inside the workspace.
4. Repack into an output save.
   - `python aipipeline/tools/tts_pipeline.py pack --workspace "<workspace-dir>" --output "<path-to-output.json>"`
5. Run diagnostics if anything feels missing.
   - `python aipipeline/tools/tts_pipeline.py doctor --workspace "<workspace-dir>"`

Guidelines:

- Do not hand-edit the full save JSON unless debugging the pipeline itself.
- If needed information is absent from extracted files, update `aipipeline/config/extract_rules.json` and rerun `extract`.
- Keep `context/CALLS.json`, `context/SCRIPT_INDEX.md`, and `context/CONTEXT.md` current after major changes.
- Record recurring extraction or mapping failures in `aipipeline/pipeline_gaps.md` via `doctor`.
