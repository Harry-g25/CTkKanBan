# Contributing

1. Create a virtual environment with Python 3.10 or newer.
2. Install the project with `python -m pip install -e ".[dev]"`.
3. Keep model changes independent from Tk and keep gestures attached to explicit controls.
4. Add focused tests for user-visible behavior.
5. Run `tox` before opening a pull request.

Avoid adding persistence, networking, generated forms, or application-specific workflow logic to the widget. User-visible changes belong under `## Unreleased` in `CHANGELOG.md`.
