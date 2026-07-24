# Publishing CTkKanban

Releases are built once, validated, attested, published to PyPI with OpenID Connect, and attached to a GitHub release. No long-lived PyPI API token is stored in GitHub.

## One-time repository setup

1. In GitHub, create an environment named `pypi`. Add required reviewers and prevent self-review if another maintainer is available. Restrict deployment branches and tags to protected tags matching `v*`.
2. Create a second environment named `testpypi` with the same protections.
3. In PyPI, add a trusted publisher for owner `Harry-g25`, repository `CTkKanBan`, workflow `publish.yml`, environment `pypi`.
4. Because the project is not yet on PyPI, use PyPI's pending-publisher form to reserve `CTkKanBan` and create it on the first successful workflow run. The spelling and capitalization must match the project metadata exactly.
5. In TestPyPI, add a trusted publisher for workflow `test-publish.yml` and environment `testpypi`.
6. In GitHub Pages settings, choose GitHub Actions as the source.
7. Protect `main`. Require pull requests, resolved conversations, and the CI, installed-wheel, and CodeQL checks. Block force pushes and branch deletion.
8. Add a protected tag rule for `v*` so only maintainers can create release tags.

The publisher workflow names and environment names are identity fields. They must match exactly.

## Validate a candidate

Add user-facing changes under `## Unreleased` in `CHANGELOG.md`, then run:

```bash
python scripts/prepare_release.py 1.0.0
tox -e lint,type,package,py314,ctk-min,ctk-current
```

`prepare_release.py` updates the package, changelog, and visible documentation version together. Review all three changes before committing.

If a Windows checkout lives in a OneDrive-synced folder and tox reports `FailedToStart` while creating its packaging backend, keep tox's disposable environments outside the synced tree and rerun the command:

```powershell
$env:TOX_WORK_DIR = Join-Path $env:LOCALAPPDATA "ctk-kanban-tox"
tox -e lint,type,package,py314,ctk-min,ctk-current
```

Push the release-preparation commit and run **Publish to TestPyPI** manually. Test installation from TestPyPI in a clean environment:

```bash
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ CTkKanBan==1.0.0
```

The extra index supplies CustomTkinter if it is not mirrored on TestPyPI. Do not use this two-index command for production dependency resolution.

## Publish a production release

After CI is green on `main`, create and push the matching annotated tag:

```bash
git tag -a v1.0.0 -m "CTkKanban 1.0.0"
git push origin v1.0.0
```

`publish.yml` then:

1. Checks that the tag, package version, and dated changelog section agree.
2. Runs linting, core type checks, branch coverage, and tests against the minimum and current supported CustomTkinter releases.
3. Builds exactly one wheel and one source archive.
4. Checks metadata, archive safety, typing marker, Twine rendering, wheel contents, and Pyroma score.
5. Installs the exact wheel with normal dependency resolution, runs `pip check`, and smoke-tests its SQLite adapter.
6. Generates SHA-256 checksums and GitHub artifact attestations only after the wheel smoke test succeeds.
7. Publishes the same files to PyPI through trusted publishing.
8. Creates a GitHub release with generated notes and attaches the distributions and checksums.

PyPI releases are immutable. Never delete and reuse a version. If a release is wrong, fix it and publish a higher version.

## Recovery

If publishing fails before PyPI accepts the files, fix the workflow or environment and rerun the failed jobs. If PyPI accepted the package but the GitHub release failed, rerun only the failed `github-release` job. Do not recreate the tag or rebuild artifacts unnecessarily.

Verify provenance for a downloaded file with the GitHub CLI:

```bash
gh attestation verify ctk_kanban-1.0.0-py3-none-any.whl --repo Harry-g25/CTkKanBan
```
