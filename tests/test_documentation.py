"""Keep the hand-written guides aligned with the supported public surface."""

from __future__ import annotations

import inspect
import re
from dataclasses import fields as dataclass_fields
from html.parser import HTMLParser
from pathlib import Path
from typing import get_args

import ctk_kanban
from ctk_kanban import (
    DEFAULT_THEME,
    ActionConfig,
    BoardConfig,
    BoardModel,
    CTkKanbanBoard,
    FieldDefinition,
    FieldType,
    LayoutConfig,
    TextConfig,
)
from ctk_kanban.fields import CardRole

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
HTML = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
GUIDES = {"README.md": README, "docs/index.html": HTML}


class _BalancedHTMLParser(HTMLParser):
    """Small structural check for this static, explicitly closed HTML page."""

    _void_elements = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag not in self._void_elements:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack, f"unexpected closing HTML tag: {tag}"
        current = self.stack.pop()
        assert current == tag, (
            f"closed {tag} while {current} was open at line {self.getpos()[0]}"
        )


def _assert_documented(names: set[str]) -> None:
    for guide_name, source in GUIDES.items():
        missing = sorted(name for name in names if name not in source)
        assert not missing, f"{guide_name} is missing documentation for: {missing}"


def test_guides_cover_every_public_export_and_declared_method() -> None:
    names = set(ctk_kanban.__all__)
    for cls in (CTkKanbanBoard, BoardModel):
        names.update(
            name
            for name, value in cls.__dict__.items()
            if not name.startswith("_") and (callable(value) or isinstance(value, property))
        )
    names.update(inspect.signature(CTkKanbanBoard).parameters)
    _assert_documented(names)


def test_guides_cover_field_config_and_theme_contracts() -> None:
    names = {
        *get_args(FieldType),
        *get_args(CardRole),
        *FieldDefinition.__required_keys__,
        *FieldDefinition.__optional_keys__,
        *DEFAULT_THEME,
    }
    for cls in (ActionConfig, LayoutConfig, TextConfig, BoardConfig):
        names.update(field.name for field in dataclass_fields(cls))
    _assert_documented(names)


def test_guides_cover_events_structural_keys_and_default_text() -> None:
    names = {
        "card_added",
        "card_updated",
        "card_deleted",
        "card_moved",
        "column_added",
        "column_updated",
        "column_deleted",
        "column_moved",
        "fields_changed",
        "before",
        "data",
        "id",
        "column",
        "column_id",
    }
    names.update(
        str(getattr(TextConfig(), field.name)) for field in dataclass_fields(TextConfig)
    )
    _assert_documented(names)


def test_html_section_navigation_is_complete_and_unambiguous() -> None:
    all_ids = re.findall(r'\bid="([^"]+)"', HTML)
    assert len(all_ids) == len(set(all_ids)), "HTML IDs must be unique"

    section_ids = set(re.findall(r'<section\s+id="([^"]+)"', HTML))
    local_links = set(re.findall(r'href="#([^"]+)"', HTML))
    assert section_ids <= local_links, f"sections missing from navigation: {section_ids - local_links}"
    assert local_links <= set(all_ids), f"links point to missing IDs: {local_links - set(all_ids)}"


def test_html_elements_are_balanced() -> None:
    parser = _BalancedHTMLParser()
    parser.feed(HTML)
    parser.close()
    assert not parser.stack, f"unclosed HTML tags: {parser.stack}"


def test_readme_local_links_resolve() -> None:
    targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", README)
    local_paths = {
        target.split("#", 1)[0]
        for target in targets
        if not target.startswith(("#", "http://", "https://"))
    }
    missing = sorted(path for path in local_paths if not (ROOT / path).exists())
    assert not missing, f"README links point to missing paths: {missing}"


def test_guides_do_not_repeat_superseded_field_claims_or_mojibake() -> None:
    stale_claims = {
        "Version 2 removes the 1.x field-definition",
        "cards reject unknown fields",
        "four fixed card fields only",
    }
    for guide_name, source in GUIDES.items():
        found = sorted(claim for claim in stale_claims if claim in source)
        assert not found, f"{guide_name} contains superseded claims: {found}"
        assert "�" not in source, f"{guide_name} contains replacement characters"


def test_release_version_is_consistent_across_user_facing_docs() -> None:
    version = ctk_kanban.__version__
    assert f"## {version} - " in CHANGELOG
    assert f"v{version} Docs" in HTML
    assert f"CTkKanban {version} documentation" in HTML
