#!/usr/bin/env python3
"""Tests for XML response parsing and unformatted-answer recovery (#142)."""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from file_processor import parse_plain_response, parse_xml_response
from tags import Xml

_BACKUP_DISABLED = {
    "enabled": False,
    "timestamp_format": "%Y%m%d%H%M%S",
    "extra_string": "thin-wrap",
    "overwrite_original": True,
}


def _closed_comments(body: str) -> str:
    return f"<{Xml.COMMENTS}>\n{body}\n</{Xml.COMMENTS}>"


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_well_formed_comments_are_extracted(_mock_backup):
    body = "Use anyhow at the CLI boundary."
    result = parse_xml_response(_closed_comments(body))
    assert result == body


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_plain_text_without_tags_is_returned(_mock_backup):
    raw = "Use anyhow at the CLI boundary.\n\nIt keeps main.rs small."
    result = parse_xml_response(raw)
    assert result == raw


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_unclosed_comments_tag_is_recovered(_mock_backup):
    body = (
        "La décision de passer d'un `anyhow::Error` générique à une "
        "énumération d'erreurs spécifique dépend de la nature du projet."
    )
    raw = f"<{Xml.COMMENTS}>\n{body}"
    result = parse_xml_response(raw)
    assert "No explanation" not in result
    assert "anyhow::Error" in result
    assert Xml.COMMENTS not in result


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_issue_142_conversation_reply_is_shown(_mock_backup):
    raw = (
        "<prompt_engineering_answer_comments>\n"
        "La décision de passer d'un `anyhow::Error` générique à une "
        "énumération d'erreurs spécifique (`enum MyError`) dépend de la "
        "nature du projet et de son public cible. Dans le cas précis de "
        "`fathom` (un outil de ligne de commande - CLI), voici l'analyse :\n"
        "\n"
        "### 1. Pourquoi `anyhow` est souvent préféré pour les CLIs "
        "(`main.rs`)\n"
        "\n"
        "Actuellement, l'utilisation de `anyhow` est une excellente "
        "pratique pour le point d'entrée d'une application :\n"
        "*   **Simplicité :** Vous n'avez pas besoin de définir une grande "
        "énumération pour chaque module.\n"
    )
    result = parse_xml_response(raw)
    assert "énumération d'erreurs spécifique" in result
    assert "### 1. Pourquoi" in result
    assert result.lstrip().startswith("La décision")


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_valid_edit_plus_leftover_text_applies_file_and_shows_text(
    _mock_backup, tmp_path
):
    target = tmp_path / "app.py"
    target.write_text("old\n", encoding="utf-8")
    leftover = "Keep anyhow for now; no code change is required."
    raw = (
        f"<{Xml.EDITED_FILES}>\n"
        f'<{Xml.EDITED_FILE} path="{target}">\n'
        "new\n"
        f"</{Xml.EDITED_FILE}>\n"
        f"</{Xml.EDITED_FILES}>\n"
        f"{leftover}\n"
    )
    result = parse_xml_response(raw)
    assert target.read_text(encoding="utf-8") == "new\n"
    assert leftover in result


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_empty_response_stays_empty(_mock_backup):
    raw = (
        f"<{Xml.EDITED_FILES}>\n</{Xml.EDITED_FILES}>\n"
        f"<{Xml.NEW_FILES}>\n</{Xml.NEW_FILES}>\n"
        f"<{Xml.COMMENTS}>\n</{Xml.COMMENTS}>\n"
    )
    assert parse_xml_response(raw) == ""


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_unclosed_edited_file_is_not_written(_mock_backup, tmp_path):
    target = tmp_path / "app.py"
    target.write_text("old\n", encoding="utf-8")
    raw = (
        f"<{Xml.EDITED_FILES}>\n"
        f'<{Xml.EDITED_FILE} path="{target}">\n'
        "should-not-be-written\n"
    )
    result = parse_xml_response(raw)
    assert target.read_text(encoding="utf-8") == "old\n"
    assert "should-not-be-written" in result


@patch("file_processor.config.backup", return_value=_BACKUP_DISABLED)
def test_fenced_closed_comments_are_extracted(_mock_backup):
    body = "Closed tags inside a markdown fence still parse."
    raw = f"```xml\n{_closed_comments(body)}\n```"
    result = parse_xml_response(raw)
    assert result == body


def test_parse_plain_response_returns_full_text():
    raw = "  just a free-chat answer  \n"
    assert parse_plain_response(raw) == "just a free-chat answer"
