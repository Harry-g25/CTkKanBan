"""Column widget for the simplified Kanban board."""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable, Mapping

import customtkinter as ctk

from ._scrolling import ManagedScrollableFrame
from .card import CTkKanbanCard
from .config import TextConfig


class CTkKanbanColumn(ctk.CTkFrame):
    """A readable, full-height column with a vertically scrollable card list."""

    def __init__(
        self,
        master: Any,
        column: Mapping[str, Any],
        theme: Mapping[str, Any],
        *,
        width: int = 288,
        height: int = 600,
        accent_color: Any | None = None,
        on_add: Callable[[Any], None] | None = None,
        on_menu: Callable[[Any, Any], None] | None = None,
        text: TextConfig | None = None,
    ) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            fg_color=theme["column_fg_color"],
            border_color=theme["column_border_color"],
            border_width=theme["column_border_width"],
            corner_radius=theme["column_corner_radius"],
        )
        self.grid_propagate(False)
        self.column = dict(column)
        self.column_id = self.column["id"]
        self.theme = dict(theme)
        self.accent_color = accent_color or self.theme["accent_color"]
        self._on_add = on_add
        self.text = text or TextConfig()
        self.card_widgets: list[CTkKanbanCard] = []
        self._drop_active = False
        self._drop_index: int | None = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.accent_bar = ctk.CTkFrame(
            self,
            height=self.theme["column_accent_height"],
            corner_radius=2,
            fg_color=self.accent_color,
        )
        self.accent_bar.grid(
            row=0,
            column=0,
            padx=self.theme["column_header_padding_x"],
            pady=(10, 2),
            sticky="ew",
        )

        header = ctk.CTkFrame(self, fg_color=self.theme["column_header_fg_color"])
        header.grid(
            row=1,
            column=0,
            padx=self.theme["column_header_padding_x"],
            pady=(5, 8),
            sticky="ew",
        )
        header.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            header,
            text=str(self.column["title"]),
            anchor="w",
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(**self.theme["column_title_font"]),
        )
        self.title_label.grid(row=0, column=0, sticky="ew")

        self.count_label = ctk.CTkLabel(
            header,
            text="0",
            width=26,
            height=22,
            corner_radius=7,
            fg_color=self.theme["count_fg_color"],
            text_color=self.theme["muted_text_color"],
            font=ctk.CTkFont(**self.theme["column_count_font"]),
        )
        self.count_label.grid(row=0, column=1, padx=(8, 5))

        self.add_button = ctk.CTkButton(
            header,
            text="+",
            width=30,
            height=30,
            corner_radius=8,
            command=lambda: on_add(self.column_id) if on_add is not None else None,
        )
        if on_add is not None:
            self.add_button.grid(row=0, column=2, padx=2)

        self.menu_button: ctk.CTkButton = ctk.CTkButton(
            header,
            text="\u22ef",
            width=30,
            height=30,
            corner_radius=8,
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
        self.body.grid(row=2, column=0, padx=7, pady=(0, 8), sticky="nsew")
        if hasattr(self.body, "_scrollbar"):
            self.body._scrollbar.configure(width=self.theme["scrollbar_width"])

        self.drop_indicator = ctk.CTkFrame(
            self.body,
            height=4,
            corner_radius=2,
            fg_color=self.theme["drop_indicator_color"],
        )
        self.empty_label: ctk.CTkLabel | None = None
        self.empty_frame: ctk.CTkFrame | None = None

    def _clear_empty(self) -> None:
        if self.empty_frame is not None:
            self.empty_frame.destroy()
            self.empty_frame = None
            self.empty_label = None

    def add_card(self, card: CTkKanbanCard) -> None:
        self._clear_empty()
        self.card_widgets.append(card)
        card.pack(fill="x", padx=3, pady=self.theme["card_gap"])
        self.count_label.configure(text=str(len(self.card_widgets)))

    def set_cards(self, cards: list[CTkKanbanCard], *, empty_text: str = "No cards") -> None:
        """Arrange existing card widgets without rebuilding the scroll frame."""

        self.clear_drop_indicator()
        self._clear_empty()
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
            options = {"fill": "x", "padx": 3, "pady": self.theme["card_gap"]}
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
        self.empty_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        self.empty_frame.pack(fill="x", padx=12, pady=(54, 18))
        is_search = "matching" in text.casefold()
        ctk.CTkLabel(
            self.empty_frame,
            text="\u2315" if is_search else "+",
            width=42,
            height=42,
            corner_radius=21,
            fg_color=self.theme["empty_icon_fg_color"],
            text_color=self.accent_color,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(0, 9))
        self.empty_label = ctk.CTkLabel(
            self.empty_frame,
            text=self.text.no_results if is_search else self.text.no_cards,
            text_color=self.theme["text_color"],
            font=ctk.CTkFont(**self.theme["column_empty_title_font"]),
        )
        self.empty_label.pack()
        ctk.CTkLabel(
            self.empty_frame,
            text=self.text.no_results_help if is_search else self.text.no_cards_help,
            text_color=self.theme["muted_text_color"],
            font=ctk.CTkFont(**self.theme["column_empty_body_font"]),
        ).pack(pady=(2, 10))
        if not is_search and self._on_add is not None:
            ctk.CTkButton(
                self.empty_frame,
                text="Add card",
                width=92,
                height=30,
                corner_radius=8,
                fg_color="transparent",
                border_width=1,
                border_color=self.theme["column_border_color"],
                hover_color=self.theme["control_hover_color"],
                text_color=self.theme["text_color"],
                command=(
                    lambda: self._on_add(self.column_id)
                    if self._on_add is not None
                    else None
                ),
            ).pack()

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
