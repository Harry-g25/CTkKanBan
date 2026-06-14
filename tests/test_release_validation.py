"""Regression tests for release-script argument handling."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts.verify_release import parse_args


class ReleaseValidationTests(unittest.TestCase):
    def test_github_branch_name_is_not_inferred_as_release_tag(self) -> None:
        with patch.dict(os.environ, {"GITHUB_REF_NAME": "main"}):
            self.assertIsNone(parse_args([]).tag)

    def test_explicit_release_tag_is_preserved(self) -> None:
        self.assertEqual(parse_args(["--tag", "v0.2.0"]).tag, "v0.2.0")


if __name__ == "__main__":
    unittest.main()
