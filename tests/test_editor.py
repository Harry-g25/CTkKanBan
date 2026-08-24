"""Explicit-save behavior for the single card editor."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from ctk_kanban import Field
from ctk_kanban.dropdown import CTkDropdown
from ctk_kanban.editor import CardEditor


def test_save_collects_the_small_card_shape(tk_root: Any) -> None:
    saved: list[dict[str, Any]] = []
    editor = CardEditor(
        tk_root,
        title="Edit card",
        initial={"id": 1, "column": "todo", "title": "Before"},
        columns=[{"id": "todo", "title": "To do"}],
        on_save=lambda value: saved.append(value),
    )
    tk_root.update()
    assert isinstance(editor, ctk.CTkFrame)
    assert not isinstance(editor, ctk.CTkToplevel)
    assert editor.master is tk_root
    assert editor.place_info()
    editor.title_entry.delete(0, "end")
    editor.title_entry.insert(0, "After")
    editor.tags_entry.insert(0, "one, two")

    editor.save()

    assert saved == [
        {
            "title": "After",
            "description": "",
            "priority": "",
            "tags": ["one", "two"],
            "column": "todo",
        }
    ]
    assert not editor.winfo_exists()


def test_failed_save_stays_open_and_cancel_never_saves(tk_root: Any) -> None:
    calls: list[dict[str, Any]] = []
    editor = CardEditor(
        tk_root,
        title="Edit card",
        initial={"column": "todo", "title": "Before"},
        columns=[{"id": "todo", "title": "To do"}],
        on_save=lambda value: calls.append(value) or "Try again",
    )
    tk_root.update()

    editor.save()
    assert editor.winfo_exists()
    assert editor.error_label.cget("text") == "Try again"
    editor.close()

    assert len(calls) == 1
    assert not editor.winfo_exists()


def test_custom_field_schema_generates_typed_controls_and_values(tk_root: Any) -> None:
    saved: list[dict[str, Any]] = []
    editor = CardEditor(
        tk_root,
        title="Edit card",
        initial={
            "column": "todo",
            "title": "Flexible",
            "estimate": 3,
            "blocked": False,
            "stage": "Discovery",
        },
        columns=[{"id": "todo", "title": "To do"}],
        fields=[
            {"key": "title", "label": "Title", "type": "text"},
            {"key": "estimate", "label": "Estimate", "type": "integer"},
            {"key": "blocked", "label": "Blocked", "type": "checkbox"},
            {
                "key": "stage",
                "label": "Stage",
                "type": "select",
                "options": ["Discovery", "Delivery"],
            },
        ],
        on_save=lambda value: saved.append(value),
    )
    tk_root.update()

    editor._variables["estimate"].set("8")
    editor._variables["blocked"].set(True)
    editor._variables["stage"].set("Delivery")
    editor.save()

    assert saved == [
        {
            "title": "Flexible",
            "estimate": 8,
            "blocked": True,
            "stage": "Delivery",
            "column": "todo",
        }
    ]


def test_editor_controls_share_scaled_geometry_and_typography(tk_root: Any) -> None:
    tk_root.geometry("900x760")
    tk_root.deiconify()
    editor = CardEditor(
        tk_root,
        title="Add card",
        initial={
            "column": "todo",
            "title": "Consistent",
            "description": "Readable copy",
            "blocked": False,
            "stage": "Discovery",
            "tags": ["ui"],
        },
        columns=[{"id": "todo", "title": "To do"}],
        fields=[
            {"key": "title", "label": "Title", "type": "text", "section": "Details"},
            {
                "key": "description",
                "label": "Description",
                "type": "textarea",
                "section": "Details",
            },
            {
                "key": "stage",
                "label": "Stage",
                "type": "select",
                "options": ["Discovery", "Delivery"],
                "section": "Planning",
            },
            {
                "key": "blocked",
                "label": "Blocked",
                "type": "checkbox",
                "section": "Planning",
            },
            {"key": "tags", "label": "Tags", "type": "tags", "section": "Planning"},
        ],
        on_save=lambda _value: None,
        relative_width=1.0,
    )
    tk_root.update()

    title = editor._field_widgets["title"]
    stage = editor._field_widgets["stage"]
    blocked = editor._field_widgets["blocked"]
    expected_height = round(editor._apply_widget_scaling(editor.theme["input_height"]))

    assert isinstance(title, ctk.CTkEntry)
    assert isinstance(stage, CTkDropdown)
    assert isinstance(blocked, ctk.CTkCheckBox)
    assert title.winfo_height() == expected_height
    assert stage.winfo_height() == expected_height
    assert blocked.winfo_height() == expected_height
    assert editor.tags_entry.winfo_height() == expected_height
    assert editor.add_tag_button.winfo_height() == expected_height
    assert editor.cancel_button.winfo_height() == expected_height
    assert editor.save_button.winfo_height() == expected_height
    assert editor.cancel_button.winfo_width() == editor.save_button.winfo_width()
    assert title.cget("font").cget("size") == 13
    assert stage.cget("font").cget("size") == 13
    assert blocked.cget("font").cget("size") == 13
    assert editor._label_widgets
    assert all(isinstance(label, ctk.CTkLabel) for label in editor._label_widgets)
    assert editor._section_widgets
    assert all(isinstance(section, ctk.CTkFrame) for section in editor._section_widgets)
    assert all(
        section.cget("corner_radius") == editor.theme["editor_section_corner_radius"]
        for section in editor._section_widgets
    )
    editor.destroy()


def test_select_fields_use_the_widget_based_dropdown(tk_root: Any) -> None:
    editor = CardEditor(
        tk_root,
        title="Edit card",
        initial={"column": "todo", "title": "Flexible", "stage": "Discovery"},
        columns=[
            {"id": "todo", "title": "To do"},
            {"id": "done", "title": "Done"},
        ],
        fields=[
            {"key": "title", "label": "Title", "type": "text"},
            {
                "key": "stage",
                "label": "Stage",
                "type": "select",
                "options": ["Discovery", "Delivery"],
            },
        ],
        on_save=lambda _value: None,
    )
    tk_root.update()

    stage = editor._field_widgets["stage"]
    assert isinstance(stage, CTkDropdown)
    assert isinstance(editor.column_menu, CTkDropdown)
    stage._clicked()
    tk_root.update_idletasks()

    assert stage._popup is not None
    assert [
        button.cget("text") for button in stage._popup._entry_widgets.values()
    ] == ["None", "Discovery", "Delivery"]
    stage._popup.invoke(2)
    assert editor._variables["stage"].get() == "Delivery"
    editor.destroy()


def test_dropdown_content_does_not_overlap_its_border_or_clip(tk_root: Any) -> None:
    tk_root.geometry("500x220")
    tk_root.deiconify()
    dropdown = CTkDropdown(
        tk_root,
        values=["Compact", "Normal", "Large"],
        label_prefix="Cards: ",
        width=100,
        height=36,
    )
    dropdown.pack()
    tk_root.update()

    assert dropdown.winfo_width() > dropdown._apply_widget_scaling(100)
    assert dropdown._value_label.winfo_width() >= dropdown._value_label.winfo_reqwidth()
    assert dropdown._value_label.winfo_y() >= dropdown._apply_widget_scaling(4)
    assert (
        dropdown._value_label.winfo_y() + dropdown._value_label.winfo_height()
        <= dropdown.winfo_height() - dropdown._apply_widget_scaling(4)
    )

    dropdown._clicked()
    tk_root.update()
    assert dropdown._popup is not None
    expected_menu_height = sum(
        button.winfo_height() for button in dropdown._popup._entry_widgets.values()
    ) + dropdown._apply_widget_scaling(CTkDropdown.POPUP_PADDING_Y * 2)
    assert dropdown._popup.winfo_height() >= expected_menu_height
    assert dropdown._popup.winfo_rooty() == (
        dropdown.winfo_rooty() + dropdown.winfo_height() + 4
    )
    if dropdown.tk.call("tk", "windowingsystem") == "win32":
        assert str(dropdown._popup.wm_attributes("-transparentcolor")) == "#010203"
    dropdown.destroy()


def test_custom_title_field_is_the_editor_heading_input(tk_root: Any) -> None:
    saved: list[dict[str, Any]] = []
    editor = CardEditor(
        tk_root,
        title="Edit card",
        initial={"column": "todo", "summary": "Database title", "customer": "Acme"},
        columns=[{"id": "todo", "title": "To do"}],
        fields=[Field("summary").title(), "customer"],
        on_save=lambda value: saved.append(value),
    )
    tk_root.update()

    assert editor.title_entry is editor._field_widgets["summary"]
    editor.title_entry.delete(0, "end")
    editor.title_entry.insert(0, "Changed title")
    editor.save()

    assert saved == [
        {"summary": "Changed title", "customer": "Acme", "column": "todo"}
    ]
