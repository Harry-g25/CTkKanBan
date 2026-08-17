"""Focused behavior checks for the simplified board widget."""

from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace
from typing import Any

import pytest

from ctk_kanban import CTkKanbanBoard
from ctk_kanban.editor import CardEditor


def descendants(widget: Any) -> list[Any]:
    children = list(widget.winfo_children())
    return children + [nested for child in children for nested in descendants(child)]


def binding_count(root: Any, sequence: str) -> int:
    return str(root.bind_all(sequence) or "").count('if {"[')


def make_board(root: Any, **options: Any) -> CTkKanbanBoard:
    values: dict[str, Any] = {
        "columns": [
            {"id": "todo", "title": "To do"},
            {"id": "done", "title": "Done"},
        ],
        "cards": [
            {"id": 1, "column": "todo", "title": "One"},
            {"id": 2, "column": "todo", "title": "Two"},
        ],
        "show_toolbar": False,
        "column_height": 400,
    }
    values.update(options)
    board = CTkKanbanBoard(root, **values)
    board.pack(fill="both", expand=True)
    root.update_idletasks()
    return board


def test_one_change_callback_contains_current_snapshot(tk_root: Any) -> None:
    events: list[dict[str, Any]] = []
    board = make_board(tk_root, on_change=events.append)

    board.move_card(1, "done")

    assert len(events) == 1
    assert events[0]["type"] == "card_moved"
    assert events[0]["data"] == board.get_data()
    assert board.get_card(1)["column"] == "done"

    board.move_card(1, "done")
    assert len(events) == 1


def test_invalid_initial_data_does_not_leave_an_orphan_widget(tk_root: Any) -> None:
    before = set(tk_root.winfo_children())

    with pytest.raises(ValueError, match="unknown column"):
        CTkKanbanBoard(
            tk_root,
            columns=[{"id": "todo", "title": "To do"}],
            cards=[{"id": 1, "column": "missing", "title": "Bad"}],
        )

    assert set(tk_root.winfo_children()) == before


def test_deleting_selected_cards_clears_selection(tk_root: Any) -> None:
    board = make_board(tk_root)
    board._select_card_widget(board._card_widgets[1])

    board.delete_column("todo", delete_cards=True)

    assert board.get_selected_card() is None


def test_priority_and_tags_render_as_colored_pills(tk_root: Any) -> None:
    board = make_board(
        tk_root,
        cards=[
            {
                "id": 1,
                "column": "todo",
                "title": "Styled",
                "priority": "High",
                "tags": ["design", "client"],
            }
        ],
    )
    card = board._card_widgets[1]

    assert card.priority_pill is not None
    assert card.priority_pill.cget("text") == "High"
    assert card.priority_pill.cget("fg_color") == board.theme["priority_high_color"]
    assert [pill.cget("text") for pill in card.tag_pills] == ["#design", "#client"]
    assert all(pill.cget("fg_color") in board.theme["tag_pill_colors"] for pill in card.tag_pills)


def test_card_body_selects_without_starting_drag(tk_root: Any) -> None:
    board = make_board(tk_root)
    card = board._card_widgets[1]

    # CustomTkinter renders label text through its internal Tk label; this is
    # the widget a real pointer event reaches.
    target = card.title_label._label
    target.event_generate("<ButtonPress-1>", x=2, y=2)
    target.event_generate("<ButtonRelease-1>", x=2, y=2)
    tk_root.update()

    assert board.get_selected_card()["id"] == 1
    assert board._drag_state is None


def test_real_drag_events_route_outside_the_handle_and_release(tk_root: Any) -> None:
    tk_root.geometry("760x520")
    tk_root.deiconify()
    board = make_board(tk_root)
    card = board._card_widgets[1]
    destination = board._column_widgets["done"]
    tk_root.update()
    start_x = card.drag_handle.winfo_rootx() + card.drag_handle.winfo_width() // 2
    start_y = card.drag_handle.winfo_rooty() + card.drag_handle.winfo_height() // 2
    target_x = destination.winfo_rootx() + 30
    target_y = destination.winfo_rooty() + 100
    source = card.drag_handle.winfo_containing(start_x, start_y)
    assert source is not None
    local_x = start_x - source.winfo_rootx()
    local_y = start_y - source.winfo_rooty()

    try:
        source.event_generate(
            "<ButtonPress-1>",
            x=local_x,
            y=local_y,
            rootx=start_x,
            rooty=start_y,
        )
        tk_root.update()
        assert tk_root.grab_current() == source

        source.event_generate(
            "<B1-Motion>",
            x=local_x,
            y=local_y,
            rootx=target_x,
            rooty=target_y,
            state=0x100,
        )
        tk_root.update()
        assert board._drag_state is not None
        assert board._drag_state.active
        assert board._drag_state.target_column == "done"

        source.event_generate(
            "<ButtonRelease-1>",
            x=local_x,
            y=local_y,
            rootx=target_x,
            rooty=target_y,
        )
        tk_root.update()
        assert board.get_card(1)["column"] == "done"
        assert board._drag_state is None
        assert tk_root.grab_current() is None
    finally:
        current = tk_root.grab_current()
        if current is not None:
            current.grab_release()
        tk_root.withdraw()


