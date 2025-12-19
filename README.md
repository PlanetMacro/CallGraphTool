# CallGraphTool

Small wrapper around koknat/callGraph to generate static call graphs (and subset-code “prompt” files).

## Setup

This repo includes a modified copy of `callGraph` (GPLv3) at `src/callgraphtool/callGraph` (see `LICENSE`).

Install system dependencies required by `callGraph` (Debian/Ubuntu):

```bash
sudo apt-get update
sudo apt-get install -y graphviz libgraphviz-perl
```

If you don't have `sudo`, you can install the Perl `GraphViz` module locally into `.perl5/`:

```bash
curl -L https://cpanmin.us -o /tmp/cpanm
perl /tmp/cpanm --local-lib-contained .perl5 GraphViz
```

Create and activate the virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the package in editable mode:

```bash
python -m pip install -e .
```

## Usage

Generate a call graph for a function within a folder (defaults to Python / `-language py`):

```bash
callgraphtool path/to/project my_function
```

If multiple functions share the same name, you can disambiguate the start function with:

```bash
callgraphtool path/to/project relative/path/to/file.rs:my_function
```

(`relative/path/to/file.rs` is relative to `path/to/project`; an absolute path also works.)

By default, outputs are written to `results/` in this repo.

Override the language and output path:

```bash
callgraphtool path/to/project my_function --language py --output callgraph.svg
```

Generate a subset-code file (all functions included in the call graph scope of the start function):

```bash
callgraphtool path/to/project my_function --subset-code
```

The subset-code file includes:

- An indented call tree at the top (as comments)
- `Source: <path>:<line> (<function>)` markers above each copied function

When generating `.png`/`.svg`/`.pdf` graphs, the intermediate `.dot` file is deleted (use `--output ... .dot` if you want to keep DOT).
