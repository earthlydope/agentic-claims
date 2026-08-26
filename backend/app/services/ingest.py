"""Turning real files into claim evidence.

Document AI stands in here, but nothing about the path around it is simulated: an uploaded
file is preflighted, its text is extracted, each field carries its own confidence, and the
confidence decides whether the value is accepted, confirmed, re-asked or escalated.

The extraction is deliberately honest about what it cannot read. A plate rendered with a
letter O where a zero belongs is exactly the case that should come back as "confirm this"
rather than being silently promoted to a validated value.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.semantic.definitions import PANEL_CATALOGUE
from app.services.preflight import preflight_upload, recovery_action

MAX_TEXT_CHARS = 20_000


# --------------------------------------------------------------------------
# Text out of a PDF
# --------------------------------------------------------------------------
def extract_pdf(payload: bytes) -> tuple[str, int]:
    """Text and page count. A PDF we cannot read is a fact, not an exception."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
        pages = len(reader.pages)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return text[:MAX_TEXT_CHARS], pages
    except Exception as exc:  # noqa: BLE001 — an unreadable file is evidence too
        return f"[unreadable pdf: {type(exc).__name__}]", 1


# --------------------------------------------------------------------------
# How readable is a photo
# --------------------------------------------------------------------------
def assess_photo(payload: bytes) -> dict[str, Any]:
    """Score a photo on whether a panel edge could actually be measured from it.

    Sharpness is the variance of the edge response: a blurred photo has soft edges and so
    a low variance. Combined with exposure, because a correctly focused photo taken in the
    dark is just as unusable.
    """
    try:
        from PIL import Image, ImageFilter, ImageStat
    except ImportError:  # pragma: no cover
        return {"quality_score": 0.8, "detail": "Image inspection unavailable."}

    try:
        image = Image.open(io.BytesIO(payload))
        image.load()
    except Exception as exc:  # noqa: BLE001
        return {"quality_score": 0.0, "detail": f"Not a readable image: {exc}"[:120]}

    width, height = image.size
    grey = image.convert("L")

    edges = grey.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    sharpness = float(stat.stddev[0]) if stat.stddev else 0.0

    exposure = ImageStat.Stat(grey)
    mean = float(exposure.mean[0]) if exposure.mean else 0.0
    spread = float(exposure.stddev[0]) if exposure.stddev else 0.0

    # Calibrated so a clean daylight photo lands around 0.9 and a blurred low-light one
    # lands below the 0.55 re-ask threshold.
    sharp_score = min(1.0, sharpness / 26.0)
    exposure_score = 1.0 - min(1.0, abs(mean - 118.0) / 118.0)
    contrast_score = min(1.0, spread / 52.0)
    resolution_score = min(1.0, (width * height) / (1280 * 720))

    score = round(
        0.52 * sharp_score + 0.18 * exposure_score
        + 0.18 * contrast_score + 0.12 * resolution_score,
        2,
    )

    problems = []
    if sharp_score < 0.5:
        problems.append("the panel edges are not resolvable — the photo is soft")
    if mean < 62:
        problems.append("it is underexposed")
    if resolution_score < 0.4:
        problems.append("the resolution is too low to measure from")

    return {
        "quality_score": max(0.05, min(0.98, score)),
        "width": width,
        "height": height,
        "sharpness": round(sharpness, 1),
        "brightness": round(mean, 1),
        "problems": problems,
        "detail": (
            "Readable." if not problems
            else "Not readable: " + "; and ".join(problems) + "."
        ),
    }


# --------------------------------------------------------------------------
# What the text says
# --------------------------------------------------------------------------
PANEL_PATTERN = re.compile(
    r"\(([a-z_]+)\s*,\s*(repair|replace)\)", re.IGNORECASE
)

# Structural panels force complex severity, so a document naming one matters.
STRUCTURAL = {"a_pillar_left", "sill_left", "radiator_support", "airbag_module"}


def detect_panels(text: str) -> list[dict[str, Any]]:
    """Panel findings named in a repair document."""
    found: dict[str, dict[str, Any]] = {}
    for match in PANEL_PATTERN.finditer(text or ""):
        panel, action = match.group(1).lower(), match.group(2).lower()
        if panel not in PANEL_CATALOGUE:
            continue
        # A line that mentions paint gets painted; realigning without a repaint is common.
        window = (text[max(0, match.start() - 140) : match.end() + 60] or "").lower()
        paint = ("paint" in window or "lackier" in window) and "no repaint" not in window
        found[panel] = {
            "panel": panel,
            "action": action,
            "paint": bool(paint),
            "confidence": 0.93 if action == "replace" else 0.9,
            "structural": panel in STRUCTURAL,
        }
    return list(found.values())


AMBIGUOUS = re.compile(r"[O0Il1S5B8]")

FIELD_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("plate", re.compile(
        r"(?:Kennzeichen|Plate|Registration)[^A-Z0-9]{0,24}([A-Z]{1,2}[-\s][A-Z0-9]{2,6}\s?[A-Z]{0,3})")),
    ("vin", re.compile(r"(?:VIN|Fahrgestellnummer)[^A-Z0-9]{0,24}([A-Z0-9]{15,19})")),
    ("quote_total_eur", re.compile(
        r"(?:Gesamt inkl\.? USt|Total incl\.? VAT)[^0-9]{0,30}([0-9][0-9.,]+)")),
    ("police_report_ref", re.compile(r"(LPD-[A-Z]{2}-\d{4}-\d{4,8})")),
    ("at_fault_party", re.compile(r"at_fault_party[:\s]+([a-z_]+)")),
    ("injury_reported", re.compile(r"injury_reported[:\s]+(true|false)", re.IGNORECASE)),
    ("replacement_value_eur", re.compile(
        r"Wiederbeschaffungswert[^0-9]{0,24}([0-9][0-9.,]+)")),
    ("repairer_name", re.compile(r"^([A-Z][A-Za-z&.\s]{6,44}(?:GmbH|Nord|Sued|Süd|Innsbruck|Wien|Graz|Linz|Salzburg))",
                                 re.MULTILINE)),
]