def test_drag_requires_threshold_and_commits_once_on_release(tk_root: Any) -> None:
    events: list[dict[str, Any]] = []
    board = make_board(tk_root, on_change=events.append)
    card = board._card_widgets[1]
    target = board._column_widgets["done"]
    start_x = card.drag_handle.winfo_rootx() + 2
    start_y = card.drag_handle.winfo_rooty() + 2

    board._on_drag_press(card, SimpleNamespace(x_root=start_x, y_root=start_y))
    board._on_drag_motion(card, SimpleNamespace(x_root=start_x + 2, y_root=start_y + 2))
    assert board._drag_state is not None
    assert not board._drag_state.active
    assert board.get_card(1)["column"] == "todo"

    target_x = target.winfo_rootx() + 20
    target_y = target.winfo_rooty() + 100
    board._on_drag_motion(card, SimpleNamespace(x_root=target_x, y_root=target_y))
    assert board._drag_state is not None
    assert board._drag_state.active
    assert board.get_card(1)["column"] == "todo"

    board._on_drag_release(card, SimpleNamespace(x_root=target_x, y_root=target_y))
    assert board.get_card(1)["column"] == "done"
    assert [event["type"] for event in events] == ["card_moved"]


def test_repeated_motion_over_one_drop_position_does_not_repaint(
    monkeypatch: Any,
    tk_root: Any,
) -> None:
    board = make_board(tk_root)
    card = board._card_widgets[1]
    target = board._column_widgets["done"]
    start_x = card.drag_handle.winfo_rootx() + 2
    start_y = card.drag_handle.winfo_rooty() + 2
    target_x = target.winfo_rootx() + 20
    target_y = target.winfo_rooty() + 100
    target_calls: list[bool] = []
    indicator_calls: list[int] = []
    original_target = target.set_drop_target
    original_indicator = target.show_drop_indicator

    def set_target(active: bool) -> None:
        target_calls.append(active)
        original_target(active)

    def show_indicator(index: int, *, excluding_id: Any | None = None) -> None:
        indicator_calls.append(index)
        original_indicator(index, excluding_id=excluding_id)

    monkeypatch.setattr(target, "set_drop_target", set_target)
    monkeypatch.setattr(target, "show_drop_indicator", show_indicator)
    board._on_drag_press(card, SimpleNamespace(x_root=start_x, y_root=start_y))

    for _ in range(20):
        board._on_drag_motion(card, SimpleNamespace(x_root=target_x, y_root=target_y))

    assert target_calls == [True]
    assert len(indicator_calls) == 1
    board._clear_drag_feedback()


def test_invalid_drop_does_not_mutate(tk_root: Any) -> None:
    events: list[dict[str, Any]] = []
    board = make_board(tk_root, on_change=events.append)
    card = board._card_widgets[1]
    x = card.winfo_rootx()
    y = card.winfo_rooty()

    board._on_drag_press(card, SimpleNamespace(x_root=x, y_root=y))
    board._on_drag_motion(card, SimpleNamespace(x_root=x - 100, y_root=y - 100))
    board._on_drag_release(card, SimpleNamespace(x_root=x - 100, y_root=y - 100))

    assert board.get_card(1)["column"] == "todo"
    assert events == []


def test_drop_cannot_target_a_clipped_offscreen_column(tk_root: Any) -> None:
    tk_root.geometry("400x500")
    tk_root.deiconify()
    board = make_board(
        tk_root,
        columns=[
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
            {"id": "c", "title": "C"},
        ],
        cards=[{"id": 1, "column": "a", "title": "One"}],
    )
    tk_root.update()
    card = board._card_widgets[1]
    clipped_column = board._column_widgets["c"]
    canvas = board.board_area._parent_canvas
    target_x = clipped_column.winfo_rootx() + 20
    target_y = clipped_column.winfo_rooty() + 100
    assert target_x > canvas.winfo_rootx() + canvas.winfo_width()

    board._on_drag_press(
        card,
        SimpleNamespace(x_root=card.winfo_rootx(), y_root=card.winfo_rooty()),
    )
    board._on_drag_motion(card, SimpleNamespace(x_root=target_x, y_root=target_y))
    board._on_drag_release(card, SimpleNamespace(x_root=target_x, y_root=target_y))

    assert board.get_card(1)["column"] == "a"
    assert board._drag_state is None
    tk_root.withdraw()


def test_search_only_changes_the_view(tk_root: Any) -> None:
    board = make_board(tk_root, show_toolbar=True)
    original = board.get_data()

    board.search("two")

    assert board.search_entry.get() == "two"
    assert set(board._card_widgets) == {2}
    assert board.get_data() == original
    card = board._card_widgets[2]
    board._on_drag_press(card, SimpleNamespace(x_root=0, y_root=0))
    assert board._drag_state is None


