#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "extract_rules.json"
DEFAULT_WORKSPACES_ROOT = ROOT / "workspaces"
DEFAULT_GAPS_PATH = ROOT / "pipeline_gaps.md"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "workspace"


def path_tokens_to_string(tokens: List[Any]) -> str:
    parts: List[str] = []
    for token in tokens:
        if isinstance(token, int):
            parts.append(f"[{token}]")
        else:
            parts.append(token if not parts else f".{token}")
    return "".join(parts) if parts else "<root>"


def read_text_exact(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_text_exact(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load_config(path: Path | None) -> Dict[str, Any]:
    resolved = path or DEFAULT_CONFIG_PATH
    if not resolved.exists():
        raise FileNotFoundError(f"Config not found: {resolved}")
    config = read_json(resolved)
    fields = config.get("fields", [])
    if not fields:
        raise ValueError("Config must include non-empty 'fields'.")
    return config


def obj_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def walk_objects(
    obj: Dict[str, Any],
    path: List[Any],
    parent: Dict[str, Any] | None,
    depth: int,
) -> Iterable[Dict[str, Any]]:
    meta = {
        "path": path,
        "path_string": path_tokens_to_string(path),
        "guid": obj_string(obj.get("GUID")),
        "name": obj_string(obj.get("Name")),
        "nickname": obj_string(obj.get("Nickname")),
        "parent_guid": obj_string(parent.get("guid")) if parent else "",
        "parent_name": obj_string(parent.get("name")) if parent else "",
        "parent_nickname": obj_string(parent.get("nickname")) if parent else "",
        "depth": depth,
        "contained_count": len(obj.get("ContainedObjects") or []),
    }
    yield meta
    for index, child in enumerate(obj.get("ContainedObjects") or []):
        child_path = path + ["ContainedObjects", index]
        yield from walk_objects(child, child_path, meta, depth + 1)


def scan_save(save_data: Dict[str, Any]) -> Dict[str, Any]:
    object_states = save_data.get("ObjectStates") or []
    objects: List[Dict[str, Any]] = []
    for index, obj in enumerate(object_states):
        objects.extend(
            list(walk_objects(obj, ["ObjectStates", index], parent=None, depth=0))
        )

    global_lua = obj_string(save_data.get("LuaScript"))
    global_xml = obj_string(save_data.get("XmlUI"))
    global_state = obj_string(save_data.get("LuaScriptState"))

    scripted_objects = []
    containers = []
    for meta in objects:
        ref = get_by_path(save_data, meta["path"])
        lua = obj_string(ref.get("LuaScript"))
        xml = obj_string(ref.get("XmlUI"))
        if lua or xml:
            scripted_objects.append(
                {
                    "guid": meta["guid"],
                    "name": meta["name"],
                    "nickname": meta["nickname"],
                    "depth": meta["depth"],
                    "lua_len": len(lua),
                    "xml_len": len(xml),
                    "path": meta["path_string"],
                }
            )
        if meta["contained_count"] > 0:
            containers.append(
                {
                    "guid": meta["guid"],
                    "name": meta["name"],
                    "nickname": meta["nickname"],
                    "contained_count": meta["contained_count"],
                    "path": meta["path_string"],
                }
            )

    scripted_objects.sort(key=lambda x: x["lua_len"] + x["xml_len"], reverse=True)
    containers.sort(key=lambda x: x["contained_count"], reverse=True)

    return {
        "save_name": obj_string(save_data.get("SaveName")),
        "version_number": obj_string(save_data.get("VersionNumber")),
        "object_state_count": len(object_states),
        "object_count_all_levels": len(objects),
        "global": {
            "lua_len": len(global_lua),
            "xml_len": len(global_xml),
            "state_len": len(global_state),
        },
        "scripted_object_count": len(scripted_objects),
        "scripted_objects_top": scripted_objects[:40],
        "containers_top": containers[:40],
    }


def ext_for_field(field: str, config: Dict[str, Any]) -> str:
    mapping = config.get("field_extensions", {})
    return obj_string(mapping.get(field) or ".txt")


def collect_entries(save_data: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = config["fields"]
    extract_empty = bool(config.get("extract_empty_fields", False))
    include_global = bool(config.get("include_global", True))
    include_objects = bool(config.get("include_objects", True))

    entries: List[Dict[str, Any]] = []
    counter = 0

    def maybe_add(
        kind: str,
        field: str,
        content: str,
        path_tokens: List[Any],
        guid: str = "",
        name: str = "",
        nickname: str = "",
        parent_guid: str = "",
        depth: int = 0,
    ) -> None:
        nonlocal counter
        if not extract_empty and content == "":
            return
        counter += 1
        if kind == "global":
            rel = Path("scripts") / "global" / f"{field}{ext_for_field(field, config)}"
        else:
            label = safe_slug(nickname or name or "object")
            guid_label = safe_slug(guid or "noguid")
            folder = f"{counter:04d}_{guid_label}_{label}"
            rel = Path("scripts") / "objects" / folder / f"{field}{ext_for_field(field, config)}"
        entries.append(
            {
                "id": f"{counter:04d}",
                "kind": kind,
                "field": field,
                "json_path": path_tokens,
                "json_path_string": path_tokens_to_string(path_tokens),
                "guid": guid,
                "name": name,
                "nickname": nickname,
                "parent_guid": parent_guid,
                "depth": depth,
                "file_rel": rel.as_posix(),
                "length": len(content),
                "original_hash": stable_hash(content),
            }
        )

    if include_global:
        for field in fields:
            maybe_add(
                kind="global",
                field=field,
                content=obj_string(save_data.get(field)),
                path_tokens=[field],
            )

    if include_objects:
        for index, obj in enumerate(save_data.get("ObjectStates") or []):
            for meta in walk_objects(obj, ["ObjectStates", index], parent=None, depth=0):
                ref = get_by_path(save_data, meta["path"])
                for field in fields:
                    if field in ref:
                        maybe_add(
                            kind="object",
                            field=field,
                            content=obj_string(ref.get(field)),
                            path_tokens=meta["path"] + [field],
                            guid=meta["guid"],
                            name=meta["name"],
                            nickname=meta["nickname"],
                            parent_guid=meta["parent_guid"],
                            depth=meta["depth"],
                        )

    return entries


def get_by_path(data: Any, path_tokens: List[Any]) -> Any:
    current = data
    for token in path_tokens:
        if isinstance(token, int):
            current = current[token]
        else:
            current = current[token]
    return current


def set_by_path(data: Any, path_tokens: List[Any], value: Any) -> None:
    if not path_tokens:
        raise ValueError("Cannot set root path.")
    parent = get_by_path(data, path_tokens[:-1]) if len(path_tokens) > 1 else data
    last = path_tokens[-1]
    if isinstance(last, int):
        parent[last] = value
    else:
        parent[last] = value


def ensure_workspace(workspace: Path, save_path: Path, config_path: Path) -> Dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    for rel in ("scripts", "context", "reports", "out"):
        (workspace / rel).mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": 1,
        "workspace_name": workspace.name,
        "created_at": now_iso(),
        "source_save_path": str(save_path.resolve()),
        "config_path": str(config_path.resolve()),
    }
    write_json(workspace / "workspace.json", metadata)
    return metadata


def load_workspace(workspace: Path) -> Dict[str, Any]:
    meta_path = workspace / "workspace.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"Missing workspace metadata: {meta_path}")
    return read_json(meta_path)


def derive_workspace_path(save_path: Path, explicit_workspace: Path | None) -> Path:
    if explicit_workspace:
        return explicit_workspace
    slug = safe_slug(save_path.stem)
    return DEFAULT_WORKSPACES_ROOT / slug


def command_scan(args: argparse.Namespace) -> int:
    save_path = Path(args.save).resolve()
    save_data = read_json(save_path)
    summary = scan_save(save_data)
    summary["source_save_path"] = str(save_path)
    print(json.dumps(summary, indent=2, ensure_ascii=True))

    if args.workspace:
        workspace = Path(args.workspace)
        (workspace / "reports").mkdir(parents=True, exist_ok=True)
        write_json(workspace / "reports" / "scan.json", summary)
    return 0


def command_extract(args: argparse.Namespace) -> int:
    save_path = Path(args.save).resolve()
    config_path = Path(args.config).resolve() if args.config else DEFAULT_CONFIG_PATH
    config = load_config(config_path)
    workspace = derive_workspace_path(save_path, Path(args.workspace) if args.workspace else None)
    workspace = workspace.resolve()

    save_data = read_json(save_path)
    ensure_workspace(workspace, save_path, config_path)
    entries = collect_entries(save_data, config)

    # Clean previous scripts for deterministic output.
    scripts_dir = workspace / "scripts"
    if scripts_dir.exists():
        for item in sorted(scripts_dir.rglob("*"), reverse=True):
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                try:
                    item.rmdir()
                except OSError:
                    pass
    scripts_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        content = obj_string(get_by_path(save_data, entry["json_path"]))
        write_text_exact(workspace / entry["file_rel"], content)

    manifest = {
        "schema_version": 1,
        "source_save_path": str(save_path),
        "extracted_at": now_iso(),
        "entry_count": len(entries),
        "entries": entries,
    }
    write_json(workspace / "manifest.json", manifest)

    summary = scan_save(save_data)
    summary["source_save_path"] = str(save_path)
    summary["workspace"] = str(workspace)
    summary["extracted_entry_count"] = len(entries)
    write_json(workspace / "reports" / "scan.json", summary)
    write_json(workspace / "reports" / "extract.json", {"workspace": str(workspace), "entry_count": len(entries)})

    print(f"Extracted {len(entries)} fields to {workspace}")
    return 0


def collect_lua_symbols(content: str) -> Dict[str, Any]:
    defs = set(re.findall(r"^\s*function\s+([A-Za-z_][\w\.]*)\s*\(", content, flags=re.MULTILINE))
    defs.update(
        f"local:{name}"
        for name in re.findall(
            r"^\s*local\s+function\s+([A-Za-z_][\w]*)\s*\(", content, flags=re.MULTILINE
        )
    )
    global_calls = sorted(set(re.findall(r"Global\.call\s*\(\s*['\"]([^'\"]+)['\"]", content)))
    global_get_vars = sorted(
        set(re.findall(r"Global\.getVar\s*\(\s*['\"]([^'\"]+)['\"]", content))
    )
    guid_refs = sorted(
        set(re.findall(r"getObjectFromGUID\s*\(\s*['\"]([0-9a-fA-F]{6})['\"]", content))
    )
    return {
        "function_defs": sorted(defs),
        "global_calls": global_calls,
        "global_get_vars": global_get_vars,
        "guid_refs": guid_refs,
    }


def load_manifest(workspace: Path) -> Dict[str, Any]:
    manifest_path = workspace / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")
    return read_json(manifest_path)


def load_entry_texts(workspace: Path, manifest: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for entry in manifest["entries"]:
        file_path = workspace / entry["file_rel"]
        if not file_path.exists():
            raise FileNotFoundError(f"Missing extracted file: {file_path}")
        out[entry["id"]] = read_text_exact(file_path)
    return out


def build_context(workspace: Path, manifest: Dict[str, Any]) -> Dict[str, Any]:
    workspace_meta = load_workspace(workspace)
    source_path = Path(workspace_meta["source_save_path"])
    save_data = read_json(source_path)
    scan = scan_save(save_data)

    entry_texts = load_entry_texts(workspace, manifest)
    global_function_defs: set[str] = set()
    object_guids = {entry["guid"] for entry in manifest["entries"] if entry["guid"]}
    script_rows: List[Dict[str, Any]] = []
    all_global_calls: set[str] = set()
    all_guid_refs: set[str] = set()
    all_get_vars: set[str] = set()

    for entry in manifest["entries"]:
        content = entry_texts[entry["id"]]
        symbols = collect_lua_symbols(content) if entry["field"] == "LuaScript" else {
            "function_defs": [],
            "global_calls": [],
            "global_get_vars": [],
            "guid_refs": [],
        }
        if entry["kind"] == "global" and entry["field"] == "LuaScript":
            global_function_defs.update(
                d.split("local:", 1)[-1] for d in symbols["function_defs"] if not d.startswith("local:")
            )
            global_function_defs.update(
                d for d in symbols["function_defs"] if "." in d and not d.startswith("local:")
            )

        all_global_calls.update(symbols["global_calls"])
        all_guid_refs.update(symbols["guid_refs"])
        all_get_vars.update(symbols["global_get_vars"])

        script_rows.append(
            {
                "id": entry["id"],
                "kind": entry["kind"],
                "field": entry["field"],
                "guid": entry["guid"],
                "name": entry["name"],
                "nickname": entry["nickname"],
                "file_rel": entry["file_rel"],
                "length": len(content),
                "functions": symbols["function_defs"],
                "global_calls": symbols["global_calls"],
                "global_get_vars": symbols["global_get_vars"],
                "guid_refs": symbols["guid_refs"],
            }
        )

    unresolved_global_calls = sorted(
        call for call in all_global_calls if call not in global_function_defs
    )
    unresolved_guid_refs = sorted(g for g in all_guid_refs if g not in object_guids)

    calls = {
        "generated_at": now_iso(),
        "global_function_defs": sorted(global_function_defs),
        "global_calls_all": sorted(all_global_calls),
        "global_get_vars_all": sorted(all_get_vars),
        "guid_refs_all": sorted(all_guid_refs),
        "unresolved_global_calls": unresolved_global_calls,
        "unresolved_guid_refs": unresolved_guid_refs,
        "scripts": script_rows,
    }

    script_rows_sorted = sorted(script_rows, key=lambda row: row["length"], reverse=True)
    scripted_containers = []
    for container in scan["containers_top"]:
        if container["contained_count"] <= 0:
            continue
        path_tokens = parse_path_string(container["path"])
        obj = get_by_path(save_data, path_tokens)
        contained = obj.get("ContainedObjects") or []
        scripted = 0
        for child in contained:
            if obj_string(child.get("LuaScript")) or obj_string(child.get("XmlUI")):
                scripted += 1
        scripted_containers.append(
            {
                "guid": container["guid"],
                "name": container["name"],
                "nickname": container["nickname"],
                "contained_count": len(contained),
                "contained_scripted_count": scripted,
            }
        )

    return {
        "scan": scan,
        "calls": calls,
        "script_rows_sorted": script_rows_sorted,
        "scripted_containers": scripted_containers,
    }


def parse_path_string(path_string: str) -> List[Any]:
    # Input format from path_tokens_to_string, e.g. ObjectStates[1].ContainedObjects[0].LuaScript
    tokens: List[Any] = []
    if path_string in ("", "<root>"):
        return tokens
    for segment in path_string.split("."):
        while segment:
            if "[" in segment:
                left, right = segment.split("[", 1)
                if left:
                    tokens.append(left)
                index_text, rest = right.split("]", 1)
                tokens.append(int(index_text))
                segment = rest
            else:
                tokens.append(segment)
                segment = ""
    return tokens


def render_script_index(context: Dict[str, Any], manifest: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Script Index")
    lines.append("")
    lines.append(f"- Generated: {now_iso()}")
    lines.append(f"- Total extracted fields: {manifest['entry_count']}")
    lines.append(f"- Script-bearing entries: {sum(1 for row in context['script_rows_sorted'] if row['length'] > 0)}")
    lines.append("")
    lines.append("| Size | Kind | Field | GUID | Name | Nickname | File |")
    lines.append("| ---: | --- | --- | --- | --- | --- | --- |")
    for row in context["script_rows_sorted"]:
        lines.append(
            f"| {row['length']} | {row['kind']} | {row['field']} | {row['guid'] or ''} | "
            f"{(row['name'] or '').replace('|', '\\|')} | {(row['nickname'] or '').replace('|', '\\|')} | "
            f"{row['file_rel']} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_context_md(context: Dict[str, Any], workspace: Path, manifest: Dict[str, Any]) -> str:
    scan = context["scan"]
    calls = context["calls"]
    major = scan["scripted_objects_top"][:12]
    lines: List[str] = []
    lines.append("# TTS Context")
    lines.append("")
    lines.append(f"- Generated: {now_iso()}")
    lines.append(f"- Workspace: `{workspace}`")
    lines.append(f"- SaveName: `{scan['save_name']}`")
    lines.append(f"- Version: `{scan['version_number']}`")
    lines.append(f"- ObjectStates: `{scan['object_state_count']}`")
    lines.append(f"- Extracted fields: `{manifest['entry_count']}`")
    lines.append("")
    lines.append("## Core Layout")
    lines.append("")
    lines.append(f"- Global Lua length: `{scan['global']['lua_len']}`")
    lines.append(f"- Global XmlUI length: `{scan['global']['xml_len']}`")
    lines.append(f"- Scripted objects (non-global): `{scan['scripted_object_count']}`")
    lines.append("")
    lines.append("## Largest Script Objects")
    lines.append("")
    for row in major:
        lines.append(
            f"- `{row['guid']}` `{row['name']}` `{row['nickname']}` "
            f"(lua={row['lua_len']}, xml={row['xml_len']}, depth={row['depth']})"
        )
    lines.append("")
    lines.append("## Scripted Containers")
    lines.append("")
    for row in context["scripted_containers"][:20]:
        lines.append(
            f"- `{row['guid']}` `{row['name']}` `{row['nickname']}` "
            f"(contained={row['contained_count']}, contained_scripted={row['contained_scripted_count']})"
        )
    lines.append("")
    lines.append("## Call Graph Signals")
    lines.append("")
    lines.append(f"- Global function definitions discovered: `{len(calls['global_function_defs'])}`")
    lines.append(f"- Distinct `Global.call` names: `{len(calls['global_calls_all'])}`")
    lines.append(f"- Distinct `getObjectFromGUID` references: `{len(calls['guid_refs_all'])}`")
    if calls["unresolved_global_calls"]:
        lines.append(f"- Unresolved `Global.call` names: `{', '.join(calls['unresolved_global_calls'][:25])}`")
    else:
        lines.append("- Unresolved `Global.call` names: none")
    if calls["unresolved_guid_refs"]:
        lines.append(f"- Unresolved GUID refs: `{', '.join(calls['unresolved_guid_refs'][:25])}`")
    else:
        lines.append("- Unresolved GUID refs: none")
    lines.append("")
    lines.append("## Workflow Hint")
    lines.append("")
    lines.append("- Edit only files under `scripts/` and repack with `pack`.")
    lines.append("- Run `context` after major changes to refresh dependency hints.")
    lines.append("- Run `doctor` when extraction feels incomplete; add findings to config/rules.")
    lines.append("")
    return "\n".join(lines)


def command_context(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    manifest = load_manifest(workspace)
    context_data = build_context(workspace, manifest)

    context_dir = workspace / "context"
    context_dir.mkdir(parents=True, exist_ok=True)
    write_json(context_dir / "CALLS.json", context_data["calls"])
    write_text_exact(context_dir / "SCRIPT_INDEX.md", render_script_index(context_data, manifest))
    write_text_exact(context_dir / "CONTEXT.md", render_context_md(context_data, workspace, manifest))
    write_json(workspace / "reports" / "context.json", {"generated_at": now_iso(), "workspace": str(workspace)})

    print(f"Context files generated under {context_dir}")
    return 0


def command_pack(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    manifest = load_manifest(workspace)
    workspace_meta = load_workspace(workspace)
    source_save = Path(workspace_meta["source_save_path"])
    source_data = read_json(source_save)

    changed: List[Dict[str, Any]] = []
    missing_files: List[str] = []
    for entry in manifest["entries"]:
        file_path = workspace / entry["file_rel"]
        if not file_path.exists():
            missing_files.append(str(file_path))
            continue
        content = read_text_exact(file_path)
        new_hash = stable_hash(content)
        if new_hash != entry["original_hash"]:
            changed.append(
                {
                    "id": entry["id"],
                    "field": entry["field"],
                    "guid": entry["guid"],
                    "name": entry["name"],
                    "nickname": entry["nickname"],
                    "file_rel": entry["file_rel"],
                    "from_hash": entry["original_hash"],
                    "to_hash": new_hash,
                }
            )
        set_by_path(source_data, entry["json_path"], content)

    if missing_files:
        raise FileNotFoundError("Missing extracted files:\n" + "\n".join(missing_files))

    if args.output:
        out_path = Path(args.output).resolve()
    else:
        out_name = source_save.stem + "__ai_pipeline.json"
        out_path = (workspace / "out" / out_name).resolve()
    write_json(out_path, source_data)

    report = {
        "generated_at": now_iso(),
        "workspace": str(workspace),
        "source_save_path": str(source_save),
        "output_save_path": str(out_path),
        "changed_field_count": len(changed),
        "changed_fields": changed,
    }
    write_json(workspace / "reports" / "pack.json", report)

    print(f"Packed save written: {out_path}")
    print(f"Changed extracted fields: {len(changed)}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    manifest = load_manifest(workspace)
    workspace_meta = load_workspace(workspace)
    source_save = Path(workspace_meta["source_save_path"])

    issues: List[str] = []
    warnings: List[str] = []
    stats: Dict[str, Any] = {}

    if not source_save.exists():
        issues.append(f"Source save path missing: {source_save}")
    else:
        source_data = read_json(source_save)
        stale = []
        for entry in manifest["entries"]:
            try:
                current = obj_string(get_by_path(source_data, entry["json_path"]))
            except Exception as exc:
                issues.append(f"Path no longer valid for entry {entry['id']}: {exc}")
                continue
            if stable_hash(current) != entry["original_hash"]:
                stale.append(entry["id"])
        if stale:
            warnings.append(
                f"{len(stale)} entries differ from source save; workspace may be stale vs source JSON."
            )
        stats["stale_entry_ids"] = stale

    missing = []
    edited = []
    for entry in manifest["entries"]:
        file_path = workspace / entry["file_rel"]
        if not file_path.exists():
            missing.append(entry["file_rel"])
            continue
        content = read_text_exact(file_path)
        if stable_hash(content) != entry["original_hash"]:
            edited.append(entry["id"])
    if missing:
        issues.append(f"{len(missing)} extracted files are missing.")
    stats["missing_files"] = missing
    stats["edited_entry_ids"] = edited

    calls_path = workspace / "context" / "CALLS.json"
    if calls_path.exists():
        calls_data = read_json(calls_path)
        unresolved_calls = calls_data.get("unresolved_global_calls", [])
        unresolved_guids = calls_data.get("unresolved_guid_refs", [])
        if unresolved_calls:
            warnings.append(f"{len(unresolved_calls)} unresolved Global.call names.")
        if unresolved_guids:
            warnings.append(f"{len(unresolved_guids)} unresolved GUID references.")
        stats["unresolved_global_calls"] = unresolved_calls
        stats["unresolved_guid_refs"] = unresolved_guids
    else:
        warnings.append("Context call graph missing; run `context`.")

    report = {
        "generated_at": now_iso(),
        "workspace": str(workspace),
        "issues": issues,
        "warnings": warnings,
        "stats": stats,
    }
    write_json(workspace / "reports" / "doctor.json", report)

    if issues or warnings:
        lines = []
        lines.append(f"## {now_iso()} `{workspace.name}`")
        if issues:
            lines.append("- Issues:")
            for issue in issues:
                lines.append(f"  - {issue}")
        if warnings:
            lines.append("- Warnings:")
            for warning in warnings:
                lines.append(f"  - {warning}")
        lines.append("")
        append_text = "\n".join(lines)
        if DEFAULT_GAPS_PATH.exists():
            prior = read_text_exact(DEFAULT_GAPS_PATH)
            if not prior.endswith("\n"):
                prior += "\n"
            write_text_exact(DEFAULT_GAPS_PATH, prior + append_text)
        else:
            write_text_exact(DEFAULT_GAPS_PATH, "# Pipeline Gaps\n\n" + append_text)

    print(f"Doctor report written: {workspace / 'reports' / 'doctor.json'}")
    print(f"Issues: {len(issues)} | Warnings: {len(warnings)}")
    return 0 if not issues else 2


def render_layout_notes(
    scan: Dict[str, Any],
    workspace: Path,
    source_save: Path,
    title: str | None = None,
) -> str:
    heading = title or f"AI Layout Notes - {source_save.stem}"
    script_rows = scan.get("scripted_objects_top", [])[:14]
    container_rows = scan.get("containers_top", [])[:12]
    source_dir = source_save.parent

    lines: List[str] = []
    lines.append(f"# {heading}")
    lines.append("")
    lines.append(f"Last updated: {dt.datetime.now().date().isoformat()}")
    lines.append("")
    lines.append("## Primary files in this directory")
    lines.append(f"- Main save: `{source_save.name}`")
    out_candidates = sorted(source_dir.glob(f"{source_save.stem}*.json"))
    if out_candidates:
        for candidate in out_candidates[:4]:
            if candidate.name == source_save.name:
                continue
            lines.append(f"- Related save: `{candidate.name}`")
    lines.append("")
    lines.append("## Preferred AI workflow")
    lines.append("- Use extraction/context pipeline before editing.")
    lines.append(f"- Workspace: `{workspace}`")
    lines.append(f"- Extracted global script: `{workspace / 'scripts' / 'global' / 'LuaScript.lua'}`")
    lines.append(f"- Script map/context: `{workspace / 'context' / 'CONTEXT.md'}`")
    lines.append(f"- Call graph: `{workspace / 'context' / 'CALLS.json'}`")
    lines.append("- Repack through pipeline instead of manual full JSON edits.")
    lines.append("")
    lines.append("## Save structure summary")
    lines.append(f"- TTS version observed: `{scan.get('version_number', '')}`")
    lines.append(f"- `ObjectStates` count: `{scan.get('object_state_count', 0)}`")
    global_meta = scan.get("global", {})
    lines.append(f"- Global Lua length: `{global_meta.get('lua_len', 0)}`")
    lines.append(f"- Global XmlUI length: `{global_meta.get('xml_len', 0)}`")
    lines.append(f"- Scripted objects (non-global): `{scan.get('scripted_object_count', 0)}`")
    lines.append("")
    lines.append("## Major script-bearing objects")
    for row in script_rows:
        lines.append(
            f"- `{row.get('guid','')}` `{row.get('name','')}` `{row.get('nickname','')}` "
            f"(lua={row.get('lua_len',0)}, xml={row.get('xml_len',0)}, depth={row.get('depth',0)})"
        )
    lines.append("")
    lines.append("## Containers worth checking")
    for row in container_rows:
        lines.append(
            f"- `{row.get('guid','')}` `{row.get('name','')}` `{row.get('nickname','')}` "
            f"(contained={row.get('contained_count',0)})"
        )
    lines.append("")
    lines.append("## Exploration order")
    lines.append("1. Refresh extract/context in pipeline workspace.")
    lines.append("2. Inspect global script entrypoints first.")
    lines.append("3. Inspect major helper/library objects and menu modules.")
    lines.append("4. Inspect relevant container prototypes for clone/spawn behavior.")
    lines.append("5. Repack and test in TTS.")
    lines.append("")
    lines.append("## Caveat")
    lines.append("- GUIDs/object indexes may drift between save revisions; re-scan when save changes.")
    lines.append("")
    return "\n".join(lines)


def command_refresh_notes(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    workspace_meta = load_workspace(workspace)
    source_save = Path(workspace_meta["source_save_path"]).resolve()
    if not source_save.exists():
        raise FileNotFoundError(f"Source save does not exist: {source_save}")
    save_data = read_json(source_save)
    scan = scan_save(save_data)
    output = Path(args.output).resolve() if args.output else (source_save.parent / "AI_LAYOUT_NOTES.md")
    title = args.title if args.title else None
    content = render_layout_notes(scan, workspace, source_save, title=title)
    write_text_exact(output, content)
    print(f"Layout notes written: {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract, edit, and repack Tabletop Simulator save scripts."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Summarize save layout and scripted structure.")
    scan.add_argument("--save", required=True, help="Path to TTS save JSON.")
    scan.add_argument("--workspace", help="Optional workspace path for report output.")
    scan.set_defaults(func=command_scan)

    extract = sub.add_parser("extract", help="Extract script fields into workspace files.")
    extract.add_argument("--save", required=True, help="Path to TTS save JSON.")
    extract.add_argument("--workspace", help="Workspace directory; default is aipipeline/workspaces/<slug>.")
    extract.add_argument("--config", help=f"Config path (default: {DEFAULT_CONFIG_PATH}).")
    extract.set_defaults(func=command_extract)

    context = sub.add_parser("context", help="Generate script index and call graph context files.")
    context.add_argument("--workspace", required=True, help="Workspace directory from extract step.")
    context.set_defaults(func=command_context)

    pack = sub.add_parser("pack", help="Pack edited extracted scripts back into a save JSON.")
    pack.add_argument("--workspace", required=True, help="Workspace directory from extract step.")
    pack.add_argument("--output", help="Output save path. Defaults to workspace/out/<source>__ai_pipeline.json.")
    pack.set_defaults(func=command_pack)

    doctor = sub.add_parser("doctor", help="Validate workspace integrity and report extraction gaps.")
    doctor.add_argument("--workspace", required=True, help="Workspace directory from extract step.")
    doctor.set_defaults(func=command_doctor)

    refresh_notes = sub.add_parser(
        "refresh-notes",
        help="Generate/update AI_LAYOUT_NOTES.md for a mod from workspace + source save.",
    )
    refresh_notes.add_argument("--workspace", required=True, help="Workspace directory from extract step.")
    refresh_notes.add_argument("--output", help="Output markdown path; defaults to <save-dir>/AI_LAYOUT_NOTES.md.")
    refresh_notes.add_argument("--title", help="Optional heading title.")
    refresh_notes.set_defaults(func=command_refresh_notes)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
