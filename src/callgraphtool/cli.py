from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


def _vendored_callgraph_path() -> Path:
    return Path(__file__).resolve().parent / "callGraph"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _results_dir() -> Path:
    return _repo_root() / "results"


def _project_local_perl5lib() -> Path:
    return Path(__file__).resolve().parents[2] / ".perl5" / "lib" / "perl5"


_LANGUAGE_ALIASES: dict[str, str] = {
    # callGraph codes (as-is)
    "awk": "awk",
    "bas": "bas",
    "c": "c",
    "cpp": "cpp",
    "dart": "dart",
    "for": "for",
    "go": "go",
    "java": "java",
    "jl": "jl",
    "js": "js",
    "kt": "kt",
    "lua": "lua",
    "m": "m",
    "pas": "pas",
    "php": "php",
    "pl": "pl",
    "py": "py",
    "r": "r",
    "rb": "rb",
    "rs": "rs",
    "sc": "sc",
    "sh": "sh",
    "swift": "swift",
    "tcl": "tcl",
    "ts": "ts",
    "v": "v",
    # friendly aliases
    "bash": "sh",
    "basic": "bas",
    "fortran": "for",
    "javascript": "js",
    "julia": "jl",
    "kotlin": "kt",
    "matlab": "m",
    "pascal": "pas",
    "perl": "pl",
    "python": "py",
    "ruby": "rb",
    "rust": "rs",
    "scala": "sc",
    "typescript": "ts",
    "verilog": "v",
}


def _resolve_callgraph_bin(explicit_path: str | None) -> str | None:
    if explicit_path:
        return explicit_path

    env_path = os.environ.get("CALLGRAPH_BIN")
    if env_path:
        return env_path

    vendored = _vendored_callgraph_path()
    if vendored.exists():
        return str(vendored)

    return shutil.which("callGraph")


def _normalize_language(language: str | None) -> str | None:
    if not language:
        return None
    return _LANGUAGE_ALIASES.get(language.strip().lower(), language.strip())


def _infer_language(folder: Path) -> str | None:
    ext_to_lang = {
        ".awk": "awk",
        ".bash": "sh",
        ".bas": "bas",
        ".dart": "dart",
        ".f": "for",
        ".f90": "for",
        ".go": "go",
        ".jl": "jl",
        ".js": "js",
        ".kt": "kotlin",
        ".lua": "lua",
        ".m": "m",
        ".pas": "pas",
        ".php": "php",
        ".pl": "pl",
        ".pm": "pl",
        ".py": "py",
        ".r": "r",
        ".rb": "rb",
        ".rs": "rs",
        ".scala": "sc",
        ".sh": "sh",
        ".swift": "swift",
        ".tcl": "tcl",
        ".ts": "ts",
    }

    counts: dict[str, int] = {}
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        language = _normalize_language(ext_to_lang.get(path.suffix.lower()))
        if not language:
            continue
        counts[language] = counts.get(language, 0) + 1

    if not counts:
        return None

    top_language, top_count = max(counts.items(), key=lambda item: item[1])
    if list(counts.values()).count(top_count) > 1:
        return None
    return top_language


def _normalize_start(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw

    if re.search(r"\s", raw):
        match = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)", raw)
        if match:
            return match.group(1)

        match = re.search(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)", raw)
        if match:
            return match.group(1)

    return raw


