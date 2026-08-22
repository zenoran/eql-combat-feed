# Contributing

- Target Python 3.12 or newer.
- Keep log parsing, combat aggregation, and Qt rendering separate.
- Add parser fixtures for every new combat-log pattern.
- Keep the normal overlay glanceable; detail belongs on hover or in diagnostics.
- Run `uv run pytest` and `uv run ruff check .` before committing.
- Do not commit EverQuest logs, account names, local paths, or generated builds.
