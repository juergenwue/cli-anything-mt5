# Releasing `cli-anything-mt5`

One-time steps for publishing a new version to PyPI and registering it
with the HKUDS/CLI-Anything registry.

## 1. Version bump

Update the version in exactly one place:

- `pyproject.toml` → `project.version`

If the change is user-visible, also bump `registry-entry.json` → `version`.

## 2. Green tests

```bash
pip install -e ".[dev]"
pytest tests/test_core.py -v       # must be 28/28 green
MT5_E2E=1 pytest tests/test_full_e2e.py -v   # only if a VM is reachable
```

## 3. Build artefacts

```bash
pip install --upgrade build twine
rm -rf dist/
python -m build
twine check dist/*
```

## 4. Publish

```bash
# TestPyPI first:
twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ cli-anything-mt5

# Production:
twine upload dist/*
```

## 5. Git tag

```bash
git tag -a v0.1.0 -m "v0.1.0: initial MT5 harness (10 commands)"
git push --tags
```

## 6. Registry PR

Fork [`HKUDS/CLI-Anything`](https://github.com/HKUDS/CLI-Anything), add
the contents of `registry-entry.json` to `registry.json` under the
`trading` category, and open a PR titled
`Add cli-anything-mt5 to trading category`.
