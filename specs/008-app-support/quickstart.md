# Quickstart: validating feature 008

No pedal is needed for any step.

## 1. Hardware-free suite (the milestone gate)

```bash
uv sync
uv run ruff check
uv run ruff format --check
uv run mypy src
uv run pytest
```

Expected: all green. New files: `tests/unit/test_panel.py`, `tests/unit/test_preset_positions.py`,
`tests/unit/test_simulated_build.py`, `tests/integration/test_simulated_pedal.py`,
`tests/integration/test_example_simulated_pedal.py`,
`tests/contract/test_changelog_070.py`.

## 2. The three additions with public imports only

```bash
uv run python docs/examples/simulated_pedal.py
```

Expected: the script builds a simulated pedal from
`captures/fw96/20261116-probe-connect.jsonl`, prints the panel in order (MASTER first, D/AMP
last), edits two fields, selects 2C with `preset_index("2C")`, takes a backup, saves and restores,
and ends with the number of frames sent. It imports only from `openvave` and `openvave.protocol`.
Contract: [contracts/library-api.md](contracts/library-api.md).

## 3. Release checks

```bash
uv run openvave --version                      # openvave 0.7.0
section() { awk '/^## \[0\.6\.0\]/{on=1} /^## \[0\.5\.0\]/{on=0} on'; }
diff <(git show 61fdf6a:CHANGELOG.md | section) <(section < CHANGELOG.md) && echo "0.6.0 unchanged"
git diff --stat origin/main -- src/openvave/cli src/openvave/mcp_server   # no output: CLI and MCP untouched
```

## 4. After the merge (owner)

```bash
git tag v0.7.0 <merge commit> && git push origin v0.7.0
uv run --with "openvave @ git+https://github.com/gustavolima00/openvave@v0.7.0" \
  python -c "import openvave; print(openvave.__version__)"   # 0.7.0
```
