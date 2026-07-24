"""Regression tests for release-script argument handling."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_release import update_docs_version
from scripts.verify_release import SDIST_REQUIRED_SUFFIXES, parse_args, validate_sdist


class ReleaseValidationTests(unittest.TestCase):
    def test_github_branch_name_is_not_inferred_as_release_tag(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REF_NAME": "main"}):
            self.assertIsNone(parse_args([]).tag)

    def test_explicit_release_tag_is_preserved(self) -> None:
        self.assertEqual(parse_args(["--tag", "v0.2.0"]).tag, "v0.2.0")

    def test_release_preparation_updates_the_documentation_version(self) -> None:
        document = '<span class="nav-version">v0.2.0 Docs</span>'

        updated = update_docs_version(document, "0.3.0")

        self.assertEqual(updated, '<span class="nav-version">v0.3.0 Docs</span>')

    def test_release_preparation_requires_one_documentation_version_badge(self) -> None:
        with self.assertRaisesRegex(ValueError, "version badge"):
            update_docs_version("<html></html>", "0.3.0")

        duplicate = '<span class="nav-version">v0.1.0 Docs</span>' * 2
        with self.assertRaisesRegex(ValueError, "version badge"):
            update_docs_version(duplicate, "0.3.0")

    def test_source_distribution_requires_the_shared_gui_test_helper(self) -> None:
        helper = "tests/gui_test_app.py"
        names = [f"ctk_kanban-0.2.0/{suffix}" for suffix in sorted(SDIST_REQUIRED_SUFFIXES - {helper})]

        with patch("scripts.verify_release.tarfile.open") as open_archive:
            open_archive.return_value.__enter__.return_value.getnames.return_value = names
            with self.assertRaisesRegex(ValueError, "tests/gui_test_app.py"):
                validate_sdist(Path("ctk_kanban-0.2.0.tar.gz"), "0.2.0")


if __name__ == "__main__":
    unittest.main()
