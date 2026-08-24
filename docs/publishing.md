# Publishing CTkKanban

This is the maintainer runbook for producing a release through GitHub Actions
and PyPI trusted publishing. Users install the distribution named
`CTkKanBan`; Python code imports the lowercase package `ctk_kanban`.

## One-time setup

1. Create a protected GitHub environment named `pypi`. Add required reviewers
   if the repository's release policy calls for a manual publish approval.
2. In PyPI, configure a pending or trusted publisher for this GitHub repository
   with workflow `.github/workflows/publish.yml` and environment `pypi`.
3. Ensure the default branch is `main` and the publish workflow has
   `id-token: write` only in its environment-protected publish job.
4. Confirm maintainers who create releases can push tags and publish GitHub
   releases. No long-lived PyPI API token is required or expected.

The PyPI project might not exist until its first trusted-publisher release. The
repository workflow uses the project URL
`https://pypi.org/project/CTkKanBan/` after publication.

## Prepare a release

1. Choose the version and update `ctk_kanban/version.py`.
2. Move the appropriate entries from `CHANGELOG.md`'s `Unreleased` section to
   a dated version heading. Keep remaining unreleased work under a fresh
   `Unreleased` heading.
3. Check that the README, `docs/index.html`, examples, type declarations, and
   migration notes describe the code being released.
4. Install the development extras in a supported Python environment:

   ```bash
   python -m pip install -e ".[dev]"
   ```

5. Run the same core validation performed by CI:

   ```bash
   python -m pytest -q
   python -m ruff check ctk_kanban tests scripts example.py examples
   python -m mypy ctk_kanban
   python -m build
   python -m twine check dist/*
   ```

   CI installs an allowed CustomTkinter release, while its compatibility job
   pins the minimum. Before a release, reproduce both dependency edges:

   ```bash
   python -m pip install "customtkinter==6.0.0"
   python -m pytest -q
   python -m pip install --upgrade "customtkinter>=6.0.0,<7"
   python -m pytest -q
   ```

   On Linux without a display, run GUI tests under Xvfb, for example
   `xvfb-run -a python -m pytest -q`. `tox` is a convenient alternative for
   the test and quality environments.

6. Install the newly built wheel without dependencies and smoke-test it from a
   directory outside the repository so the source tree cannot mask packaging
   omissions:

   ```bash
   python -m pip install --force-reinstall --no-deps dist/*.whl
   python -c "import ctk_kanban; print(ctk_kanban.__version__)"
   ```

7. Start `python example.py` and the focused programs in `examples/`. Manually
   verify board creation, editing, dragging, deletion configuration, custom and
   built-in editors, database mappings, async loading, and both appearance modes.
8. Review the diff, commit the release preparation, push it to `main`, and wait
   for required CI checks to pass.

Build artifacts in `dist/` are local outputs and must not be committed.

## Publish through a GitHub release

1. Create a GitHub release targeting the validated commit on `main`.
2. Use a tag that exactly matches `ctk_kanban.__version__`, with an optional
   leading `v` (for example `2.3.0` or `v2.3.0`).
3. Use the matching changelog section as the release notes and publish the
   release. A draft does not trigger publishing.
4. Publishing triggers the `Publish to PyPI` workflow. Prereleases are
   intentionally skipped by its build job.
5. The workflow checks out the tag, verifies that it exists and is contained
   in `origin/main`, compares the tag to the imported package version, runs
   tests/lint/types, builds and checks distributions, installs the wheel for a
   smoke test, and uploads the build artifact.
6. The environment-protected publish job downloads that exact artifact and
   uploads it to PyPI with OpenID Connect trusted publishing.
7. After success, verify the version and metadata on PyPI, then install it in a
   clean environment with `python -m pip install --upgrade CTkKanBan`.

Do not rebuild or manually upload different files after the workflow's build
job. PyPI releases are immutable, so a broken artifact requires a new version.
Likewise, do not move a tag after publishing a GitHub release. If validation or
upload fails after the release is visible, fix the problem and increment the
patch version for a new release commit and tag.

## Manual recovery for a missed release event

If the GitHub release exists but its event did not start the workflow, open
**Actions → Publish to PyPI → Run workflow** on `main` and enter the existing
release tag with or without its leading `v`.

The recovery path does not invent or move a tag. It verifies that the tag
exists, belongs to `main`, and matches the package version before following the
same build and protected publish jobs. Do not use it to publish an unreviewed
commit or to work around a failing validation check.

## Common failures

- **Tag/version mismatch:** update the package version and create a new correct
  tag/release. Do not retag a version that may already have been observed.
- **Tag is not contained in `main`:** merge or cherry-pick the release commit
  through the normal review path, then create a new release tag on `main`.
- **Trusted publisher rejected:** verify the PyPI owner/repository, workflow
  filename, GitHub environment, and environment approval state exactly.
- **PyPI says the version or filename already exists:** published artifacts
  cannot be replaced; fix the issue and increment the version.
- **Wheel smoke test imports the source tree:** repeat it from a temporary
  directory outside the checkout.
- **GUI tests fail on Linux:** confirm Xvfb is installed and the test command is
  wrapped with `xvfb-run -a`.
