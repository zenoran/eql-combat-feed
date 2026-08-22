# Repository instructions

## Scope

EQL Combat Feed is a local, log-driven EverQuest Legends overlay built with
Python 3.12 and PySide6. It must not inject into the game, read process memory,
or transmit gameplay logs.

## Architecture

Keep these concerns separate:

1. Log discovery and incremental tailing
2. EQL combat-line parsing
3. Combat-beat aggregation
4. Qt rendering and animation
5. User configuration and packaging

Parsing and aggregation must remain usable without importing PySide6 so they
can be tested headlessly.

## Development

- Stay on `main`.
- Use `uv` for dependency management.
- Run `uv run pytest` and `uv run ruff check .` after behavior changes.
- Add log fixtures for new parser patterns, with character/account names removed.
- Never commit actual EverQuest logs, local paths, credentials, or generated builds.
- Keep the default overlay compact: visual summaries first, details on hover.

## Git

Do not force-push, amend published commits, bypass hooks, or discard another
contributor's working-tree changes.
