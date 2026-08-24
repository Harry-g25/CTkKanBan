"""Explicit-save behavior for the single card editor."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from ctk_kanban import Field
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