def _default_output_path(function_name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", function_name).strip("_") or "callgraph"
    return _results_dir() / f"callgraph_{safe}.png"


def _default_subset_code_path(function_name: str, language: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", function_name).strip("_") or "subset"
    lang_to_ext = {
        "awk": ".awk",
        "bas": ".bas",
        "dart": ".dart",
        "for": ".f90",
        "go": ".go",
        "jl": ".jl",
        "js": ".js",
        "kt": ".kt",
        "lua": ".lua",
        "m": ".m",
        "pas": ".pas",
        "php": ".php",
        "pl": ".pl",
        "py": ".py",
        "r": ".r",
        "rb": ".rb",
        "rs": ".rs",
        "sc": ".scala",
        "sh": ".sh",
        "swift": ".swift",
        "tcl": ".tcl",
        "ts": ".ts",
        "v": ".v",
    }
    return _results_dir() / f"subset_{safe}{lang_to_ext.get(language, '.txt')}"


def _start_selector(folder: Path, raw: str) -> tuple[str, str]:
    """
    Returns (start_pattern_for_callGraph, start_label_for_output_paths).

    If `raw` looks like `<file>:<function>` and the file exists (absolute or relative to `folder`),
    an exact, anchored selector is generated so only that specific function node is selected.
    """

    raw = raw.strip()
    if not raw:
        return raw, raw

    if ":" in raw:
        maybe_file, maybe_func_spec = raw.split(":", 1)
        maybe_file = maybe_file.strip()
        maybe_func_spec = maybe_func_spec.strip()

        file_path = Path(maybe_file)
        candidate = file_path if file_path.is_absolute() else folder / file_path
        if maybe_file and maybe_func_spec and file_path.suffix and candidate.exists():
            func_name = _normalize_start(maybe_func_spec)
            start_pattern = rf"\A{re.escape(str(candidate))}:{re.escape(func_name)}\z"

            label_file = maybe_file
            if file_path.is_absolute():
                try:
                    label_file = str(candidate.resolve().relative_to(folder.resolve()))
                except Exception:
                    label_file = maybe_file
            start_label = f"{label_file}:{func_name}"
            return start_pattern, start_label

    start = _normalize_start(raw)
    return start, start


_COMMENT_PREFIX_BY_LANGUAGE: dict[str, str] = {
    "awk": "#",
    "bas": "'",
    "c": "//",
    "cpp": "//",
    "dart": "//",
    "for": "!",
    "go": "//",
    "java": "//",
    "jl": "#",
    "js": "//",
    "kt": "//",
    "lua": "--",
    "m": "%",
    "pas": "//",
    "php": "//",
    "pl": "#",
    "py": "#",
    "r": "#",
    "rb": "#",
    "rs": "//",
    "sc": "//",
    "sh": "#",
    "swift": "//",
    "tcl": "#",
    "ts": "//",
    "v": "//",
}


def _comment_prefix(language: str) -> str:
    return _COMMENT_PREFIX_BY_LANGUAGE.get(language, "#")


def _dot_to_call_tree(dot_text: str, subset_text: str, folder: Path) -> list[str]:
    node_block_re = re.compile(r"(?ms)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*\[(.*?)\];")
    edge_re = re.compile(r"(?m)^[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*->[ \t]*([A-Za-z_][A-Za-z0-9_]*)\b")

    node_file: dict[str, str] = {}
    node_func: dict[str, str] = {}
    initial_nodes: list[str] = []

    for match in node_block_re.finditer(dot_text):
        node_id = match.group(1)
        attrs = match.group(2)
        label_match = re.search(r'label="([^"]*)"', attrs)
        if not label_match:
            continue
        label = label_match.group(1)
        if label == r"\N":
            continue

        label = label.replace(r"\n", "\n")
        parts = [part for part in label.split("\n") if part]
        if len(parts) >= 2:
            node_file[node_id] = parts[0]
            node_func[node_id] = parts[-1]
        else:
            node_file[node_id] = ""
            node_func[node_id] = label

        if "fillcolor" in attrs and "/greens3/2" in attrs:
            initial_nodes.append(node_id)

    edges = edge_re.findall(dot_text)
    calls: dict[str, list[str]] = {}
    indegree: dict[str, int] = {}
    for from_node, to_node in edges:
        calls.setdefault(from_node, []).append(to_node)
        indegree[to_node] = indegree.get(to_node, 0) + 1
        indegree.setdefault(from_node, indegree.get(from_node, 0))

    roots = initial_nodes or sorted([node for node, degree in indegree.items() if degree == 0])

    sources_by_basename_func: dict[tuple[str, str], set[str]] = {}
    sources_by_relpath_func: dict[tuple[str, str], str] = {}
    for match in re.finditer(r"Source:\s+(.+?):(\d+)\s+\(([^)]+)\)", subset_text):
        rel_path, line_num, func = match.group(1), match.group(2), match.group(3)
        sources_by_basename_func.setdefault((Path(rel_path).name, func), set()).add(
            f"{rel_path}:{line_num}"
        )
        sources_by_relpath_func[(rel_path, func)] = f"{rel_path}:{line_num}"

    def display_label(node_id: str) -> str:
        func = node_func.get(node_id, node_id)
        file_label = node_file.get(node_id, "")

        source: str | None = None
        normalized_file_label: str | None = None

        if file_label and ("/" in file_label or "\\" in file_label):
            try:
                candidate = Path(file_label)
                if candidate.is_absolute():
                    normalized_file_label = str(candidate.resolve().relative_to(folder.resolve()))
                else:
                    normalized_file_label = str(candidate)
            except Exception:
                normalized_file_label = file_label

            source = sources_by_relpath_func.get((normalized_file_label, func))

        if source is None and file_label:
            candidates = sources_by_basename_func.get((Path(file_label).name, func), set())
            if len(candidates) == 1:
                source = next(iter(candidates))

        if source:
            return f"{func} ({source})"
        if normalized_file_label:
            return f"{func} ({normalized_file_label})"
        if file_label:
            return f"{func} ({file_label})"
        return func

    def child_sort_key(node_id: str) -> tuple[str, str]:
        return (node_func.get(node_id, node_id), node_file.get(node_id, ""))

    lines: list[str] = []
    if not roots:
        return lines

    lines.append("Call Tree (caller -> callee)")

    global_seen: set[str] = set()

    def dfs(node_id: str, prefix: str, path: set[str]) -> None:
        children = sorted(set(calls.get(node_id, [])), key=child_sort_key)
        for index, child in enumerate(children):
            is_last = index == len(children) - 1
            branch = "└─ " if is_last else "├─ "
            next_prefix = prefix + ("   " if is_last else "│  ")

            label = display_label(child)
            if child in path:
                lines.append(f"{prefix}{branch}{label} (cycle)")
                continue
            if child in global_seen:
                lines.append(f"{prefix}{branch}{label} (seen)")
                continue

            lines.append(f"{prefix}{branch}{label}")
            global_seen.add(child)
            path.add(child)
            dfs(child, next_prefix, path)
            path.remove(child)

    for root in roots:
        if root in global_seen:
            continue
        if len(roots) > 1 and lines[-1] != "Call Tree (caller -> callee)":
            lines.append("")
        root_label = display_label(root)
        lines.append(root_label)
        global_seen.add(root)
        dfs(root, "", {root})

    return lines


def _prepend_tree_to_subset_file(
    subset_code: Path, language: str, tree_lines: list[str]
) -> None:
    if not tree_lines:
        return

    comment_prefix = _comment_prefix(language)
    content = subset_code.read_text(encoding="utf-8", errors="replace")
    original_lines = content.splitlines(keepends=True)

    insert_at = 0
    while insert_at < len(original_lines) and original_lines[insert_at].startswith("#!"):
        insert_at += 1

    block = "".join(f"{comment_prefix} {line}\n" for line in tree_lines) + "\n"
    updated = "".join(original_lines[:insert_at] + [block] + original_lines[insert_at:])
    subset_code.write_text(updated, encoding="utf-8")


def _dot_path_for_output(output: Path) -> Path:
    suffix = output.suffix.lower()
    if suffix in {".dot", ".png", ".svg", ".pdf"}:
        return output.with_suffix(".dot")
    return output.with_name(output.name + ".dot")


_SUBSET_CODE_AUTO = object()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="callgraphtool",
        description=(
            "Generate a static call graph for a function using koknat/callGraph (or emit a subset-code file)."
        ),
    )
    parser.add_argument("folder", type=Path, help="Folder to scan for source files.")
    parser.add_argument(
        "function",
        help="Starting function name (passed to callGraph -start). You can disambiguate with <file>:<function>.",
    )
    parser.add_argument(
        "-l",
        "--language",
        help="Language code for callGraph (-language). If omitted, tries to infer from file extensions.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path. Extension controls format (.png/.svg/.pdf/.dot).",
    )
    parser.add_argument(
        "--subset-code",
        "--prompt-out",
        dest="subset_code",
        nargs="?",
        const=_SUBSET_CODE_AUTO,
        type=str,
        help=(
            "Write a subset source file containing only the functions included in the graph "
            "(callGraph -writeSubsetCode). If omitted, defaults to results/subset_<function>.<ext>."
        ),
    )
    parser.add_argument(
        "--callgraph-bin",
        help="Path to the callGraph script/binary. Defaults to the vendored copy or PATH.",
    )
    parser.add_argument(
        "--full-path",
        action="store_true",
        help="Pass -fullPath to callGraph (do not strip input paths).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Allow callGraph to open the generated image (by default it is suppressed).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    folder: Path = args.folder
    if not folder.exists():
        print(f"ERROR: folder not found: {folder}", file=sys.stderr)
        return 2
    if not folder.is_dir():
        print(f"ERROR: not a folder: {folder}", file=sys.stderr)
        return 2

    callgraph_bin = _resolve_callgraph_bin(args.callgraph_bin)
    if not callgraph_bin:
        vendored = _vendored_callgraph_path()
        print(
            "ERROR: could not find `callGraph`.\n"
            f"- Looked for vendored copy at: {vendored}\n"
            "- Looked for `callGraph` in PATH\n"
            "- You can also set CALLGRAPH_BIN or pass --callgraph-bin\n",
            file=sys.stderr,
        )
        return 2

    start_selector, start_label = _start_selector(folder, args.function)
    language = _normalize_language(args.language) or _infer_language(folder) or "py"
    subset_code: Path | None
    if args.subset_code is _SUBSET_CODE_AUTO:
        subset_code = _default_subset_code_path(start_label, language)
    elif args.subset_code:
        subset_code = Path(args.subset_code)
    else:
        subset_code = None
    if subset_code:
        subset_code.parent.mkdir(parents=True, exist_ok=True)

    temp_output_dir: tempfile.TemporaryDirectory[str] | None = None
    output_is_user_requested = args.output is not None
    if args.output:
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
    elif subset_code:
        temp_output_dir = tempfile.TemporaryDirectory(prefix="callgraphtool_")
        output = Path(temp_output_dir.name) / "callgraph.dot"
    else:
        output = _default_output_path(start_label)
        output.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    local_perl5lib = _project_local_perl5lib()
    if local_perl5lib.exists():
        env["PERL5LIB"] = f"{local_perl5lib}{os.pathsep}{env.get('PERL5LIB', '')}".rstrip(os.pathsep)

    callgraph_bin_path = Path(callgraph_bin)
    cmd: list[str] = []
    if callgraph_bin_path.exists() and not os.access(callgraph_bin_path, os.X_OK):
        cmd.extend(["perl", str(callgraph_bin_path)])
    else:
        cmd.append(callgraph_bin)
    cmd.extend(
        [
            str(folder),
            "-language",
            language,
            "-start",
            start_selector,
            "-output",
            str(output),
        ]
    )
    if subset_code:
        cmd.extend(["-writeSubsetCode", str(subset_code)])
    if args.full_path:
        cmd.append("-fullPath")
    if not args.show:
        cmd.append("-noShow")

    try:
        result = subprocess.run(cmd, text=True, capture_output=True, env=env)
        if result.returncode != 0:
            if result.stdout:
                sys.stdout.write(result.stdout)
            if result.stderr:
                sys.stderr.write(result.stderr)
            return result.returncode

        dot_path = _dot_path_for_output(output)
        if subset_code and subset_code.exists():
            try:
                if dot_path.exists():
                    dot_text = dot_path.read_text(encoding="utf-8", errors="replace")
                    subset_text = subset_code.read_text(encoding="utf-8", errors="replace")
                    tree_lines = _dot_to_call_tree(dot_text, subset_text, folder)
                    _prepend_tree_to_subset_file(subset_code, language, tree_lines)
            except Exception as exc:
                print(f"WARNING: failed to generate call tree header: {exc}", file=sys.stderr)

        if output.suffix.lower() != ".dot":
            try:
                dot_path.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                print(f"WARNING: failed to remove intermediate dot file {dot_path}: {exc}", file=sys.stderr)
    finally:
        if temp_output_dir is not None:
            temp_output_dir.cleanup()

    printed_any = False
    if subset_code and subset_code.exists():
        print(str(subset_code))
        printed_any = True
    if output_is_user_requested and output.exists():
        print(str(output))
        printed_any = True
    if not printed_any and output.exists():
        print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
