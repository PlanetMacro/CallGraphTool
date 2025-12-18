from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def _vendored_callgraph_path() -> Path:
    return Path(__file__).resolve().parents[2] / "third_party" / "callGraph" / "callGraph"


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="callgraphtool",
        description="Generate a static call graph for a function using koknat/callGraph.",
    )
    parser.add_argument("folder", type=Path, help="Folder to scan for source files.")
    parser.add_argument("function", help="Starting function name (passed to callGraph -start).")
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
        "--callgraph-bin",
        help="Path to the callGraph script/binary. Defaults to vendored submodule or PATH.",
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
            f"- Looked for vendored submodule at: {vendored}\n"
            "- Looked for `callGraph` in PATH\n"
            "- You can also set CALLGRAPH_BIN or pass --callgraph-bin\n",
            file=sys.stderr,
        )
        return 2

    start = _normalize_start(args.function)
    language = _normalize_language(args.language) or _infer_language(folder) or "py"
    output = args.output or _default_output_path(start)
    output.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    local_perl5lib = _project_local_perl5lib()
    if local_perl5lib.exists():
        env["PERL5LIB"] = f"{local_perl5lib}{os.pathsep}{env.get('PERL5LIB', '')}".rstrip(os.pathsep)

    cmd: list[str] = [
        callgraph_bin,
        str(folder),
        "-language",
        language,
        "-start",
        start,
        "-output",
        str(output),
    ]
    if args.full_path:
        cmd.append("-fullPath")
    if not args.show:
        cmd.append("-noShow")

    result = subprocess.run(cmd, text=True, capture_output=True, env=env)
    if result.returncode != 0:
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
        return result.returncode

    if output.exists():
        print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
