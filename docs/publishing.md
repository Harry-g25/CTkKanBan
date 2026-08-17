# Publishing

Before the first upload, confirm that the repository has a protected GitHub
environment named `pypi`. In PyPI, configure a pending or trusted publisher for
this repository, `.github/workflows/publish.yml`, and the `pypi` environment.
The PyPI project may not exist until that one-time setup is completed.

For each release:

1. Confirm `ctk_kanban/version.py` and `CHANGELOG.md` contain the release version.
2. Run `tox` and verify `python example.py` starts.
3. Commit the release and create a matching tag such as `v2.0.0` from `main`.
4. Push the tag. The publish workflow tests, builds, checks, and uploads the distributions through PyPI trusted publishing.

The PyPI project name remains `CTkKanBan`; the Python import is `ctk_kanban`.
