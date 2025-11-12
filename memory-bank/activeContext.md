# Active Context

## Current Focus
Codebase consolidation into a single `src/` package with clear module boundaries and centralized configuration for environment management.

## Key Implementation Details
- Created `src/` with dedicated subpackages: `core`, `messaging`, `infrastructure`, `monitoring`, `scheduling`, `utils`
- Split legacy `message_processor.py` into `messaging/orchestrator.py`, `messaging/sender.py`, and `messaging/error_handlers.py`
- Introduced `core/config.py` using `pydantic-settings` to load `.env` once and expose typed settings
- Updated entrypoints to run via `python -m src.cli`; reorganized tests under `tests/unit/` with shared fixtures

## Recent Changes (2025-11-12)
- Dependencies now declared in `pyproject.toml`; removed `requirements.txt`
- Dockerfile installs the package via `pip install .` and runs the new module entrypoint
- Deployment script packages `src/`, `pyproject.toml`, and supporting assets
- Unit test suite updated to new import paths; all 93 tests pass locally