def extract_fields(text: str, doc_type: str) -> list[dict[str, Any]]:
    """Pull the fields a claims handler would look for, each with its own confidence."""
    out: list[dict[str, Any]] = []
    body = text or ""

    for name, pattern in FIELD_RULES:
        match = pattern.search(body)
        if not match:
            continue
        value = match.group(1).strip()

        # Confidence is earned, not assumed. Characters that OCR routinely confuses are
        # the whole reason the confirm path exists.
        confidence = 0.96
        if name == "plate":
            # A plate is short and unverifiable, so an ambiguous character genuinely
            # warrants asking the customer to confirm what we read.
            risky = len(AMBIGUOUS.findall(value))
            confidence = round(max(0.55, 0.96 - 0.09 * risky), 2)
        elif name == "vin":
            # A VIN legitimately contains those characters and carries a check digit, so
            # the penalty is smaller and floors above the re-ask threshold.
            risky = len(AMBIGUOUS.findall(value))
            confidence = round(max(0.72, 0.95 - 0.015 * risky), 2)
        elif name in ("quote_total_eur", "replacement_value_eur"):
            confidence = 0.94
        elif name == "at_fault_party":
            confidence = 0.88
        elif name == "repairer_name":
            confidence = 0.93

        action = recovery_action(confidence)
        out.append({
            "field_name": name,
            "extracted_value": value,
            "validated_value": value if action == "accept" else None,
            "confidence": confidence,
            "recovery_action": action,
        })
    return out


def classify(filename: str, text: str) -> str:
    """What kind of document this is."""
    lowered = f"{filename} {text[:900]}".lower()
    if "polizei" in lowered or "police" in lowered or "lpd-" in lowered:
        return "police_report"
    if "rechnung" in lowered or "invoice" in lowered:
        return "invoice"
    if "kostenvoranschlag" in lowered or "quotation" in lowered or "quote" in lowered:
        return "repair_quote"
    if "gutachten" in lowered or "assessment" in lowered:
        return "assessor_report"
    return "document"


# --------------------------------------------------------------------------
@dataclass
class IngestedFile:
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    kind: str                      # photo | pdf
    doc_type: str
    page_count: int = 1
    quality_score: float = 0.9
    text: str = ""
    detections: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    preflight: dict[str, Any] = field(default_factory=dict)
    accepted: bool = True
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename, "mime_type": self.mime_type,
            "size_bytes": self.size_bytes, "sha256": self.sha256, "kind": self.kind,
            "doc_type": self.doc_type, "page_count": self.page_count,
            "quality_score": self.quality_score,
            "quality_action": recovery_action(self.quality_score),
            "text_chars": len(self.text),
            "detections": self.detections, "fields": self.fields,
            "preflight": self.preflight, "accepted": self.accepted, "notes": self.notes,
        }


PHOTO_MIME = {"image/jpeg", "image/jpg", "image/png", "image/heic", "image/webp"}


def ingest(
    filename: str,
    mime_type: str,
    payload: bytes,
    known_hashes: dict[str, str] | None = None,
) -> IngestedFile:
    """Read one uploaded file the way the platform would read it in production."""
    is_photo = (mime_type in PHOTO_MIME) or filename.lower().endswith(
        (".jpg", ".jpeg", ".png", ".heic", ".webp")
    )
    kind = "photo" if is_photo else "pdf"

    text, pages = ("", 1)
    quality = 0.9
    notes: list[str] = []
    detections: list[dict[str, Any]] = []

    if is_photo:
        assessment = assess_photo(payload)
        quality = float(assessment["quality_score"])
        notes.append(assessment["detail"])
        # A photo carries its panel in the filename or its caption; in production this is
        # the vision model's job.
        stem = filename.lower().replace("-", "_")
        for panel in PANEL_CATALOGUE:
            parts = panel.split("_")
            if panel in stem or all(part in stem for part in parts):
                detections.append({
                    "panel": panel,
                    "action": "replace" if "replace" in filename.lower() else "repair",
                    "paint": True,
                    "confidence": round(min(0.95, quality + 0.02), 2),
                    "structural": panel in STRUCTURAL,
                })
                break
    else:
        text, pages = extract_pdf(payload)
        detections = detect_panels(text)
        # A document's quality is how much of it we could actually read.
        quality = 0.95 if len(text) > 400 else 0.6 if len(text) > 80 else 0.3
        if quality < 0.7:
            notes.append("Little text could be extracted from this file.")

    doc_type = "photo" if is_photo else classify(filename, text)
    pre = preflight_upload(
        filename=filename, mime_type=mime_type or "application/octet-stream",
        payload=payload, page_count=pages, known_hashes=known_hashes,
    )
    notes.extend(pre.notes)

    return IngestedFile(
        filename=filename, mime_type=mime_type, size_bytes=len(payload),
        sha256=pre.sha256, kind=kind, doc_type=doc_type, page_count=pages,
        quality_score=quality, text=text, detections=detections,
        fields=extract_fields(text, doc_type) if not is_photo else [],
        preflight=pre.as_dict(), accepted=pre.accepted, notes=notes,
    )
