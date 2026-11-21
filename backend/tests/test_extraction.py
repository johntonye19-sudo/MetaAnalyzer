"""Extraction test fixtures use synthetic local files only."""

import json
from pathlib import Path
import zipfile

import pytest

from app.evidence.extraction import ExtractionFailure, extract_metadata, identify_file


def test_json_extraction_uses_content_and_not_client_claim(tmp_path: Path) -> None:
    path = tmp_path / "actual.json"
    path.write_text(json.dumps({"case": "synthetic", "count": 2}), encoding="utf-8")
    result = extract_metadata(path, "renamed.exe")
    assert result["values"]["identification"]["kind"] == "unsupported"
    assert result["status"] in {"completed", "completed_with_warnings"}
    # Extension claims are not treated as actual content identification.
    assert "content" in result["values"]


def test_json_file_detects_valid_json_and_records_keys(tmp_path: Path) -> None:
    path = tmp_path / "fixture.json"
    path.write_text('{"synthetic": true, "items": [1, 2]}', encoding="utf-8")
    result = extract_metadata(path, "fixture.json")
    assert result["values"]["identification"]["kind"] == "json"
    assert result["values"]["content"]["top_level_keys"] == ["synthetic", "items"]


def test_eml_header_parser_preserves_received_chain_without_geolocation(tmp_path: Path) -> None:
    path = tmp_path / "message.eml"
    path.write_text("From: sender@example.test\nTo: recipient@example.test\nSubject: Synthetic\nReceived: from host.example.test\n\nBody", encoding="utf-8")
    result = extract_metadata(path, "message.eml")
    headers = result["values"]["content"]["headers"]
    assert headers["subject"] == ["Synthetic"]
    assert headers["received"] == ["from host.example.test"]
    assert "physical sender location" in result["values"]["content"]["note"]


def test_archive_inspection_does_not_extract_members(tmp_path: Path) -> None:
    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("safe/file.txt", "synthetic")
        archive.writestr("../escape.txt", "not extracted")
    result = extract_metadata(archive_path, "sample.zip")
    content = result["values"]["content"]
    assert content["member_count"] == 2
    assert any("unsafe" in warning for warning in result["warnings"])
    assert not (tmp_path / "escape.txt").exists()


def test_signature_identification_overrides_mismatched_extension(tmp_path: Path) -> None:
    path = tmp_path / "image.bin"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"synthetic")
    assert identify_file(path, "image.exe")["kind"] == "image"
