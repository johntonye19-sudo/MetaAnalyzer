"""Bounded metadata extraction for untrusted evidence files.

Extractors never execute evidence, follow URLs, or write extracted content. Optional
libraries and command-line tools are detected at runtime; unavailable tools are
reported as limitations rather than represented as successful extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from typing import Any
import xml.etree.ElementTree as ET

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 20_000
MAX_ARCHIVE_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
MAX_NETWORK_PACKETS = 100_000
EXIFTOOL_TIMEOUT_SECONDS = 20
MEDIAINFO_TIMEOUT_SECONDS = 20


class ExtractionFailure(Exception):
    """An extraction failure that is safe to show as a processing limitation."""


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _read_prefix(path: Path, size: int = 32) -> bytes:
    with path.open("rb") as source:
        return source.read(size)


def identify_file(path: Path, original_filename: str) -> dict[str, Any]:
    """Classify by known signatures first, using extension only as a weak hint."""
    prefix = _read_prefix(path)
    ext = Path(original_filename).suffix.lower()
    signatures: list[tuple[bytes, str, str]] = [
        (b"\xff\xd8\xff", "image", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", "image", "image/png"),
        (b"GIF87a", "image", "image/gif"), (b"GIF89a", "image", "image/gif"),
        (b"II*\x00", "image", "image/tiff"), (b"MM\x00*", "image", "image/tiff"),
        (b"BM", "image", "image/bmp"), (b"RIFF", "container", "application/octet-stream"),
        (b"%PDF-", "pdf", "application/pdf"),
        (b"PK\x03\x04", "zip_container", "application/zip"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole_document", "application/x-ole-storage"),
    ]
    for signature, kind, mime in signatures:
        if prefix.startswith(signature):
            if kind == "container":
                if ext in {".webp"} and prefix[8:12] == b"WEBP":
                    return {"kind": "image", "mime_type": "image/webp", "confidence": "signature"}
                if ext in {".wav", ".avi"}:
                    return {"kind": "media", "mime_type": mime, "confidence": "container-signature"}
                if ext in {".mp4", ".mov", ".m4a", ".aac", ".flac", ".ogg", ".mp3", ".mkv", ".webm"}:
                    return {"kind": "media", "mime_type": mime, "confidence": "container-signature"}
            if kind == "zip_container":
                if ext == ".docx":
                    return {"kind": "docx", "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "confidence": "container-signature"}
                if ext == ".xlsx":
                    return {"kind": "xlsx", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "confidence": "container-signature"}
                if ext == ".pptx":
                    return {"kind": "pptx", "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "confidence": "container-signature"}
                if ext in {".zip", ".cbz", ".odt", ".ods", ".odp"}:
                    return {"kind": "archive", "mime_type": mime, "confidence": "signature"}
            return {"kind": kind, "mime_type": mime, "confidence": "signature"}
    if ext in {".eml"}:
        return {"kind": "email", "mime_type": "message/rfc822", "confidence": "extension-only"}
    if ext in {".pcap", ".pcapng"}:
        return {"kind": "network_capture", "mime_type": "application/vnd.tcpdump.pcap", "confidence": "extension-only"}
    if ext in {".html", ".htm"}:
        return {"kind": "html", "mime_type": "text/html", "confidence": "extension-only"}
    if ext in {".xml"}:
        return {"kind": "xml", "mime_type": "application/xml", "confidence": "extension-only"}
    if ext in {".json"}:
        return {"kind": "json", "mime_type": "application/json", "confidence": "extension-only"}
    if ext in {".txt", ".csv", ".log"}:
        return {"kind": "text", "mime_type": "text/plain", "confidence": "extension-only"}
    if ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".heic", ".heif", ".dng", ".cr2", ".nef", ".arw"}:
        return {"kind": "image", "mime_type": None, "confidence": "extension-only"}
    if ext == ".pdf":
        return {"kind": "pdf", "mime_type": None, "confidence": "extension-only"}
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"}:
        return {"kind": "media", "mime_type": None, "confidence": "extension-only"}
    return {"kind": "unsupported", "mime_type": None, "confidence": "unknown"}


class _HTMLMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.in_title = False
        self.meta: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            self.meta.append({k: v or "" for k, v in attrs if k.lower() in {"name", "property", "content", "http-equiv"}})

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title and data.strip():
            self.title.append(data.strip())


def _extract_image(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        from PIL import Image, ExifTags
        import warnings
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as image:
            if image.width * image.height > 100_000_000:
                raise ExtractionFailure("Image exceeds the configured pixel limit")
            exif = image.getexif()
            named = {ExifTags.TAGS.get(tag, str(tag)): _json_value(value) for tag, value in exif.items()}
            info = {key: _json_value(value) for key, value in image.info.items() if isinstance(value, (str, int, float, bool, bytes))}
            result = {
                "format": image.format, "width": image.width, "height": image.height,
                "mode": image.mode, "exif": named, "embedded_info": info,
            }
        return result, []
    except ImportError:
        return {}, ["Pillow is not installed; image dimensions and EXIF were not extracted."]
    except ExtractionFailure:
        raise
    except Exception as exc:
        return {}, [f"Image parser could not safely read this file ({type(exc).__name__})."]


def _extract_pdf(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        import fitz
        with fitz.open(path) as document:
            metadata = document.metadata or {}
            return {"page_count": document.page_count, "metadata": _json_value(metadata), "encrypted": document.is_encrypted}, []
    except ImportError:
        return {}, ["PyMuPDF is not installed; PDF document properties were not extracted."]
    except Exception as exc:
        return {}, [f"PDF parser could not read this file ({type(exc).__name__})."]


def _extract_office(path: Path, kind: str) -> tuple[dict[str, Any], list[str]]:
    try:
        if kind == "docx":
            from docx import Document
            document = Document(path)
            props = document.core_properties
            return {"paragraph_count": len(document.paragraphs), "section_count": len(document.sections),
                    "properties": {name: _json_value(getattr(props, name)) for name in ("author", "title", "subject", "keywords", "comments", "created", "modified", "last_modified_by", "revision", "identifier", "language", "category")}}, []
        if kind == "xlsx":
            import openpyxl
            workbook = openpyxl.load_workbook(path, read_only=True, data_only=False)
            props = workbook.properties
            result = {"sheet_names": workbook.sheetnames, "properties": {name: _json_value(getattr(props, name)) for name in ("creator", "title", "subject", "description", "keywords", "created", "modified", "lastModifiedBy", "revision")}}
            workbook.close()
            return result, []
        from pptx import Presentation
        presentation = Presentation(path)
        props = presentation.core_properties
        return {"slide_count": len(presentation.slides), "properties": {name: _json_value(getattr(props, name)) for name in ("author", "title", "subject", "keywords", "comments", "created", "modified", "last_modified_by", "revision")}}, []
    except ImportError:
        return {}, [f"The optional parser for {kind.upper()} files is not installed."]
    except Exception as exc:
        return {}, [f"{kind.upper()} parser could not read this file ({type(exc).__name__})."]


def _extract_email(path: Path) -> tuple[dict[str, Any], list[str]]:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return {}, ["Email exceeds the configured parsing limit; headers were not parsed."]
    try:
        with path.open("rb") as source:
            message = BytesParser(policy=policy.default).parse(source)
        names = {"from": "From", "to": "To", "cc": "Cc", "bcc": "Bcc", "subject": "Subject", "date": "Date", "message_id": "Message-ID"}
        headers = {key: [str(value) for value in message.get_all(header, [])] for key, header in names.items()}
        headers["received"] = [str(value) for value in message.get_all("Received", [])]
        headers["authentication_results"] = [str(value) for value in message.get_all("Authentication-Results", [])]
        return {"headers": headers, "note": "Header IP addresses are not evidence of physical sender location."}, []
    except Exception as exc:
        return {}, [f"Email parser could not read this file ({type(exc).__name__})."]


def _extract_archive(path: Path) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_ENTRIES:
                raise ExtractionFailure("Archive member count exceeds the configured safety limit")
            total = sum(member.file_size for member in members)
            if total > MAX_ARCHIVE_UNCOMPRESSED:
                raise ExtractionFailure("Archive declared uncompressed size exceeds the configured safety limit")
            unsafe = [m.filename for m in members if m.filename.startswith(("/", "\\")) or ".." in Path(m.filename.replace("\\", "/")).parts]
            if unsafe:
                warnings.append(f"{len(unsafe)} member path(s) appear unsafe; archive contents were not extracted.")
            return {"member_count": len(members), "declared_uncompressed_bytes": total,
                    "members": [{"name": m.filename, "size_bytes": m.file_size, "compressed_bytes": m.compress_size} for m in members[:1000]],
                    "truncated_member_listing": len(members) > 1000,
                    "note": "Archive entries were listed only; no member was extracted or executed."}, warnings
    except ExtractionFailure:
        raise
    except Exception as exc:
        return {}, [f"Archive directory could not be read ({type(exc).__name__})."]


def _extract_network(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        from scapy.all import IP, IPv6, TCP, UDP, DNS, DNSQR, PcapReader
    except ImportError:
        return {}, ["Scapy is not installed; PCAP packet analysis is unavailable."]
    protocol_counts: dict[str, int] = {}
    endpoints: dict[str, int] = {}
    dns_queries: list[str] = []
    packet_count = 0
    try:
        with PcapReader(str(path)) as capture:
            for packet in capture:
                packet_count += 1
                if packet_count > MAX_NETWORK_PACKETS:
                    return {"packet_count": packet_count - 1, "truncated": True, "protocol_counts": protocol_counts,
                            "top_endpoints": sorted(endpoints.items(), key=lambda item: item[1], reverse=True)[:50],
                            "dns_queries": dns_queries[:500]}, ["PCAP packet limit reached; remaining packets were not processed."]
                if IP in packet:
                    ip = packet[IP]
                    protocol_counts["IPv4"] = protocol_counts.get("IPv4", 0) + 1
                    endpoints[str(ip.src)] = endpoints.get(str(ip.src), 0) + 1
                    endpoints[str(ip.dst)] = endpoints.get(str(ip.dst), 0) + 1
                elif IPv6 in packet:
                    ip = packet[IPv6]
                    protocol_counts["IPv6"] = protocol_counts.get("IPv6", 0) + 1
                    endpoints[str(ip.src)] = endpoints.get(str(ip.src), 0) + 1
                    endpoints[str(ip.dst)] = endpoints.get(str(ip.dst), 0) + 1
                if TCP in packet:
                    protocol_counts["TCP"] = protocol_counts.get("TCP", 0) + 1
                if UDP in packet:
                    protocol_counts["UDP"] = protocol_counts.get("UDP", 0) + 1
                if DNS in packet and packet[DNS].qd and DNSQR in packet:
                    query = packet[DNSQR].qname
                    if isinstance(query, bytes):
                        query = query.decode("ascii", errors="replace")
                    if len(dns_queries) < 500:
                        dns_queries.append(str(query).rstrip("."))
        return {"packet_count": packet_count, "truncated": False, "protocol_counts": protocol_counts,
                "top_endpoints": sorted(endpoints.items(), key=lambda item: item[1], reverse=True)[:50],
                "dns_queries": dns_queries,
                "note": "Offline PCAP analysis only; no network traffic was captured or transmitted."}, []
    except Exception as exc:
        return {}, [f"PCAP parser could not read this capture ({type(exc).__name__})."]


def _extract_simple(path: Path, kind: str) -> tuple[dict[str, Any], list[str]]:
    if path.stat().st_size > MAX_TEXT_BYTES:
        return {}, ["Text content exceeds the configured parsing limit; content was not parsed."]
    raw = path.read_bytes()
    warnings: list[str] = []
    text = raw.decode("utf-8", errors="replace")
    if "\ufffd" in text:
        warnings.append("Text contains invalid UTF-8 bytes; replacement characters were used for display parsing.")
    if kind == "json":
        try:
            parsed = json.loads(text)
            return {"json_type": type(parsed).__name__, "top_level_keys": list(parsed.keys())[:500] if isinstance(parsed, dict) else None}, warnings
        except json.JSONDecodeError as exc:
            return {}, [f"JSON syntax is invalid at line {exc.lineno}, column {exc.colno}."]
    if kind == "html":
        parser = _HTMLMetadataParser()
        parser.feed(text)
        return {"title": " ".join(parser.title)[:2000], "meta_tags": parser.meta[:500], "note": "HTML was parsed as inert text; external resources were not fetched."}, warnings
    if kind == "xml":
        try:
            root = ET.fromstring(raw)
            return {"root_element": root.tag, "child_count": len(root), "note": "XML structure inspected; external entities and resources were not resolved."}, warnings
        except ET.ParseError as exc:
            return {}, [f"XML syntax is invalid: {exc.position}."]
    return {"text_bytes": len(raw), "line_count": text.count("\n") + (1 if text else 0), "preview": text[:500]}, warnings


def _run_optional_tool(command: list[str], timeout: int, tool_name: str) -> tuple[Any | None, str | None]:
    if not shutil.which(command[0]):
        return None, f"{tool_name} is not installed."
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout, check=False, shell=False,
                                   stdin=subprocess.DEVNULL, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"})
    except subprocess.TimeoutExpired:
        return None, f"{tool_name} exceeded the {timeout}-second processing timeout."
    except OSError as exc:
        return None, f"{tool_name} could not be started ({type(exc).__name__})."
    if len(completed.stdout) > MAX_TEXT_BYTES:
        return None, f"{tool_name} output exceeded the parsing size limit."
    if completed.returncode != 0:
        return None, f"{tool_name} could not parse this file (exit {completed.returncode})."
    try:
        return json.loads(completed.stdout), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, f"{tool_name} returned invalid JSON."


def extract_metadata(path: str | Path, original_filename: str) -> dict[str, Any]:
    """Extract structured metadata from a stored evidence file without modifying it."""
    path = Path(path)
    stat = path.stat()
    classification = identify_file(path, original_filename)
    kind = classification["kind"]
    warnings: list[str] = []
    values: dict[str, Any] = {
        "identification": classification,
        "filesystem": {
            "size_bytes": stat.st_size,
            "modified_time_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "note": "Filesystem timestamps describe the stored copy and are not assumed to be recording/original timestamps.",
        },
    }
    if kind == "image":
        extracted, notes = _extract_image(path)
    elif kind == "pdf":
        extracted, notes = _extract_pdf(path)
    elif kind in {"docx", "xlsx", "pptx"}:
        extracted, notes = _extract_office(path, kind)
    elif kind == "email":
        extracted, notes = _extract_email(path)
    elif kind == "network_capture":
        extracted, notes = _extract_network(path)
    elif kind in {"archive", "zip_container"}:
        extracted, notes = _extract_archive(path)
    elif kind in {"json", "xml", "html", "text"}:
        extracted, notes = _extract_simple(path, kind)
    else:
        extracted, notes = {}, ["Content format is unsupported or could not be identified; only filesystem properties and identification hints are available."]
    values["content"] = extracted
    warnings.extend(notes)

    exiftool, error = _run_optional_tool(["exiftool", "-json", "-G1", "-n", str(path)], EXIFTOOL_TIMEOUT_SECONDS, "ExifTool")
    if exiftool is not None:
        values["exiftool"] = exiftool[0] if isinstance(exiftool, list) and exiftool else exiftool
    else:
        warnings.append(error or "ExifTool metadata is unavailable.")
    if kind == "media":
        mediainfo, error = _run_optional_tool(["mediainfo", "--Output=JSON", str(path)], MEDIAINFO_TIMEOUT_SECONDS, "MediaInfo")
        if mediainfo is not None:
            values["mediainfo"] = mediainfo
        else:
            warnings.append(error or "MediaInfo metadata is unavailable.")
    return {
        "category": "extraction",
        "source": "MetaAnalyzer extraction engine",
        "tool_version": "0.2.0",
        "values": values,
        "warnings": warnings,
        "status": "completed_with_warnings" if warnings else "completed",
    }
