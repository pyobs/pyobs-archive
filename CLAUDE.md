# CLAUDE.md

Entry points for working in this repo.

## What this is

`pyobs-archive` is a Django webservice archiving astronomical images. It implements most of the
[Las Cumbres Observatory archive interfaces](https://developers.lco.global/#archive), and can
optionally restrict frame access to project members via a `pyobs-portal` connection. Full
installation, configuration, architecture, and REST API reference live in
[`docs/source/`](docs/source/) (Sphinx — `cd docs && uv run --with sphinx --with sphinx-rtd-theme make html`).

## Design history and planning

This repo keeps its own implementation plans under `specs/plans/`; design docs and ADRs that
concern `pyobs-archive` (including cross-repo ones with `pyobs-portal`/`pyobs-core`) live in
`pyobs-core`'s `specs/` tree instead, tagged with a `Repos:` line — see `specs/index.md` for the
current list and `pyobs-core/CLAUDE.md`'s "Cross-repo docs" section for the convention.

## Tooling

- Backend: Django, managed via `uv`
- Tests: `uv run manage.py test`
- No ruff/black/pyrefly config in this repo yet (unlike most `pyobs-*` siblings)
