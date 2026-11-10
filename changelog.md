# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Configurable model via the `ANTHROPIC_MODEL` environment variable (defaults to the latest Haiku).
- `.env` support: environment variables are now loaded from a `.env` file at startup (`python-dotenv`).
- `.env.example` documenting the expected environment variables (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`).
- `requirements.txt` listing project dependencies.

### Changed
- `.gitignore` now ignores `.env` to keep secrets out of version control.
