"""Check documentation links, release identity, and referenced public APIs."""

from __future__ import annotations

import ast
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MARKDOWN_LINK = re.compile(r"!?\[[^]]*]\((?P<target><[^>]+>|[^)\s]+)")
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
MISSING = object()


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
        for name in ("href", "src"):
            value = values.get(name)
            if value:
                self.links.append(value)


def is_external(raw_link: str) -> bool:
    link = urlsplit(raw_link)
    return bool(link.scheme or link.netloc)


def check_html_links(failures: list[str]) -> int:
    parsers: dict[Path, LinkParser] = {}
    for path in sorted(DOCS.rglob("*.html")):
        parser = LinkParser()
        parser.feed(path.read_text(encoding="utf-8"))
        parsers[path.resolve()] = parser

    link_count = 0
    for source, parser in parsers.items():
        for raw_link in parser.links:
            link_count += 1
            if is_external(raw_link):
                continue
            link = urlsplit(raw_link)
            if link.path.startswith("/"):
                failures.append(f"{source.relative_to(ROOT)} uses a Pages-unsafe root link: {raw_link}")
                continue
            target = (source.parent / unquote(link.path)).resolve() if link.path else source
            if not target.is_relative_to(DOCS.resolve()):
                failures.append(f"{source.relative_to(ROOT)} links outside docs: {raw_link}")
                continue
            if not target.exists():
                failures.append(f"{source.relative_to(ROOT)} has a missing local target: {raw_link}")
                continue
            if link.fragment and target.suffix.lower() == ".html":
                target_parser = parsers.get(target)
                if target_parser is None or link.fragment not in target_parser.ids:
                    failures.append(f"{source.relative_to(ROOT)} has a missing fragment target: {raw_link}")
    return link_count


def check_markdown_links(failures: list[str]) -> int:
    paths = sorted(ROOT.glob("*.md")) + sorted(DOCS.rglob("*.md"))
    link_count = 0
    for source in paths:
        for match in MARKDOWN_LINK.finditer(source.read_text(encoding="utf-8")):
            link_count += 1
            raw_link = match.group("target").strip("<>")
            if is_external(raw_link) or raw_link.startswith("#"):
                continue
            if source == ROOT / "README.md":
                failures.append(f"README.md has a relative link that will not be PyPI-safe: {raw_link}")
                continue
            link = urlsplit(raw_link)
            if link.path.startswith("/"):
                failures.append(f"{source.relative_to(ROOT)} uses a root-relative link: {raw_link}")
                continue
            target = (source.parent / unquote(link.path)).resolve()
            if not target.is_relative_to(ROOT) or not target.exists():
                failures.append(f"{source.relative_to(ROOT)} has a missing local target: {raw_link}")
    return link_count


def literal_value(node: ast.expr | None) -> Any:
    if node is None:
        return MISSING
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return MISSING


def board_api() -> tuple[dict[str, Any], set[str]]:
    tree = ast.parse((ROOT / "ctk_kanban" / "board.py").read_text(encoding="utf-8"))
    board = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CTkKanbanBoard"
    )
    constructor = next(
        node
        for node in board.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__"
    )
    positional = [*constructor.args.posonlyargs, *constructor.args.args]
    positional_defaults = [None] * (len(positional) - len(constructor.args.defaults)) + list(
        constructor.args.defaults
    )
    defaults = {
        argument.arg: literal_value(default)
        for argument, default in zip(positional, positional_defaults, strict=True)
        if argument.arg != "self"
    }
    defaults.update(
        {
            argument.arg: literal_value(default)
            for argument, default in zip(
                constructor.args.kwonlyargs,
                constructor.args.kw_defaults,
                strict=True,
            )
        }
    )
    methods = {
        node.name
        for node in board.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }
    for module_name, class_name in (("rendering.py", "RenderingMixin"), ("drag.py", "DragDropMixin")):
        mixin_tree = ast.parse((ROOT / "ctk_kanban" / module_name).read_text(encoding="utf-8"))
        mixin = next(
            node
            for node in mixin_tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        methods.update(
            node.name
            for node in mixin.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
        )
    return defaults, methods


def section(document: str, section_id: str) -> str:
    match = re.search(
        rf'<section\b[^>]*\bid="{re.escape(section_id)}"[^>]*>(.*?)</section>',
        document,
        re.DOTALL,
    )
    if match is None:
        raise ValueError(f"docs/index.html is missing #{section_id}")
    return match.group(1)


def check_api_references(document: str, failures: list[str]) -> tuple[int, int, int, int]:
    defaults, methods = board_api()
    constructor_docs = section(document, "api-constructor")
    method_docs = section(document, "api-board-methods")

    row_pattern = re.compile(
        r"<tr>\s*<td><code>([a-z][a-z0-9_]*)</code></td>\s*<td>(.*?)</td>",
        re.DOTALL,
    )
    documented_parameters: set[str] = set()
    for name, default_cell in row_pattern.findall(constructor_docs):
        documented_parameters.add(name)
        if name not in defaults:
            failures.append(f"Constructor documentation references unknown parameter: {name}")
            continue
        text = unescape(re.sub(r"<[^>]+>", "", default_cell)).strip()
        try:
            documented_default = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            continue
        actual_default = defaults[name]
        if actual_default is not MISSING and documented_default != actual_default:
            failures.append(
                f"Constructor default drift for {name}: docs={documented_default!r}, code={actual_default!r}"
            )

    documented_methods = set(
        re.findall(r'class="signature">\s*([a-z][a-z0-9_]*)\s*\(', method_docs)
    )
    for name in sorted(documented_methods - methods):
        failures.append(f"Board-method documentation references unknown method: {name}")

    if (documented_parameters != set(defaults) or documented_methods != methods) and "help(CTkKanbanBoard)" not in document:
        failures.append("Partial API tables must point readers to help(CTkKanbanBoard) for the full live API")
    return len(documented_parameters), len(defaults), len(documented_methods), len(methods)


def check_release_docs(document: str, failures: list[str]) -> None:
    version_file = (ROOT / "ctk_kanban" / "version.py").read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(version_file)
    if match is None:
        failures.append("Could not read ctk_kanban/version.py")
        return
    version = match.group(1)
    if f'<span class="nav-version">v{version} Docs</span>' not in document:
        failures.append(f"docs/index.html version badge does not match package version {version}")
    if '<span id="install-command">python -m pip install CTkKanBan</span>' not in document:
        failures.append("The documentation hero must show the installable PyPI command")


def main() -> None:
    index = DOCS / "index.html"
    document = index.read_text(encoding="utf-8")
    failures: list[str] = []
    html_links = check_html_links(failures)
    markdown_links = check_markdown_links(failures)
    check_release_docs(document, failures)
    parameter_count, total_parameters, method_count, total_methods = check_api_references(document, failures)
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"Checked {html_links + markdown_links} documentation links and assets; "
        f"validated {parameter_count}/{total_parameters} constructor parameters and "
        f"{method_count}/{total_methods} public board methods"
    )


if __name__ == "__main__":
    main()
