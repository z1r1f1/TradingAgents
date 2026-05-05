# Repository Guidelines

## Project Structure & Module Organization

TradingAgents is a Python package for multi-agent financial analysis. Core library code lives in `tradingagents/`: agent roles under `agents/`, data integrations under `dataflows/`, orchestration in `graph/`, provider adapters in `llm_clients/`, and shared helpers in `utils/`. The Typer/Rich command-line interface is in `cli/`, with static CLI text in `cli/static/`. Tests live in `tests/` and should mirror the behavior or module they cover. Documentation and screenshots are in `README.md`, `CHANGELOG.md`, and `assets/`. Runtime data and secrets belong in local `.env` files or user cache directories, not in source control.

## Build, Test, and Development Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install .
```
Installs the package and exposes the `tradingagents` console script.

```bash
tradingagents
python -m cli.main
```
Runs the interactive CLI from an installed package or directly from source.

```bash
pytest
pytest -m unit
pytest tests/test_safe_ticker_component.py
```
Runs all tests, a marker subset, or one focused test file. Docker users can run `docker compose run --rm tradingagents`; use the `ollama` profile for local models.

## Coding Style & Naming Conventions

Use Python 3.10+ syntax and follow PEP 8 with 4-space indentation. Prefer descriptive snake_case for functions, variables, and modules; use PascalCase for classes. Keep provider-specific logic isolated in `tradingagents/llm_clients/` or configuration helpers rather than spreading conditionals through agents. Avoid committing generated caches, local checkpoints, `.env`, or `.pyc` files.

## Testing Guidelines

Pytest is configured in `pyproject.toml` with strict markers: `unit`, `integration`, and `smoke`. Name tests `test_*.py` and write focused assertions around public behavior, CLI defaults, provider validation, checkpointing, and safety boundaries. Mark external-service tests as `integration` and keep unit tests deterministic by mocking network or LLM calls.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style prefixes such as `feat:`, `fix:`, `fix(security):`, and `chore:`. Keep the subject concise and explain user impact. Pull requests should include a short description, linked issue when applicable, test evidence (`pytest`, focused tests, or Docker smoke run), and screenshots for CLI/UI changes. Call out configuration, migration, or security implications explicitly.

## Security & Configuration Tips

Copy `.env.example` or `.env.enterprise.example` locally and never commit real API keys. Validate ticker or user-provided path components before file access, and prefer existing cache/config helpers for paths under `~/.tradingagents/`.
