# Active Context

## Current Focus
Optimization of deployment process and Docker build efficiency.

## Key Implementation Details
- Streamlined Docker build process by removing unnecessary package installation
- Enhanced deploy.sh with comprehensive visual feedback and timing information
- Eliminated verbose log output from deployment tools (tar warnings, logrotate debug)
- Maintained robust error handling while improving user experience

## Recent Changes (2025-11-12)
- **Docker Optimization**: Removed redundant `pip install -e .` step, using direct PYTHONPATH approach
- **Deployment Visual Enhancement**: Added ANSI colors, section timing, and progress indicators
- **Log Cleanup**: Suppressed macOS tar extended attributes warnings and logrotate debug output
- **Build Efficiency**: Separated dependency installation from package installation for better caching
- Dependencies now declared in `pyproject.toml`; removed `requirements.txt`
- Dockerfile installs the package via `pip install .` and runs the new module entrypoint
- Deployment script packages `src/`, `pyproject.toml`, and supporting assets
- Unit test suite updated to new import paths; all 93 tests pass locally
- Added `link` field to Setting model for storing message links in separate Google Sheets column
- Links now appear in dedicated column instead of being appended to error column
- Success timestamps now use Moscow timezone (Europe/Moscow) to match cron schedule timezone
- Added backward compatibility test for loading settings with fewer columns than model fields
