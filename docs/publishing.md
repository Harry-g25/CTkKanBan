# Publishing

Before the first upload, confirm that the repository has a protected GitHub
environment named `pypi`. In PyPI, configure a pending or trusted publisher for
this repository, `.github/workflows/publish.yml`, and the `pypi` environment.
The PyPI project may not exist until that one-time setup is completed.

For each release:

1. Confirm `ctk_kanban/version.py` and `CHANGELOG.md` contain the release version.
2. Run `tox`, build the distributions, and verify `python example.py` starts.
3. Commit and push the release changes to `main`, then wait for CI to pass.
4. Create and publish a GitHub release from `main` with a tag matching the
   package version, such as `2.0.1` or `v2.0.1`.
5. Publishing the GitHub release triggers the PyPI workflow, which tests,
   builds, checks, and uploads the distributions through trusted publishing.

If a release event was missed, open **Actions → Publish to PyPI → Run
workflow** on `main` and enter the existing release tag. The manual path checks
that the tag exists, is contained in `main`, and matches the package version
before it can publish.

The PyPI project name remains `CTkKanBan`; the Python import is `ctk_kanban`.
