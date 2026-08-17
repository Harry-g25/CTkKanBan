"""Column widget for the simplified Kanban board."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Mapping

import customtkinter as ctk

from ._scrolling import ManagedScrollableFrame
from .card import CTkKanbanCard


class CTkKanbanColumn(ctk.CTkFrame):
    """A fixed-width column with a vertically scrollable card list."""

    def __init__(
        self,
        master: Any,
        column: Mapping[str, Any],
        theme: Mapping[str, Any],
        *,
        width: int = 288,
        height: int = 600,
        on_add: Callable[[Any], None] | None = None,
        on_menu: Callable[[Any, Any], None] | None = None,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color=theme["column_fg_color"],
            border_color=theme["column_border_color"],
            border_width=1,
        )
        self.grid_propagate(False)
        self.column = dict(column)
        self.column_id = self.column["id"]
        self.theme = dict(theme)
        self.card_widgets: list[CTkKanbanCard] = []
        self._drop_active = False
        self._drop_index: int | None = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            header,
            text=str(self.column["title"]),
            anchor="w",
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, sticky="ew")

        self.count_label = ctk.CTkLabel(
            header,
            text="0",
            width=28,
            height=24,
            corner_radius=8,
            fg_color=self.theme["count_fg_color"],
            text_color=self.theme["muted_text_color"],
        )
        self.count_label.grid(row=0, column=1, padx=(6, 4))

        add_button = ctk.CTkButton(
            header,
            text="+",
            width=30,
            height=28,
            command=lambda: on_add(self.column_id) if on_add is not None else None,
        )
        add_button.grid(row=0, column=2, padx=2)

        self.menu_button: ctk.CTkButton = ctk.CTkButton(
            header,
            text="...",
            width=30,
            height=28,
            fg_color="transparent",
            hover_color=self.theme["control_hover_color"],
            text_color=self.theme["text_color"],
        )
        if on_menu is not None:
            self.menu_button.configure(command=lambda: on_menu(self.column_id, self.menu_button))
        self.menu_button.grid(row=0, column=3, padx=(2, 0))

        self.body: Any = ManagedScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=self.theme["scrollbar_color"],
            scrollbar_button_hover_color=self.theme["scrollbar_hover_color"],
        )
        self.body.grid(row=1, column=0, padx=7, pady=(0, 8), sticky="nsew")
        if hasattr(self.body, "_scrollbar"):
            self.body._scrollbar.configure(width=7)

        self.drop_indicator = ctk.CTkFrame(
            self.body,
            height=4,
            corner_radius=2,
            fg_color=self.theme["drop_indicator_color"],
        )
        self.empty_label: ctk.CTkLabel | None = None

    def add_card(self, card: CTkKanbanCard) -> None:
        if self.empty_label is not None:
            self.empty_label.destroy()
            self.empty_label = None
        self.card_widgets.append(card)
        card.pack(fill="x", padx=2, pady=5)
        self.count_label.configure(text=str(len(self.card_widgets)))

    def set_cards(self, cards: list[CTkKanbanCard], *, empty_text: str = "No cards") -> None:
        """Arrange existing card widgets without rebuilding the scroll frame."""

        self.clear_drop_indicator()
        if self.empty_label is not None:
            self.empty_label.destroy()
            self.empty_label = None
        current: list[CTkKanbanCard] = []
        for card in self.card_widgets:
            try:
                if card in cards and card.winfo_manager() == "pack":
                    current.append(card)
            except tk.TclError:
                continue

        for index, card in enumerate(cards):
            if index < len(current) and current[index] is card:
                continue
            if card in current:
                card.pack_forget()
                current.remove(card)
            options = {"fill": "x", "padx": 2, "pady": 5}
            if index < len(current):
                card.pack(before=current[index], **options)
            else:
                card.pack(**options)
            current.insert(index, card)

        self.card_widgets = list(cards)
        if not self.card_widgets:
            self.show_empty(empty_text)

    def show_empty(self, text: str = "No cards") -> None:
        if self.card_widgets or self.empty_label is not None:
            return
        self.empty_label = ctk.CTkLabel(
            self.body,
            text=text,
            height=80,
            text_color=self.theme["muted_text_color"],
        )
        self.empty_label.pack(fill="x", padx=8, pady=14)

    def contains_point(self, root_x: int, root_y: int) -> bool:
        return (
            self.winfo_rootx() <= root_x <= self.winfo_rootx() + self.winfo_width()
            and self.winfo_rooty() <= root_y <= self.winfo_rooty() + self.winfo_height()
        )

    def card_index_at(self, root_y: int, *, excluding_id: Any | None = None) -> int:
        visible = [card for card in self.card_widgets if card.card_id != excluding_id]
        for index, card in enumerate(visible):
            midpoint = card.winfo_rooty() + card.winfo_height() // 2
            if root_y < midpoint:
                return index
        return len(visible)

    def show_drop_indicator(self, index: int, *, excluding_id: Any | None = None) -> None:
        if self._drop_index == index:
            return
        self.clear_drop_indicator()
        visible = [card for card in self.card_widgets if card.card_id != excluding_id]
        options = {"fill": "x", "padx": 5, "pady": 2}
        if 0 <= index < len(visible):
            self.drop_indicator.pack(before=visible[index], **options)
        else:
            self.drop_indicator.pack(**options)
        self._drop_index = index

    def clear_drop_indicator(self) -> None:
        if self._drop_index is None:
            return
        self.drop_indicator.pack_forget()
        self._drop_index = None

    def set_drop_target(self, active: bool) -> None:
        if self._drop_active == active:
            return
        self._drop_active = active
        self.configure(
            border_width=2 if active else 1,
            border_color=(
                self.theme["drop_indicator_color"]
                if active
                else self.theme["column_border_color"]
            ),
        )

    def destroy(self) -> None:
        """Release the card list's global wheel bindings before teardown."""

        if hasattr(self, "body"):
            self.body.destroy()
        super().destroy()
