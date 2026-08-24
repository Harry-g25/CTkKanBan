"""Repeatable CTkKanban performance benchmark.

Run from the repository root with ``python -m scripts.benchmark_performance``.
The workload intentionally mixes rich-card rendering with common interactive
mutations. Timings are emitted as JSON so optimization passes can be compared
without parsing presentation text.
"""

from __future__ import annotations

import argparse
import gc
import json
import time
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from ctk_kanban import BoardConfig, CTkKanbanBoard, LayoutConfig
from ctk_kanban.model import BoardModel

# Captured before the second optimization pass on the same machine, Python,
# CustomTkinter version, dataset, and benchmark implementation.
BASELINE_MS = {
    "board_create_240_ms": 3055.3411,
    "board_move_100_ms": 1320.9512,
    "board_update_25_ms": 316.9860,
    "column_25_cycles_ms": 20.7805,
    "editor_10_cycles_ms": 1731.0166,
    "hover_5000_cycles_ms": 32.7679,
    "model_create_2000_ms": 14.6296,
    "model_move_500_ms": 3.0332,
    "model_snapshot_25_ms": 158.2271,
    "model_update_250_ms": 3.3399,
    "search_10_cycles_ms": 62.2658,
}


FIELDS = [
    {
        "key": "title",
        "label": "Title",
        "type": "text",
        "required": True,
        "show_on_card": True,
        "searchable": True,
        "card_role": "title",
    },
    {
        "key": "description",
        "label": "Description",
        "type": "textarea",
        "show_on_card": True,
        "searchable": True,
        "card_role": "body",
    },
    {
        "key": "client",
        "label": "Client",
        "type": "text",
        "show_on_card": True,
        "searchable": True,
        "card_role": "metadata",
    },
    {
        "key": "stage",
        "label": "Stage",
        "type": "select",
        "options": ["Discovery", "Delivery", "Review"],
        "show_on_card": True,
        "searchable": True,
        "card_role": "badge",
    },
    {
        "key": "estimate",
        "label": "Estimate",
        "type": "integer",
        "show_on_card": True,
        "card_role": "metadata",
    },
    {
        "key": "owners",
        "label": "Owners",
        "type": "multiselect",
        "options": ["Avery", "Harry", "Morgan", "Sam"],
        "show_on_card": True,
        "searchable": True,
        "card_role": "metadata",
    },
    {
        "key": "tags",
        "label": "Tags",
        "type": "tags",
        "show_on_card": True,
        "searchable": True,
        "card_role": "tags",
    },
]


def dataset(column_count: int, card_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    columns = [
        {"id": f"column-{index}", "title": f"Column {index}"}
        for index in range(column_count)
    ]
    cards = [
        {
            "id": index,
            "column": f"column-{index % column_count}",
            "title": f"Deliver benchmark item {index}",
            "description": "Profile rendering, searching, moving, and updating rich cards.",
            "client": f"Client {index % 17}",
            "stage": ("Discovery", "Delivery", "Review")[index % 3],
            "estimate": index % 13,
            "owners": ["Harry", "Morgan"],
            "tags": ["performance", f"batch-{index % 11}"],
        }
        for index in range(card_count)
    ]
    return columns, cards


def milliseconds(callback: Callable[[], Any]) -> float:
    start = time.perf_counter()
    callback()
    return (time.perf_counter() - start) * 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit unsuccessfully if any workload is less than 2x faster",
    )
    arguments = parser.parse_args()
    columns, cards = dataset(12, 240)
    model_columns, model_cards = dataset(20, 2_000)
    results: dict[str, float] = {}

    # Prime CPython's adaptive bytecode on a tiny sample and start the timed
    # workload from a known GC state. Without this, a single-digit-millisecond
    # result can vary by 50% based solely on how this module was launched.
    BoardModel(model_columns, model_cards[:20], fields=FIELDS)
    gc.collect()
    model_box: list[BoardModel] = []
    results["model_create_2000_ms"] = milliseconds(
        lambda: model_box.append(BoardModel(model_columns, model_cards, fields=FIELDS))
    )
    model = model_box[0]
    results["model_snapshot_25_ms"] = milliseconds(
        lambda: [model.snapshot() for _ in range(25)]
    )
    results["model_update_250_ms"] = milliseconds(
        lambda: [model.update_card(0, {"estimate": index}) for index in range(250)]
    )
    results["model_move_500_ms"] = milliseconds(
        lambda: [model.move_card(0, f"column-{index % 20}") for index in range(500)]
    )

    root = ctk.CTk()
    root.geometry("1400x850")
    root.withdraw()
    config = BoardConfig(
        layout=LayoutConfig(
            show_toolbar=True,
            enable_drag=True,
            fill_columns=False,
            column_width=340,
            column_height=600,
        )
    )
    board_box: list[CTkKanbanBoard] = []

    def create_board() -> None:
        board = CTkKanbanBoard(
            root,
            columns=columns,
            cards=cards,
            fields=FIELDS,
            config=config,
        )
        board.pack(fill="both", expand=True)
        root.update_idletasks()
        board_box.append(board)

    results["board_create_240_ms"] = milliseconds(create_board)
    board = board_box[0]

    results["board_update_25_ms"] = milliseconds(
        lambda: [board.update_card(0, {"estimate": index}) for index in range(25)]
    )
    results["board_move_100_ms"] = milliseconds(
        lambda: [board.move_card(0, f"column-{index % 12}") for index in range(100)]
    )

    def search_cycles() -> None:
        for _ in range(10):
            board.search("client 4")
            board.search("")

    results["search_10_cycles_ms"] = milliseconds(search_cycles)

    card = board._card_widget_cache[1]

    def hover_cycles() -> None:
        for _ in range(5_000):
            card._set_hovered(True)
            card._set_hovered(False)

    results["hover_5000_cycles_ms"] = milliseconds(hover_cycles)

    def column_cycles() -> None:
        for index in range(25):
            board.update_column("column-1", {"title": f"Renamed {index}"})
            board.move_column("column-1", 0 if index % 2 else 1)

    results["column_25_cycles_ms"] = milliseconds(column_cycles)
    root.update_idletasks()
    board.destroy()

    # The repository showcase has additional field types and is the user's
    # real manual test surface, so keep editor performance tied to that schema.
    import example as showcase

    showcase_board = CTkKanbanBoard(
        root,
        columns=showcase.COLUMNS,
        cards=showcase.CARDS,
        fields=showcase.FIELDS,
        config=showcase.CONFIG,
        theme=showcase.THEME,
    )

    def editor_cycles() -> None:
        for _ in range(10):
            showcase_board.open_edit_card_editor(101)
            if showcase_board._editor is not None:
                showcase_board._editor.destroy()

    results["editor_10_cycles_ms"] = milliseconds(editor_cycles)
    showcase_board.destroy()
    root.destroy()

    speedups = {
        name: BASELINE_MS[name] / duration for name, duration in results.items()
    }
    print(
        json.dumps(
            {
                "baseline_ms": BASELINE_MS,
                "optimized_ms": results,
                "speedup": speedups,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if arguments.check:
        failing = {name: ratio for name, ratio in speedups.items() if ratio < 2.0}
        if failing:
            names = ", ".join(f"{name}={ratio:.2f}x" for name, ratio in failing.items())
            raise SystemExit(f"performance target missed: {names}")


if __name__ == "__main__":
    main()
