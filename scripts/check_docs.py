"""Check local assets and fragment links in the static documentation."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


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


def main() -> None:
    index = DOCS / "index.html"
    parser = LinkParser()
    parser.feed(index.read_text(encoding="utf-8"))
    failures: list[str] = []
    for raw_link in parser.links:
        link = urlsplit(raw_link)
        if link.scheme or link.netloc or raw_link.startswith(("mailto:", "tel:")):
            continue
        if link.path:
            target = DOCS / unquote(link.path.lstrip("/"))
            if not target.exists():
                failures.append(f"Missing local target: {raw_link}")
        if link.fragment and link.fragment not in parser.ids:
            failures.append(f"Missing fragment target: #{link.fragment}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Checked {len(parser.links)} documentation links and assets")


if __name__ == "__main__":
    main()

