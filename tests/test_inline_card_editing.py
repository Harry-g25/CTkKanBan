"""Focused GUI regressions for editing card fields in place."""

from __future__ import annotations

import tkinter as tk
import unittest
from types import SimpleNamespace
from typing import Any

import customtkinter as ctk
from gui_test_app import TEST_APP

from ctk_kanban import CTkKanbanBoard
from ctk_kanban.utils import iter_widget_tree

FIELDS = [
    {
        "key": "title",
        "label": "Title",
        "type": "text",
        "required": True,
        "show_on_card": True,
    },
    {
        "key": "assignee",
        "label": "Assignee",
        "type": "text",
        "show_on_card": True,
    },
    {
        "key": "estimate",
        "label": "Estimate",
        "type": "number",
        "show_on_card": True,
    },
    {
        "key": "tags",
        "label": "Tags",
        "type": "tags",
        "show_on_card": True,
    },
    {
        "key": "status",
        "label": "Status",
        "type": "select",
        "options": ["Todo", "Doing", "Done"],
        "show_on_card": True,
    },
    {
        "key": "flagged",
        "label": "Flagged",
        "type": "checkbox",
        "show_on_card": True,
    },
    {
        "key": "notes",
        "label": "Notes",
        "type": "text",
        "show_on_card": True,
    },
    {
        "key": "read_only_value",
        "label": "Read only",
        "type": "text",
        "show_on_card": True,
        "read_only": True,
    },
    {
        "key": "form_only",
        "label": "Form only",
        "type": "text",
        "show_on_card": False,
        "show_in_form": True,
    },
]


