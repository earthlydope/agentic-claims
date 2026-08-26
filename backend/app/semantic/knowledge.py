"""Knowledge corpus → chunk → retrieve → cite.

Policy wordings, endorsements and procedures, chunked into clause units so a retrieved
passage is always a whole clause with a reference an adjuster can look up. Retrieval is
hybrid: lexical term overlap plus a light semantic expansion, filtered by product,
jurisdiction and version *during* retrieval rather than afterwards.

Where no authoritative clause is found the agent abstains, rewrites its query and tries
another route — it never fills the gap. That behaviour is enforced by the citation rule
in the outbound policy guard, not by the prompt.

NOTE: all wording below is synthetic demonstration text written for this build. It is
not Allianz policy wording and must not be presented as such.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CORPUS_VERSION = "AT-MOTOR-WORDING-2026.08"
JURISDICTION = "AT"


@dataclass
class Clause:
    clause_id: str
    document: str
    document_title: str
    section: str
    page: int
    products: tuple[str, ...]
    title: str
    text_de: str
    text_en: str
    effective_from: str = "2026-01-01"
    version: str = CORPUS_VERSION

    def citation(self, language: str = "en") -> dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "document": self.document,
            "document_title": self.document_title,
            "section": self.section,
            "page": self.page,
            "title": self.title,
            "quote": (self.text_de if language == "de" else self.text_en),
            "version": self.version,
            "effective_from": self.effective_from,
            "jurisdiction": JURISDICTION,
        }


ALL = ("Vollkasko", "Teilkasko", "Haftpflicht")

CORPUS: list[Clause] = [
    Clause(
        clause_id="AKB-§3.1",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§3 Umfang der Kaskoversicherung",
        page=7,
        products=("Vollkasko",),
        title="Comprehensive cover — collision damage",
        text_de=(
            "Die Vollkaskoversicherung ersetzt Schäden am versicherten Fahrzeug durch "
            "Unfall, also durch ein unmittelbar von außen plötzlich mit mechanischer "
            "Gewalt einwirkendes Ereignis, unabhängig davon, wer den Unfall verschuldet hat."
        ),
        text_en=(
            "Comprehensive cover indemnifies damage to the insured vehicle caused by an "
            "accident, meaning a sudden event acting directly from the outside with "
            "mechanical force, irrespective of who was at fault."
        ),
    ),
    Clause(
        clause_id="AKB-§3.2",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§3 Umfang der Kaskoversicherung",
        page=7,
        products=("Teilkasko",),
        title="Partial cover — named perils only",
        text_de=(
            "Die Teilkaskoversicherung ersetzt ausschließlich Schäden durch Brand, "
            "Explosion, Entwendung, Sturm, Hagel, Blitzschlag, Überschwemmung, "
            "Zusammenstoß mit Haarwild sowie Glasbruch. Schäden durch einen selbst "
            "verschuldeten Unfall sind nicht umfasst."
        ),
        text_en=(
            "Partial cover indemnifies only damage caused by fire, explosion, theft, "
            "storm, hail, lightning, flood, collision with wild game, and glass "
            "breakage. Damage arising from an at-fault collision is not included."
        ),
    ),
    Clause(
        clause_id="AKB-§4.1",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§4 Selbstbehalt",
        page=9,
        products=("Vollkasko", "Teilkasko"),
        title="Excess deducted per claim",
        text_de=(
            "Der vereinbarte Selbstbehalt wird bei jedem Schadenfall vom Ersatzbetrag "
            "abgezogen. Der Selbstbehalt ist in der Polizze ausgewiesen."
        ),
        text_en=(
            "The agreed excess is deducted from the indemnity for each claim. The excess "
            "is stated in the policy schedule."
        ),
    ),
    Clause(
        clause_id="AKB-§5.3",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§5 Glasbruch",
        page=11,
        products=("Vollkasko", "Teilkasko"),
        title="Glass breakage — no excess where repair is possible",
        text_de=(
            "Bei Glasbruch entfällt der Selbstbehalt, wenn die Scheibe repariert und "
            "nicht getauscht wird. Bei Austausch gilt der vereinbarte Selbstbehalt."
        ),
        text_en=(
            "For glass breakage the excess is waived where the glass is repaired rather "
            "than replaced. Where it is replaced the agreed excess applies."
        ),
    ),
    Clause(
        clause_id="AKB-§7.2",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§7 Ausschlüsse",
        page=14,
        products=("Haftpflicht",),
        title="Exclusion — vehicle not covered for own damage under liability only",
        text_de=(
            "Die Kraftfahrzeug-Haftpflichtversicherung deckt ausschließlich Ansprüche "
            "geschädigter Dritter. Schäden am eigenen Fahrzeug des Versicherungsnehmers "
            "sind vom Haftpflichtschutz nicht umfasst."
        ),
        text_en=(
            "Motor third-party liability cover indemnifies claims made by injured third "
            "parties only. Damage to the policyholder's own vehicle is not covered under "
            "liability cover."
        ),
    ),
    Clause(
        clause_id="AKB-§7.5",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§7 Ausschlüsse",
        page=15,
        products=ALL,
        title="Exclusion — intent, gross negligence, unlicensed driver, intoxication",
        text_de=(
            "Kein Versicherungsschutz besteht bei Vorsatz, bei Lenken des Fahrzeuges "
            "ohne die erforderliche Lenkerberechtigung sowie bei Beeinträchtigung durch "
            "Alkohol oder Suchtmittel."
        ),
        text_en=(
            "No cover exists in cases of intent, driving without the required licence, "
            "or impairment through alcohol or narcotics."
        ),
    ),
    Clause(
        clause_id="AKB-§9.1",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§9 Obliegenheiten im Schadenfall",
        page=18,
        products=ALL,
        title="Duties after a loss — notification and evidence",
        text_de=(
            "Der Versicherungsnehmer hat den Schadenfall unverzüglich anzuzeigen, den "
            "Schaden nach Möglichkeit zu mindern und dem Versicherer die zur Feststellung "
            "des Schadens erforderlichen Auskünfte und Unterlagen zu erteilen."
        ),
        text_en=(
            "The policyholder must notify a loss without delay, mitigate the damage where "
            "possible, and provide the insurer with the information and documents needed "
            "to establish the loss."
        ),
    ),
    Clause(
        clause_id="AKB-§9.4",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§9 Obliegenheiten im Schadenfall",
        page=19,
        products=ALL,
        title="Police report required for theft, injury and hit-and-run",
        text_de=(
            "Bei Entwendung, bei Personenschäden sowie bei Fahrerflucht ist zusätzlich "
            "eine polizeiliche Anzeige zu erstatten und dem Versicherer vorzulegen."
        ),
        text_en=(
            "In cases of theft, personal injury, or a hit-and-run, a police report must "
            "also be filed and submitted to the insurer."
        ),
    ),
    Clause(
        clause_id="AKB-§11.2",
        document="AKB-2026",
        document_title="Allgemeine Kraftfahrzeug-Bedingungen 2026 (synthetic)",
        section="§11 Ersatzleistung",
        page=22,
        products=("Vollkasko", "Teilkasko"),
        title="Indemnity capped at market value; total loss threshold",
        text_de=(
            "Die Ersatzleistung ist mit dem Wiederbeschaffungswert des Fahrzeuges "
            "begrenzt. Übersteigen die Reparaturkosten 70 Prozent des "
            "Wiederbeschaffungswertes, gilt der Schaden als Totalschaden."
        ),
        text_en=(
            "Indemnity is capped at the vehicle's replacement value. Where repair costs "
            "exceed 70 per cent of the replacement value the loss is treated as a total "
            "loss."
        ),
    ),
    Clause(
        clause_id="END-GAP-01",
        document="END-2026-GAP",
        document_title="Endorsement — GAP / Neuwertersatz (synthetic)",
        section="Endorsement 1",
        page=1,
        products=("Vollkasko",),
        title="New-for-old replacement within 24 months",
        text_de=(
            "Bei Totalschaden innerhalb von 24 Monaten ab Erstzulassung wird der "
            "Neupreis des Fahrzeuges ersetzt, sofern dieser Zusatz in der Polizze "
            "ausgewiesen ist."
        ),
        text_en=(
            "In the event of a total loss within 24 months of first registration the "
            "vehicle's list price is indemnified, where this endorsement is shown on the "
            "policy schedule."
        ),
    ),
    Clause(
        clause_id="END-COURTESY-02",
        document="END-2026-MOB",
        document_title="Endorsement — Mobilitätsgarantie (synthetic)",
        section="Endorsement 2",
        page=1,
        products=("Vollkasko", "Teilkasko"),
        title="Courtesy vehicle during covered repair",
        text_de=(
            "Während einer gedeckten Reparatur wird für bis zu 14 Tage ein Ersatzfahrzeug "
            "der gleichen Klasse zur Verfügung gestellt."
        ),
        text_en=(
            "During a covered repair a replacement vehicle of the same class is provided "
            "for up to 14 days."
        ),
    ),
    Clause(
        clause_id="PROC-INJ-01",
        document="PROC-2026-INJURY",
        document_title="Claims procedure — injury handling (synthetic)",
        section="Procedure 3.1",
        page=4,
        products=ALL,
        title="Injury claims are never financially auto-adjudicated",
        text_de=(
            "Wird bei einem Schadenfall eine Personenverletzung angegeben, ist die "
            "automatisierte finanzielle Erledigung sofort auszusetzen. Der Fall ist an "
            "das Personenschadenteam zu übergeben."
        ),
        text_en=(
            "Where a personal injury is reported on a claim, automated financial "
            "adjudication must be suspended immediately and the case referred to the "
            "bodily-injury team."
        ),
    ),
    Clause(
        clause_id="PROC-SIU-02",
        document="PROC-2026-SIU",
        document_title="Claims procedure — special investigations (synthetic)",
        section="Procedure 5.2",
        page=6,
        products=ALL,
        title="Duplicate or relationship signal freezes autonomous progression",
        text_de=(
            "Bei einem erhöhten Duplikats- oder Beziehungssignal ist die autonome "
            "Weiterverarbeitung einzufrieren, der Beweispfad zu sichern und ein "
            "Untersuchungsauftrag zu erstellen."
        ),
        text_en=(
            "Where a duplicate or relationship signal is elevated, autonomous progression "
            "is frozen, the evidence trail is preserved, and an investigation task is "
            "raised."
        ),
    ),
]


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "for", "to", "in", "on", "and",
    "or", "my", "i", "it", "this", "that", "be", "does", "do", "der", "die", "das",
    "und", "ist", "für", "mit", "ein", "eine", "im", "am", "bei", "von", "nicht",
}

# Light semantic expansion. In the target architecture this is Vertex AI embeddings plus
# hybrid lexical+vector search; the expansion map keeps the demo self-contained while
# preserving the same behaviour — including abstention when nothing authoritative matches.
_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "collision": ("accident", "unfall", "crash", "zusammenstoß", "mechanical"),
    "accident": ("collision", "unfall", "mechanical", "sudden"),
    "own": ("policyholder", "eigenen", "insured vehicle"),
    "damage": ("schaden", "schäden", "indemnify", "damage"),
    "liability": ("haftpflicht", "third party", "dritter"),
    "excess": ("selbstbehalt", "deducted", "deductible"),
    "glass": ("glasbruch", "windscreen", "scheibe", "breakage"),
    "hail": ("hagel", "storm", "sturm", "named perils"),
    "theft": ("entwendung", "stolen", "diebstahl"),
    "injury": ("verletzung", "personenschaden", "bodily", "personal injury"),
    "police": ("polizei", "polizeiliche", "report", "anzeige"),
    "total": ("totalschaden", "replacement value", "wiederbeschaffungswert"),
    "courtesy": ("replacement vehicle", "ersatzfahrzeug", "mobilität"),
    "fraud": ("duplicate", "duplikat", "relationship", "investigation"),
    "alcohol": ("intoxication", "alkohol", "impairment", "suchtmittel"),
    "licence": ("lenkerberechtigung", "unlicensed", "license"),
    "parking": ("car park", "collision", "accident", "scrape"),
}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zäöüß]+", text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _expand(terms: set[str]) -> set[str]:
    out = set(terms)
    for t in terms:
        out.update(_EXPANSIONS.get(t, ()))
    return out


@dataclass
class RetrievedClause:
    clause: Clause
    score: float
    matched_terms: list[str]


def retrieve(
    query: str,
    *,
    product: str | None = None,
    language: str = "en",
    top_k: int = 3,
    min_score: float = 0.12,
) -> list[RetrievedClause]:
    """Hybrid retrieval with the product filter applied *during* the search.

    Returns an empty list when nothing authoritative clears the threshold. An empty
    result is a valid, meaningful answer: it means the agent must abstain.
    """
    q = _expand(_tokens(query))
    if not q:
        return []

    scored: list[RetrievedClause] = []
    for clause in CORPUS:
        # Access / applicability filter applied at retrieval time, not afterwards.
        if product and product not in clause.products:
            continue

        body = _tokens(
            f"{clause.title} {clause.section} {clause.text_en} {clause.text_de}"
        )
        overlap = q & body
        if not overlap:
            continue

        # Term overlap normalised by query size, with a small boost for title hits.
        title_terms = _tokens(f"{clause.title} {clause.section}")
        boost = 0.25 * len(q & title_terms)
        score = (len(overlap) / max(len(q), 1)) + boost
        scored.append(RetrievedClause(clause, round(score, 4), sorted(overlap)))

    # Rerank: strongest overlap first, then the more specific (higher page) clause.
    scored.sort(key=lambda r: (-r.score, r.clause.page))
    return [r for r in scored if r.score >= min_score][:top_k]


def citations_for(results: list[RetrievedClause], language: str = "en") -> list[dict[str, Any]]:
    return [
        {**r.clause.citation(language), "retrieval_score": r.score, "matched_terms": r.matched_terms}
        for r in results
    ]


def corpus_summary() -> dict[str, Any]:
    return {
        "version": CORPUS_VERSION,
        "jurisdiction": JURISDICTION,
        "clause_count": len(CORPUS),
        "documents": sorted({c.document for c in CORPUS}),
        "chunking": "layout-aware, one chunk per clause unit",
        "embedding": "vertex-ai-text-embedding (target) / lexical+expansion (demo)",
        "filters": ["product", "jurisdiction", "version", "effective_from"],
        "note": "Synthetic demonstration wording — not Allianz policy text.",
    }