def test_edit_button_to_save_updates_the_board_from_one_embedded_drawer(tk_root: Any) -> None:
    events: list[dict[str, Any]] = []
    board = make_board(tk_root, on_change=events.append)
    original_columns = dict(board._column_widgets)
    untouched_card = board._card_widgets[2]

    board._card_widgets[1].edit_button.invoke()
    tk_root.update_idletasks()
    editors = [widget for widget in descendants(board) if isinstance(widget, CardEditor)]
    assert len(editors) == 1
    editor = editors[0]
    assert editor.master is board
    assert board._editor is editor
    editor.title_entry.delete(0, "end")
    editor.title_entry.insert(0, "Edited through the drawer")
    editor._column_var.set("Done")
    editor.save_button.invoke()
    tk_root.update_idletasks()

    assert board.get_card(1)["title"] == "Edited through the drawer"
    assert board.get_card(1)["column"] == "done"
    assert board._column_widgets == original_columns
    assert board._card_widgets[2] is untouched_card
    assert [event["type"] for event in events] == ["card_updated"]
    assert board._editor is None
    assert not editor.winfo_exists()


def test_opening_another_editor_replaces_the_existing_drawer(tk_root: Any) -> None:
    board = make_board(tk_root)

    board.open_edit_card_editor(1)
    first = board._editor
    assert first is not None
    board.open_edit_card_editor(2)

    assert not first.winfo_exists()
    assert board._editor is not None
    assert board._editor is not first
    assert len([widget for widget in descendants(board) if isinstance(widget, CardEditor)]) == 1


def test_add_editor_rejects_a_stale_column_id(tk_root: Any) -> None:
    board = make_board(tk_root)

    with pytest.raises(ValueError, match="unknown column"):
        board.open_add_card_editor("missing")


def test_card_menu_move_fallback_invokes_the_public_move(monkeypatch: Any, tk_root: Any) -> None:
    captured: list[tk.Menu] = []
    board = make_board(tk_root)
    monkeypatch.setattr(board, "_popup_menu", lambda menu, _button: captured.append(menu))

    board._show_card_menu(board._card_widgets[1])

    menu = captured[0]
    move_menu = menu.nametowidget(menu.entrycget(3, "menu"))
    done_index = next(
        index
        for index in range(move_menu.index("end") + 1)
        if move_menu.entrycget(index, "label") == "Done"
    )
    move_menu.invoke(done_index)
    menu.destroy()
    assert board.get_card(1)["column"] == "done"


def test_repeated_menu_use_keeps_a_bounded_widget_count(monkeypatch: Any, tk_root: Any) -> None:
    board = make_board(tk_root)
    monkeypatch.setattr(tk.Menu, "tk_popup", lambda self, x, y: None)

    for _ in range(10):
        board._show_card_menu(board._card_widgets[1])

    assert len([widget for widget in descendants(board) if isinstance(widget, tk.Menu)]) == 2
    board._destroy_active_menu()
    assert not [widget for widget in descendants(board) if isinstance(widget, tk.Menu)]


def test_refresh_preserves_viewports_and_global_binding_count(tk_root: Any) -> None:
    baseline_bindings = binding_count(tk_root, "<MouseWheel>")
    columns = [{"id": f"c{index}", "title": f"Column {index}"} for index in range(8)]
    cards = [
        {"id": index, "column": "c7", "title": f"Card {index:02d}"}
        for index in range(30)
    ]
    tk_root.geometry("720x500")
    tk_root.deiconify()
    board = make_board(
        tk_root,
        columns=columns,
        cards=cards,
        column_height=330,
    )
    tk_root.update()
    body_canvas = board._column_widgets["c7"].body._parent_canvas
    board_canvas = board.board_area._parent_canvas
    body_canvas.yview_moveto(1.0)
    board_canvas.xview_moveto(1.0)
    tk_root.update_idletasks()
    before_y = body_canvas.yview()[0]
    before_x = board_canvas.xview()[0]
    active_bindings = binding_count(tk_root, "<MouseWheel>")
    binding_ids = {
        func_id
        for frame in [
            board.board_area,
            *(column.body for column in board._column_widgets.values()),
        ]
        for _sequence, func_id in frame._managed_global_bindings
    }

    try:
        for suffix in ("one", "two", "three"):
            board.update_card(29, {"title": f"Same size {suffix}"})
        tk_root.update_idletasks()
        after_y = board._column_widgets["c7"].body._parent_canvas.yview()[0]
        after_x = board.board_area._parent_canvas.xview()[0]

        assert after_y == pytest.approx(before_y, abs=0.02)
        assert after_x == pytest.approx(before_x, abs=0.02)
        assert binding_count(tk_root, "<MouseWheel>") == active_bindings
    finally:
        board.destroy()
        tk_root.withdraw()

    assert binding_count(tk_root, "<MouseWheel>") == baseline_bindings
    assert binding_ids.isdisjoint(set(tk_root._tclCommands or ()))