class InlineCardEditingTests(unittest.TestCase):
    app = TEST_APP

    def setUp(self) -> None:
        self.boards: list[CTkKanbanBoard] = []
        self.board = self.make_board()

    def tearDown(self) -> None:
        for board in reversed(self.boards):
            board.destroy()
        self.app.update_idletasks()

    def make_board(
        self,
        master: Any | None = None,
        **options: Any,
    ) -> CTkKanbanBoard:
        defaults: dict[str, Any] = {
            "columns": [{"id": "todo", "title": "To Do"}],
            "cards": [
                {
                    "id": 1,
                    "column": "todo",
                    "title": "Original",
                    "assignee": "Alex",
                    "estimate": 1,
                    "tags": ["initial"],
                    "status": "Todo",
                    "flagged": False,
                    "read_only_value": "Fixed",
                    "form_only": "Hidden from card",
                }
            ],
            "fields": FIELDS,
            "show_toolbar": False,
            "column_height": 420,
        }
        defaults.update(options)
        board = CTkKanbanBoard(
            self.app if master is None else master,
            **defaults,
        )
        board.pack(fill="both", expand=True)
        self.boards.append(board)
        self.app.update_idletasks()
        return board

    @staticmethod
    def replace_entry_value(control: Any, value: str) -> None:
        control.delete(0, "end")
        control.insert(0, value)

    @staticmethod
    def error_text(card: Any) -> str:
        label = card.inline_error_label
        return "" if label is None else str(label.cget("text")).strip()

    def test_inline_editing_is_enabled_by_default_and_does_not_open_a_form(self) -> None:
        self.assertTrue(self.board.enable_inline_card_editing)

        self.board.start_inline_card_edit(1)
        card = self.board._card_widgets[1]

        self.assertEqual(card.editing_field_key, "title")
        self.assertIsNotNone(card.inline_control)
        self.assertIsNone(self.board._card_form_dialog)
        self.assertIsNone(self.board._card_form_panel)

    def test_clicking_rendered_data_starts_editing_without_dragging(self) -> None:
        click_events: list[dict[str, Any]] = []
        self.board._callbacks["on_card_clicked"] = click_events.append
        card = self.board._card_widgets[1]
        target = card.title_label._label

        target.event_generate("<ButtonPress-1>", x=2, y=2)
        target.event_generate("<ButtonRelease-1>", x=2, y=2)
        self.app.update()

        self.assertEqual(card.editing_field_key, "title")
        self.assertIsNone(self.board._drag_state)
        self.assertIsNone(self.board._card_form_dialog)
        self.assertEqual(len(click_events), 1)
        self.assertEqual(click_events[0]["card_id"], 1)

    def test_inline_field_double_click_still_honors_custom_callback(self) -> None:
        double_click_events: list[dict[str, Any]] = []
        self.board.card_form_mode = "sidepanel"

        def open_custom_editor(event: dict[str, Any]) -> None:
            double_click_events.append(event)
            self.board.open_edit_card_form(1)

        self.board._callbacks["on_card_double_clicked"] = open_custom_editor
        card = self.board._card_widgets[1]
        target = card.title_label._label

        for _index in range(2):
            target.event_generate("<ButtonPress-1>", x=2, y=2)
            target.event_generate("<ButtonRelease-1>", x=2, y=2)
            self.app.update()

        self.assertEqual(len(double_click_events), 1)
        self.assertEqual(double_click_events[0]["field_key"], "title")
        self.assertIsNone(card.editing_field_key)
        self.assertIsNotNone(self.board._card_form_panel)

    def test_double_click_fallback_starts_inline_title_editing(self) -> None:
        card = self.board._card_widgets[1]
        self.board.open_edit_card_form = lambda _card_id: self.fail(  # type: ignore[method-assign]
            "double-click opened the legacy form"
        )

        self.board._on_card_double_click(
            card,
            SimpleNamespace(x_root=card.winfo_rootx(), y_root=card.winfo_rooty()),
        )

        self.assertEqual(card.editing_field_key, "title")
        self.assertIsNotNone(card.inline_control)
        self.assertIsNone(self.board._card_form_dialog)

    def test_inline_editing_can_be_disabled_for_legacy_form_behavior(self) -> None:
        board = self.make_board(enable_inline_card_editing=False)
        card = board._card_widgets[1]
        requested: list[Any] = []
        board.open_edit_card_form = requested.append  # type: ignore[method-assign]

        board._on_card_double_click(
            card,
            SimpleNamespace(x_root=card.winfo_rootx(), y_root=card.winfo_rooty()),
        )

        self.assertEqual(requested, [1])
        self.assertFalse(board.start_inline_card_edit(1))
        self.assertIsNone(card.editing_field_key)

    def test_text_commit_trims_value_and_updates_only_the_edited_card(self) -> None:
        second = self.board.add_card(
            {"id": 2, "column": "todo", "title": "Second"},
            source="test",
        )
        self.assertIsNotNone(second)
        untouched_widget = self.board._card_widgets[2]
        old_widget = self.board._card_widgets[1]

        old_widget.start_inline_edit("title")
        self.replace_entry_value(old_widget.inline_control, "  Updated title  ")
        old_widget.commit_inline_edit()
        self.app.update_idletasks()

        self.assertEqual(self.board.get_card(1)["title"], "Updated title")
        self.assertEqual(self.board._card_widgets[1].title_label.cget("text"), "Updated title")
        self.assertIsNot(self.board._card_widgets[1], old_widget)
        self.assertIs(self.board._card_widgets[2], untouched_widget)

    def test_clicking_away_saves_a_focused_inline_entry(self) -> None:
        card = self.board._card_widgets[1]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "Saved on click away")
        card.inline_control.focus_set()
        self.app.update()

        self.board._commit_inline_on_outside_press(
            SimpleNamespace(widget=self.board._canvas)
        )

        self.assertEqual(self.board.get_card(1)["title"], "Saved on click away")
        self.assertIsNot(self.board._card_widgets[1], card)

    def test_click_away_saves_before_a_host_button_action_and_blocks_invalid_data(
        self,
    ) -> None:
        observed_titles: list[str] = []
        button = ctk.CTkButton(
            self.board,
            text="Inspect",
            command=lambda: observed_titles.append(self.board.get_card(1)["title"]),
        )
        button.place(x=4, y=4)
        self.app.deiconify()
        try:
            self.app.update()

            card = self.board._card_widgets[1]
            card.start_inline_edit("title")
            self.replace_entry_value(card.inline_control, "Saved before action")
            button._canvas.event_generate("<ButtonPress-1>", x=2, y=2)
            button._canvas.event_generate("<ButtonRelease-1>", x=2, y=2)
            self.app.update()

            card = self.board._card_widgets[1]
            card.start_inline_edit("title")
            self.replace_entry_value(card.inline_control, "   ")
            button._canvas.event_generate("<ButtonPress-1>", x=2, y=2)
            button._canvas.event_generate("<ButtonRelease-1>", x=2, y=2)
            self.app.update()
        finally:
            self.app.withdraw()
            self.app.update_idletasks()

        self.assertEqual(observed_titles, ["Saved before action"])
        self.assertEqual(self.board.get_card(1)["title"], "Saved before action")
        self.assertEqual(card.editing_field_key, "title")
        self.assertTrue(self.error_text(card))

    def test_click_away_capture_includes_controls_created_during_the_edit(self) -> None:
        observed_titles: list[str] = []
        self.app.deiconify()
        try:
            self.app.update()
            card = self.board._card_widgets[1]
            card.start_inline_edit("title")
            self.replace_entry_value(card.inline_control, "Captured dynamically")

            button = ctk.CTkButton(
                self.board,
                text="Created later",
                command=lambda: observed_titles.append(
                    self.board.get_card(1)["title"]
                ),
            )
            button.place(x=4, y=4)
            self.app.update()

            capture_tag = self.board._inline_outside_click_binding[2]
            self.assertEqual(button._canvas.bindtags()[0], capture_tag)
            button._canvas.event_generate("<ButtonPress-1>", x=2, y=2)
            button._canvas.event_generate("<ButtonRelease-1>", x=2, y=2)
            self.app.update()

            card = self.board._card_widgets[1]
            card.start_inline_edit("title")
            self.replace_entry_value(card.inline_control, "   ")
            blocked_button = ctk.CTkButton(
                self.board,
                text="Also created later",
                command=lambda: observed_titles.append(
                    self.board.get_card(1)["title"]
                ),
            )
            blocked_button.place(x=120, y=4)
            self.app.update()
            blocked_button._canvas.event_generate("<ButtonPress-1>", x=2, y=2)
            blocked_button._canvas.event_generate("<ButtonRelease-1>", x=2, y=2)
            self.app.update()
        finally:
            self.app.withdraw()
            self.app.update_idletasks()

        self.assertEqual(observed_titles, ["Captured dynamically"])
        self.assertEqual(self.board.get_card(1)["title"], "Captured dynamically")
        self.assertEqual(card.editing_field_key, "title")
        self.assertTrue(self.error_text(card))

    def test_clicking_another_card_keeps_capture_for_its_new_inline_editor(
        self,
    ) -> None:
        self.board.add_card(
            {"id": 2, "column": "todo", "title": "Second"},
            source="test",
        )
        self.app.deiconify()
        try:
            self.app.update()
            first = self.board._card_widgets[1]
            first.start_inline_edit("title")
            self.replace_entry_value(first.inline_control, "First saved")
            second_target = self.board._card_widgets[2].title_label._label

            second_target.event_generate("<ButtonPress-1>", x=2, y=2)
            second_target.event_generate("<ButtonRelease-1>", x=2, y=2)
            self.app.update()
        finally:
            self.app.withdraw()
            self.app.update_idletasks()

        second = self.board._card_widgets[2]
        self.assertEqual(self.board.get_card(1)["title"], "First saved")
        self.assertEqual(second.editing_field_key, "title")
        self.assertIs(self.board._inline_edit_card, second)
        self.assertIsNotNone(self.board._inline_outside_click_binding)

    def test_full_refresh_replays_a_click_on_the_replacement_card(self) -> None:
        click_events: list[dict[str, Any]] = []
        board = self.make_board(
            cards=[
                {"id": 1, "column": "todo", "title": "First"},
                {"id": 2, "column": "todo", "title": "Second"},
            ],
            incremental_card_rendering=False,
            on_card_clicked=click_events.append,
        )
        board._callbacks["on_card_updated"] = lambda _event: board.refresh()
        self.app.deiconify()
        try:
            self.app.update()
            first = board._card_widgets[1]
            first.start_inline_edit("title")
            self.replace_entry_value(first.inline_control, "First saved")
            old_second_target = board._card_widgets[2].title_label._label

            old_second_target.event_generate("<ButtonPress-1>", x=2, y=2)
            self.app.update()
        finally:
            self.app.withdraw()
            self.app.update_idletasks()

        second = board._card_widgets[2]
        self.assertFalse(first.winfo_exists())
        self.assertEqual(board.get_card(1)["title"], "First saved")
        self.assertEqual(second.editing_field_key, "title")
        self.assertIs(board._inline_edit_card, second)
        self.assertEqual([event["card_id"] for event in click_events], [2])

    def test_capture_callbacks_are_removed_from_a_child_toplevel_root(self) -> None:
        toplevel = ctk.CTkToplevel(self.app)
        toplevel.withdraw()
        board = self.make_board(master=toplevel)
        try:
            card = board._card_widgets[1]
            card.start_inline_edit("title")
            binding = board._inline_outside_click_binding
            self.assertIsNotNone(binding)
            bind_owner = binding[1]
            bind_tag = binding[2]
            click_bind_id = binding[3]
            map_bind_id = binding[4]
            self.assertIs(bind_owner, self.app._root())
            click_script = str(bind_owner.tk.call("bind", bind_tag, "<ButtonPress-1>"))
            self.assertIn(click_bind_id, click_script)
            map_script = str(bind_owner.tk.call("bind", "all", "<Map>"))
            self.assertIn(map_bind_id, map_script)

            card.cancel_inline_edit()

            click_script = str(bind_owner.tk.call("bind", bind_tag, "<ButtonPress-1>"))
            self.assertNotIn(click_bind_id, click_script)
            map_script = str(bind_owner.tk.call("bind", "all", "<Map>"))
            self.assertNotIn(map_bind_id, map_script)
            self.assertIsNone(board._inline_outside_click_binding)
        finally:
            board.destroy()
            self.boards.remove(board)
            toplevel.destroy()

    def test_capture_cleanup_preserves_an_existing_global_map_binding(self) -> None:
        external_bind_id = tk.Misc.bind_all(
            self.app,
            "<Map>",
            lambda _event: None,
            add="+",
        )
        self.assertIsNotNone(external_bind_id)
        bind_path = ("bind", "all", "<Map>")
        baseline_script = str(self.app.tk.call(*bind_path))
        baseline_lines = [
            line
            for line in baseline_script.splitlines()
            if line.strip()
        ]
        try:
            for _index in range(3):
                card = self.board._card_widgets[1]
                card.start_inline_edit("title")
                card.cancel_inline_edit()

            remaining_script = str(self.app.tk.call(*bind_path))
            remaining_lines = [
                line
                for line in remaining_script.splitlines()
                if line.strip()
            ]
            self.assertEqual(remaining_lines, baseline_lines)
            self.assertEqual(remaining_script, baseline_script.rstrip())
            map_script = str(self.app.tk.call(*bind_path))
            self.assertIn(external_bind_id, map_script)
        finally:
            # Remove external bind: compatible with Python 3.10 and later.
            # Each registered callback occupies one line in the Tcl bind script
            # with the form: if {"[<funcid> ...]" == "break"} break
            script = str(self.app.tk.call(*bind_path))
            prefix = f'if {{"[{external_bind_id} '
            remaining = "\n".join(
                ln for ln in script.split("\n") if not ln.startswith(prefix)
            ).rstrip()
            self.app.tk.call(*bind_path, remaining)
            self.app.deletecommand(external_bind_id)

    def test_switching_fields_commits_and_opens_the_requested_replacement_editor(self) -> None:
        card = self.board._card_widgets[1]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "Switch fields")

        self.assertTrue(card.start_inline_edit("assignee"))

        replacement = self.board._card_widgets[1]
        self.assertIsNot(replacement, card)
        self.assertEqual(self.board.get_card(1)["title"], "Switch fields")
        self.assertEqual(replacement.editing_field_key, "assignee")
        self.assertEqual(replacement.inline_control.get(), "Alex")

    def test_full_refresh_cancels_the_transient_editor_and_capture_binding(self) -> None:
        card = self.board._card_widgets[1]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "Unsaved transient value")

        self.board.refresh()

        self.assertFalse(card.winfo_exists())
        self.assertEqual(self.board.get_card(1)["title"], "Original")
        self.assertIsNone(self.board._inline_edit_card)
        self.assertIsNone(self.board._inline_outside_click_binding)
        self.assertIsNone(
            self.board._commit_inline_on_outside_press(
                SimpleNamespace(widget=self.board._canvas)
            )
        )

    def test_inline_commit_is_safe_when_global_incremental_updates_are_disabled(
        self,
    ) -> None:
        board = self.make_board(
            cards=[
                {
                    "id": 1,
                    "column": "todo",
                    "title": "Original",
                    "assignee": "Alex",
                },
                {"id": 2, "column": "todo", "title": "Second"},
            ],
            incremental_card_rendering=False,
        )
        card = board._card_widgets[1]
        untouched = board._card_widgets[2]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "Saved safely")

        self.assertTrue(card.commit_inline_edit())

        self.assertFalse(card.winfo_exists())
        self.assertEqual(board.get_card(1)["title"], "Saved safely")
        self.assertEqual(
            board._card_widgets[1].title_label.cget("text"),
            "Saved safely",
        )
        self.assertIs(board._card_widgets[2], untouched)
        self.assertIsNone(board._inline_edit_card)
        self.assertIsNone(board._inline_outside_click_binding)

    def test_column_control_action_survives_inline_commit_with_full_render_mode(
        self,
    ) -> None:
        board = self.make_board(
            card_form_mode="sidepanel",
            incremental_card_rendering=False,
        )
        self.app.deiconify()
        try:
            self.app.update()
            card = board._card_widgets[1]
            card.start_inline_edit("title")
            self.replace_entry_value(card.inline_control, "Saved before adding")
            add_target = board._column_widgets["todo"].add_button._canvas

            add_target.event_generate("<ButtonPress-1>", x=2, y=2)
            add_target.event_generate("<ButtonRelease-1>", x=2, y=2)
            self.app.update()
        finally:
            self.app.withdraw()
            self.app.update_idletasks()

        self.assertEqual(board.get_card(1)["title"], "Saved before adding")
        self.assertIsNotNone(board._card_form_panel)

    def test_inline_commit_uses_update_events_and_undo_history(self) -> None:
        callback_events: list[dict[str, Any]] = []
        self.board._callbacks["on_card_updated"] = callback_events.append
        card = self.board._card_widgets[1]
        card.start_inline_edit("assignee")
        self.replace_entry_value(card.inline_control, "Morgan")

        card.commit_inline_edit()

        self.assertEqual(callback_events[0]["source"], "inline_edit")
        self.assertEqual(callback_events[0]["changed_fields"]["assignee"], "Morgan")
        self.assertTrue(self.board.can_undo())
        self.assertTrue(self.board.undo())
        self.assertEqual(self.board.get_card(1)["assignee"], "Alex")

    def test_number_tags_select_and_checkbox_values_are_parsed_on_commit(self) -> None:
        card = self.board._card_widgets[1]
        card.start_inline_edit("estimate")
        self.replace_entry_value(card.inline_control, "2.5")
        card.commit_inline_edit()
        self.assertEqual(self.board.get_card(1)["estimate"], 2.5)

        card = self.board._card_widgets[1]
        card.start_inline_edit("tags")
        self.replace_entry_value(card.inline_control, "alpha, beta, gamma")
        card.commit_inline_edit()
        self.assertEqual(self.board.get_card(1)["tags"], ["alpha", "beta", "gamma"])

        card = self.board._card_widgets[1]
        card.start_inline_edit("status")
        card.inline_control.set("Done")
        card.commit_inline_edit()
        self.assertEqual(self.board.get_card(1)["status"], "Done")

        card = self.board._card_widgets[1]
        card.start_inline_edit("flagged")
        card.inline_control.select()
        card.commit_inline_edit()
        self.assertIs(self.board.get_card(1)["flagged"], True)

    def test_textarea_temporal_multiselect_and_badge_controls_commit_typed_data(self) -> None:
        fields = [
            {
                "key": "title",
                "label": "Title",
                "type": "text",
                "required": True,
                "show_on_card": True,
            },
            {
                "key": "details",
                "label": "Details",
                "type": "textarea",
                "show_on_card": True,
            },
            {
                "key": "due",
                "label": "Due",
                "type": "date",
                "show_on_card": True,
            },
            {
                "key": "starts",
                "label": "Starts",
                "type": "datetime",
                "show_on_card": True,
            },
            {
                "key": "teams",
                "label": "Teams",
                "type": "multiselect",
                "options": ["Design", "Engineering", "QA"],
                "show_on_card": True,
            },
            {
                "key": "risk",
                "label": "Risk",
                "type": "badge",
                "options": ["Low", "High"],
                "show_on_card": True,
            },
        ]
        board = self.make_board(
            fields=fields,
            cards=[
                {
                    "id": 1,
                    "column": "todo",
                    "title": "Typed fields",
                    "details": "Original details",
                    "due": "2026-07-24",
                    "starts": "2026-07-24T09:00:00+00:00",
                    "teams": ["Design"],
                    "risk": "Low",
                }
            ],
        )

        card = board._card_widgets[1]
        card.start_inline_edit("details")
        hint_texts = [
            str(widget.cget("text"))
            for widget in iter_widget_tree(card.inline_editor)
            if isinstance(widget, ctk.CTkLabel)
        ]
        self.assertIn("Ctrl+Enter saves · Esc cancels", hint_texts)
        card.inline_control.delete("1.0", "end")
        card.inline_control.insert("1.0", "Line one\nLine two")
        card.commit_inline_edit()
        self.assertEqual(board.get_card(1)["details"], "Line one\nLine two")

        card = board._card_widgets[1]
        card.start_inline_edit("due")
        card.inline_control._open_picker()
        self.app.update()
        self.assertEqual(card.editing_field_key, "due")
        self.assertTrue(card.inline_control._picker.winfo_exists())
        card.inline_control._close_picker()
        self.replace_entry_value(card.inline_control, "2026-08-15")
        card.commit_inline_edit()
        self.assertEqual(board.get_card(1)["due"], "2026-08-15")

        card = board._card_widgets[1]
        card.start_inline_edit("starts")
        self.replace_entry_value(card.inline_control, "2026-08-15T14:30:00+00:00")
        card.commit_inline_edit()
        self.assertEqual(
            board.get_card(1)["starts"],
            "2026-08-15T14:30:00+00:00",
        )

        card = board._card_widgets[1]
        card.start_inline_edit("teams")
        self.replace_entry_value(card.inline_control, "Engineering, QA")
        card.commit_inline_edit()
        self.assertEqual(board.get_card(1)["teams"], ["Engineering", "QA"])

        card = board._card_widgets[1]
        card.start_inline_edit("risk")
        card.inline_control.set("High")
        card.commit_inline_edit()
        self.assertEqual(board.get_card(1)["risk"], "High")

    def test_escape_and_cancel_restore_the_original_value(self) -> None:
        card = self.board._card_widgets[1]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "Escape me")
        self.assertEqual(card._cancel_inline_event(), "break")

        self.assertEqual(self.board.get_card(1)["title"], "Original")
        self.assertIsNone(card.editing_field_key)
        self.assertIsNone(card.inline_control)

        card.start_inline_edit("assignee")
        self.replace_entry_value(card.inline_control, "Cancel me")
        card.cancel_inline_edit()

        self.assertEqual(self.board.get_card(1)["assignee"], "Alex")
        self.assertIsNone(card.editing_field_key)
        self.assertIsNone(card.inline_control)

    def test_unchanged_commit_is_a_no_op(self) -> None:
        callback_events: list[dict[str, Any]] = []
        self.board._callbacks["on_card_updated"] = callback_events.append
        card = self.board._card_widgets[1]
        before = self.board.get_card(1)

        card.start_inline_edit("title")
        card.commit_inline_edit()

        self.assertEqual(self.board.get_card(1), before)
        self.assertIs(self.board._card_widgets[1], card)
        self.assertEqual(callback_events, [])
        self.assertFalse(self.board.can_undo())
        self.assertIsNone(card.editing_field_key)

    def test_validation_failure_keeps_editor_open_and_data_unchanged(self) -> None:
        card = self.board._card_widgets[1]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "   ")
        card.commit_inline_edit()

        self.assertEqual(self.board.get_card(1)["title"], "Original")
        self.assertEqual(card.editing_field_key, "title")
        self.assertIsNotNone(card.inline_control)
        self.assertTrue(self.error_text(card))

        card.cancel_inline_edit()
        card.start_inline_edit("estimate")
        self.replace_entry_value(card.inline_control, "not a number")
        card.commit_inline_edit()

        self.assertEqual(self.board.get_card(1)["estimate"], 1)
        self.assertEqual(card.editing_field_key, "estimate")
        self.assertTrue(self.error_text(card))

    def test_callback_rejection_keeps_editor_open_and_shows_reason(self) -> None:
        self.board._callbacks["on_card_updated"] = lambda _event: {
            "cancel": True,
            "reason": "Inline change rejected",
        }
        card = self.board._card_widgets[1]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "Rejected")

        card.commit_inline_edit()

        self.assertEqual(self.board.get_card(1)["title"], "Original")
        self.assertIs(self.board._card_widgets[1], card)
        self.assertEqual(card.editing_field_key, "title")
        self.assertIn("rejected", self.error_text(card).casefold())

    def test_read_only_and_non_card_fields_do_not_start_editing(self) -> None:
        card = self.board._card_widgets[1]

        card.start_inline_edit("read_only_value")
        self.assertIsNone(card.editing_field_key)
        self.assertIsNone(card.inline_control)

        self.board.start_inline_card_edit(1, "form_only")
        self.assertIsNone(card.editing_field_key)
        self.assertIsNone(card.inline_control)

    def test_custom_renderer_does_not_assume_default_inline_field_widgets(self) -> None:
        def renderer(
            master: Any,
            card_data: dict[str, Any],
            _fields: list[dict[str, Any]],
            _theme: dict[str, Any],
        ) -> None:
            ctk.CTkLabel(master, text=card_data["title"]).pack()

        board = self.make_board(card_renderer=renderer)
        card = board._card_widgets[1]

        board.start_inline_card_edit(1, "title")

        self.assertIsNone(card.editing_field_key)
        self.assertIsNone(card.inline_control)
        self.assertIsNone(board._card_form_dialog)

    def test_empty_visible_field_has_a_placeholder_and_accepts_inline_data(self) -> None:
        card = self.board._card_widgets[1]
        label_texts = [
            str(widget.cget("text"))
            for widget in iter_widget_tree(card)
            if isinstance(widget, ctk.CTkLabel)
        ]
        self.assertTrue(
            any("notes" in text.casefold() for text in label_texts),
            f"No placeholder identifying the empty Notes field was rendered: {label_texts!r}",
        )

        card.start_inline_edit("notes")
        self.assertEqual(card.editing_field_key, "notes")
        self.assertEqual(card.inline_control.get(), "")
        self.replace_entry_value(card.inline_control, "Added without a dialog")
        card.commit_inline_edit()

        self.assertEqual(self.board.get_card(1)["notes"], "Added without a dialog")
        self.assertIsNone(self.board._card_form_dialog)

    def test_missing_field_default_is_saved_when_accepted_unchanged(self) -> None:
        board = self.make_board(
            fields=[
                {
                    "key": "title",
                    "label": "Title",
                    "type": "text",
                    "required": True,
                    "show_on_card": True,
                },
                {
                    "key": "status",
                    "label": "Status",
                    "type": "select",
                    "options": ["Todo", "Done"],
                    "default": "Todo",
                    "show_on_card": True,
                },
            ],
            cards=[{"id": 1, "column": "todo", "title": "Defaults"}],
        )
        card = board._card_widgets[1]

        card.start_inline_edit("status")
        self.assertEqual(card.inline_control.get(), "Todo")
        card.commit_inline_edit()

        self.assertEqual(board.get_card(1)["status"], "Todo")

    def test_option_values_with_significant_whitespace_are_preserved(self) -> None:
        fields = [
            {
                "key": "title",
                "label": "Title",
                "type": "text",
                "required": True,
                "show_on_card": True,
            },
            {
                "key": "status",
                "label": "Status",
                "type": "select",
                "options": [" A ", "B"],
                "show_on_card": True,
            },
        ]
        board = self.make_board(
            fields=fields,
            cards=[
                {
                    "id": 1,
                    "column": "todo",
                    "title": "Whitespace option",
                    "status": "B",
                }
            ],
            card_form_mode="sidepanel",
        )

        card = board._card_widgets[1]
        card.start_inline_edit("status")
        card.inline_control.set(" A ")
        self.assertTrue(card.commit_inline_edit())
        self.assertEqual(board.get_card(1)["status"], " A ")

        board.open_edit_card_form(1)
        panel = board._card_form_panel
        self.assertIsNotNone(panel)
        panel.controls["status"].set("B")
        panel._submit()
        self.assertEqual(board.get_card(1)["status"], "B")

        board.open_edit_card_form(1)
        panel = board._card_form_panel
        panel.controls["status"].set(" A ")
        panel._submit()
        self.assertEqual(board.get_card(1)["status"], " A ")

    def test_full_card_form_and_inline_editor_cannot_keep_stale_parallel_edits(self) -> None:
        board = self.make_board(card_form_mode="sidepanel")
        card = board._card_widgets[1]
        card.start_inline_edit("title")
        self.replace_entry_value(card.inline_control, "Fresh inline value")

        board.open_edit_card_form(1)

        self.assertEqual(board.get_card(1)["title"], "Fresh inline value")
        self.assertIsNone(board._inline_edit_card)
        self.assertEqual(
            board._card_form_panel.initial_data["title"],
            "Fresh inline value",
        )

        board._card_form_panel._close()
        board.open_edit_card_form(1)
        self.assertIsNotNone(board._card_form_panel)

        self.assertTrue(board.start_inline_card_edit(1, "assignee"))
        self.assertIsNone(board._card_form_panel)
        self.assertEqual(board._card_widgets[1].editing_field_key, "assignee")


if __name__ == "__main__":
    unittest.main()
