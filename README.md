# CallGraphTool

Small wrapper around koknat/callGraph to generate static call graphs.

## Setup

Initialize the bundled `callGraph` submodule:

```bash
git submodule update --init --recursive
```

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

By default, outputs are written to `results/` in this repo.

Override the language and output path:

```bash
callgraphtool path/to/project my_function --language py --output callgraph.svg
```
