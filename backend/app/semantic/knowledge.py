"""Policy wording, chunked one clause per chunk, retrieved with citations.

The wording below follows the Austrian standard-form motor conditions, which are filed
with the regulator under § 18 KHVG and published by every insurer:

  * **AKKB 2023** — Allgemeine Bedingungen für die Kraftfahrzeug-Kaskoversicherung
    (comprehensive and partial cover). Article numbering and structure as published.
  * **AKHB 2023** — Allgemeine Bedingungen für die Kraftfahrzeug-Haftpflichtversicherung
    (third-party liability), filed 06.12.2023, in force from 23.12.2023.
  * **AKKB (VAV variant)** — used for the two clauses where the market wording differs
    usefully: the parking-damage reporting duty and the recovery-cost cap.

Each clause is summarised faithfully in German and English with a short quotation, and
carries its real article reference so an adjuster can look it up. This is a demonstration
corpus built from public standard-form conditions — it is not a specific insurer's policy
document and must not be presented as one.

Retrieval is hybrid: term overlap plus a light semantic expansion, with the product filter
applied *during* the search rather than afterwards. Where nothing authoritative clears the
threshold the result is empty — and an empty result is a real answer. It means the agent
must abstain, which the citation rule in the outbound guard then enforces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CORPUS_VERSION = "AT-MOTOR-AKKB2023-AKHB2023"
JURISDICTION = "AT"

SOURCES: dict[str, dict[str, str]] = {
    "AKKB-2023": {
        "title": "Allgemeine Bedingungen für die Kraftfahrzeug-Kaskoversicherung (AKKB 2023)",
        "title_en": "General Conditions for Motor Own-Damage Insurance (AKKB 2023)",
        "basis": "Austrian standard-form conditions, as published by Austrian insurers.",
        "products": "Vollkasko, Teilkasko",
    },
    "AKHB-2023": {
        "title": "Allgemeine Bedingungen für die Kraftfahrzeug-Haftpflichtversicherung (AKHB 2023)",
        "title_en": "General Conditions for Motor Third-Party Liability Insurance (AKHB 2023)",
        "basis": (
            "Austrian standard-form conditions filed with the insurance supervisor on "
            "06.12.2023 under § 18 (1) KHVG, in force from 23.12.2023."
        ),
        "products": "Haftpflicht",
    },
    "AKKB-VAV": {
        "title": "Allgemeine Bedingungen für die Kraftfahrzeug-Kaskoversicherung (Marktvariante)",
        "title_en": "General Conditions for Motor Own-Damage Insurance (market variant)",
        "basis": "Market variant used where its wording is more specific.",
        "products": "Vollkasko, Teilkasko",
    },
}


@dataclass
class Clause:
    clause_id: str
    document: str
    section: str
    section_en: str
    page: int
    products: tuple[str, ...]
    title: str
    text_de: str
    text_en: str
    quote_de: str = ""
    effective_from: str = "2023-12-23"
    version: str = CORPUS_VERSION

    @property
    def document_title(self) -> str:
        return SOURCES.get(self.document, {}).get("title", self.document)

    def citation(self, language: str = "en") -> dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "document": self.document,
            "document_title": self.document_title,
            "section": self.section if language == "de" else self.section_en,
            "page": self.page,
            "title": self.title,
            "quote": (self.text_de if language == "de" else self.text_en),
            "quote_de": self.quote_de or self.text_de,
            "version": self.version,
            "effective_from": self.effective_from,
            "jurisdiction": JURISDICTION,
        }


KASKO = ("Vollkasko", "Teilkasko")
ALL = ("Vollkasko", "Teilkasko", "Haftpflicht")

CORPUS: list[Clause] = [
    # ── AKKB 2023 · Article 1 — what is insured ────────────────────────
    Clause(
        clause_id="AKKB Art 1.1",
        document="AKKB-2023",
        section="Artikel 1 — Was ist versichert? (Teilkasko)",
        section_en="Article 1 — What is insured? (partial cover)",
        page=1,
        # Vollkasko inherits this catalogue under Art 1.2 ("Die Vollkaskoversicherung
        # umfasst die Teilkaskoversicherung ..."), so the article is authoritative for
        # both products. Tagging it Teilkasko-only left comprehensive policies unable to
        # retrieve the clause that insures the peril being claimed.
        products=("Teilkasko", "Vollkasko"),
        title="Named perils — the partial-cover catalogue, inherited by comprehensive",
        text_de=(
            "In der Teilkaskoversicherung sind das Fahrzeug und seine Teile gegen "
            "Beschädigung, Zerstörung und Verlust versichert durch Naturgewalten "
            "(Blitzschlag, Felssturz, Steinschlag, Muren, Erdrutsch, Lawinen, Schneedruck, "
            "Hagel, Hochwasser, Überschwemmung und Sturm ab 60 km/h), durch Brand oder "
            "Explosion, durch Diebstahl, Raub oder unbefugten Gebrauch durch "
            "betriebsfremde Personen sowie durch Berührung des in Bewegung befindlichen "
            "Fahrzeuges mit Haarwild auf Straßen mit öffentlichem Verkehr."
        ),
        text_en=(
            "Partial cover insures the vehicle against damage, destruction and loss caused "
            "by natural forces (lightning, rockfall, stone impact, mudslide, landslide, "
            "avalanche, snow load, hail, flood and storm from 60 km/h), by fire or "
            "explosion, by theft, robbery or unauthorised use by persons outside the "
            "business, and by contact between the moving vehicle and wild game on public "
            "roads."
        ),
        quote_de=(
            "Versichert sind das Fahrzeug und seine Teile … gegen Beschädigung, Zerstörung "
            "und Verlust … in der Teilkaskoversicherung."
        ),
    ),
    Clause(
        clause_id="AKKB Art 1.2",
        document="AKKB-2023",
        section="Artikel 1 — Was ist versichert? (Vollkasko)",
        section_en="Article 1 — What is insured? (comprehensive cover)",
        page=1,
        products=("Vollkasko",),
        title="Comprehensive cover — accident damage, irrespective of fault",
        text_de=(
            "In der Vollkaskoversicherung ist darüber hinaus der Unfall versichert, das "
            "ist ein unmittelbar von außen plötzlich mit mechanischer Gewalt einwirkendes "
            "Ereignis, unabhängig vom Verschulden, sowie mut- oder böswillige Handlungen "
            "betriebsfremder Personen. Brems-, Betriebs- und reine Bruchschäden sind daher "
            "nicht versichert."
        ),
        text_en=(
            "Comprehensive cover additionally insures accident damage — an event acting "
            "directly from the outside, suddenly and with mechanical force — irrespective "
            "of fault, and malicious acts by persons outside the business. Braking, "
            "operating and pure breakage damage are therefore not insured."
        ),
        quote_de=(
            "durch Unfall, das ist ein unmittelbar von außen plötzlich mit mechanischer "
            "Gewalt einwirkendes Ereignis; Brems-, Betriebs- und reine Bruchschäden sind "
            "daher nicht versichert."
        ),
    ),
    Clause(
        clause_id="AKKB Art 1.3",
        document="AKKB-2023",
        section="Artikel 1 Punkt 3 — Bruchschäden an Verglasung",
        section_en="Article 1 (3) — Glass breakage",
        page=1,
        products=KASKO,
        title="Glass breakage covered only by special agreement",
        text_de=(
            "Bei PKW, Kombi und LKW bis 1,5 Tonnen Nutzlast sind Bruchschäden ohne "
            "Rücksicht auf die Schadenursache an Windschutz-, Seiten- und Heckscheiben nur "
            "bei besonderer Vereinbarung versichert."
        ),
        text_en=(
            "For cars, estates and light commercial vehicles up to 1.5 tonnes payload, "
            "breakage of the windscreen, side and rear windows is insured only where "
            "specially agreed, regardless of the cause."
        ),
    ),
    # ── AKKB 2023 · Article 5 — the indemnity ──────────────────────────
    Clause(
        clause_id="AKKB Art 5.1.1",
        document="AKKB-2023",
        section="Artikel 5 Punkt 1.1 — Versicherungsleistung bei Totalschaden",
        section_en="Article 5 (1.1) — Indemnity on a total loss",
        page=2,
        products=KASKO,
        title="Total loss, and the 70 per cent repair test",
        text_de=(
            "Ein Totalschaden liegt vor, wenn das Fahrzeug zerstört worden ist, in Verlust "
            "geraten ist und nicht innerhalb eines Monats wieder zur Stelle gebracht wird, "
            "oder die voraussichtlichen Wiederherstellungskosten zuzüglich der Restwerte "
            "den Wiederbeschaffungswert übersteigen. Der Versicherungsnehmer kann jedoch "
            "die Reparaturkosten verlangen, sofern diese voraussichtlich 70 Prozent des "
            "Wiederbeschaffungswertes nicht übersteigen und die ordnungsgemäße Reparatur "
            "in einer Fachwerkstätte zu diesem Betrag tatsächlich möglich ist; zum Nachweis "
            "ist eine Rechnung der Fachwerkstätte vorzulegen."
        ),
        text_en=(
            "A total loss exists where the vehicle has been destroyed, has been lost and is "
            "not recovered within one month, or where the expected repair costs plus the "
            "salvage value exceed the replacement value. The policyholder may nevertheless "
            "claim the repair cost, provided it is not expected to exceed 70 per cent of "
            "the replacement value and a proper repair at that figure is actually possible "
            "at a qualified workshop; an invoice from that workshop is required as proof."
        ),
        quote_de=(
            "sofern diese voraussichtlich einen Betrag von 70% des "
            "Wiederbeschaffungswertes nicht übersteigen"
        ),
    ),
    Clause(
        clause_id="AKKB Art 5.1.2",
        document="AKKB-2023",
        section="Artikel 5 Punkt 1.2 — Wiederbeschaffungswert",
        section_en="Article 5 (1.2) — Replacement value",
        page=2,
        products=KASKO,
        title="Indemnity is the replacement value on the date of loss",
        text_de=(
            "Der Versicherer leistet jenen Betrag, den der Versicherungsnehmer für ein "
            "Fahrzeug gleicher Art und Güte im gleichen Abnützungszustand zur Zeit des "
            "Versicherungsfalles hätte aufwenden müssen (Wiederbeschaffungswert)."
        ),
        text_en=(
            "The insurer pays the amount the policyholder would have had to spend on a "
            "vehicle of the same type and quality in the same condition of wear at the time "
            "of the insured event (replacement value)."
        ),
    ),
    Clause(
        clause_id="AKKB Art 5.2",
        document="AKKB-2023",
        section="Artikel 5 Punkt 2 — Versicherungsleistung bei Teilschaden",
        section_en="Article 5 (2) — Indemnity on partial damage",
        page=2,
        products=KASKO,
        title="Partial damage — the cost of the repair actually carried out",
        text_de=(
            "Liegt kein Totalschaden vor, leistet der Versicherer die Kosten der "
            "vorgenommenen Reparatur sowie die notwendigen einfachen Fracht- und sonstigen "
            "Transportkosten."
        ),
        text_en=(
            "Where there is no total loss, the insurer pays the cost of the repair actually "
            "carried out, together with the necessary basic freight and transport costs."
        ),
    ),
    # ── AKKB 2023 · Articles 6 and 8 ───────────────────────────────────
    Clause(
        clause_id="AKKB Art 6",
        document="AKKB-2023",
        section="Artikel 6 — Was ist nicht versichert? (Risikoausschlüsse)",
        section_en="Article 6 — What is not insured? (exclusions)",
        page=2,
        products=KASKO,
        title="Exclusions — intent, motorsport, war and unrest, radiation",
        text_de=(
            "Kein Versicherungsschutz besteht für Schadenereignisse, die bei der "
            "Vorbereitung oder Begehung gerichtlich strafbarer Handlungen eintreten, für "
            "die Vorsatz Tatbestandsmerkmal ist; die bei kraftfahrsportlichen "
            "Veranstaltungen oder deren Trainingsfahrten entstehen; die mit Aufruhr, "
            "inneren Unruhen, Kriegsereignissen, Verfügungen von hoher Hand oder Erdbeben "
            "ursächlich zusammenhängen; oder die durch ionisierende Strahlen entstehen."
        ),
        text_en=(
            "There is no cover for events occurring in the preparation or commission of a "
            "criminal offence requiring intent; arising at motorsport events or their "
            "training runs; causally connected with riot, civil unrest, acts of war, orders "
            "of authority or earthquake; or caused by ionising radiation."
        ),
        quote_de=(
            "die bei der Vorbereitung oder Begehung gerichtlich strafbarer Handlungen … "
            "eintreten, für die Vorsatz Tatbestandsmerkmal ist"
        ),
    ),
    Clause(
        clause_id="AKKB Art 8",
        document="AKKB-2023",
        section="Artikel 8 — Was gilt im Fall einer Selbstbeteiligung?",
        section_en="Article 8 — Excess",
        page=3,
        products=KASKO,
        title="Excess applies per vehicle and per claim",
        text_de=(
            "Eine Selbstbeteiligung gilt für jedes Fahrzeug und für jeden Versicherungsfall "
            "mit dem jeweils vereinbarten Betrag und wird von der Versicherungsleistung "
            "abgezogen."
        ),
        text_en=(
            "An excess applies to each vehicle and to each insured event in the amount "
            "agreed, and is deducted from the indemnity."
        ),
    ),
    Clause(
        clause_id="AKKB Art 9.1",
        document="AKKB-2023",
        section="Artikel 9 Punkt 1 — Fälligkeit der Versicherungsleistung",
        section_en="Article 9 (1) — When the indemnity falls due",
        page=3,
        products=KASKO,
        title="Indemnity falls due two weeks after the enquiries conclude",
        text_de=(
            "Die Versicherungsleistung wird zwei Wochen nach Abschluss der für ihre "
            "Feststellung notwendigen Erhebungen fällig. Bei einem Teilschaden tritt die "
            "Fälligkeit jedoch nicht vor Vorlage einer Rechnung über die ordnungsgemäße "
            "Reparatur ein; im Fall des Diebstahles nicht vor Ablauf der Einmonatsfrist."
        ),
        text_en=(
            "The indemnity falls due two weeks after the enquiries necessary to establish "
            "it have concluded. For partial damage it does not fall due before an invoice "
            "for the proper repair is presented; in the case of theft, not before the "
            "one-month period has elapsed."
        ),
    ),
    # ── AKKB market variant · two more specific duties ─────────────────
    Clause(
        clause_id="AKKB (VAV) Art 1 lit j",
        document="AKKB-VAV",
        section="Artikel 1 — Parkschaden",
        section_en="Article 1 — Parking damage",
        page=2,
        products=KASKO,
        title="Parking damage must be reported to the police the same day",
        text_de=(
            "Bei einem Parkschaden ist der Schaden unverzüglich, nämlich am Tag der "
            "Kenntniserlangung, bei der nächsten Polizeidienststelle zur Anzeige zu "
            "bringen; die Anzeigenbestätigung ist der Schadenmeldung beizufügen."
        ),
        text_en=(
            "Parking damage must be reported to the nearest police station without delay, "
            "namely on the day it is discovered, and the confirmation of that report must be "
            "attached to the claim notification."
        ),
    ),
    Clause(
        clause_id="AKKB (VAV) Art 1 lit l",
        document="AKKB-VAV",
        section="Artikel 1 — Bergungskosten im Totalschadenfall",
        section_en="Article 1 — Recovery costs on a total loss",
        page=2,
        products=KASKO,
        title="Recovery costs on a total loss, capped",
        text_de=(
            "Im Totalschadenfall werden die Kosten für eine notwendige Bergung bis zur "
            "nächstgelegenen Werkstatt bis EUR 2.000,00 übernommen; im Rahmen dieser Summe "
            "stehen EUR 200,00 als Abschleppkosten zur Verfügung."
        ),
        text_en=(
            "On a total loss the cost of a necessary recovery to the nearest workshop is "
            "covered up to EUR 2,000.00, of which EUR 200.00 is available for towing."
        ),
    ),
    # ── AKHB 2023 · liability ──────────────────────────────────────────
    Clause(
        clause_id="AKHB Art 1",
        document="AKHB-2023",
        section="Artikel 1 — Was ist Gegenstand der Versicherung?",
        section_en="Article 1 — Subject matter of the insurance",
        page=1,
        products=("Haftpflicht",),
        title="Liability cover meets third-party claims and defends unfounded ones",
        text_de=(
            "Die Versicherung umfasst die Befriedigung begründeter und die Abwehr "
            "unbegründeter Ersatzansprüche, die auf Grund gesetzlicher "
            "Haftpflichtbestimmungen gegen den Versicherungsnehmer erhoben werden, wenn "
            "durch die Verwendung des versicherten Fahrzeuges Personen verletzt oder "
            "getötet werden, Sachen beschädigt oder zerstört werden oder abhandenkommen "
            "oder ein bloßer Vermögensschaden verursacht wird."
        ),
        text_en=(
            "The insurance covers meeting justified and defending unjustified compensation "
            "claims brought against the policyholder under statutory liability provisions "
            "where the use of the insured vehicle injures or kills a person, damages, "
            "destroys or causes the loss of property, or causes pure financial loss."
        ),
        quote_de=(
            "die Befriedigung begründeter und die Abwehr unbegründeter Ersatzansprüche"
        ),
    ),
    Clause(
        clause_id="AKHB Art 8.2",
        document="AKHB-2023",
        section="Artikel 8 Punkt 2 — Risikoausschlüsse",
        section_en="Article 8 (2) — Exclusions",
        page=3,
        products=("Haftpflicht",),
        title="Damage to the insured vehicle itself is not covered by liability insurance",
        text_de=(
            "Der Versicherungsschutz umfasst nicht Ersatzansprüche wegen Beschädigung, "
            "Zerstörung oder Abhandenkommens des versicherten Fahrzeuges und der mit ihm "
            "beförderten Sachen. Schäden am eigenen Fahrzeug sind daher in der "
            "Kraftfahrzeug-Haftpflichtversicherung nicht gedeckt."
        ),
        text_en=(
            "Cover does not extend to claims for damage to, destruction of, or loss of the "
            "insured vehicle itself, or of property carried in it. Damage to the "
            "policyholder's own vehicle is therefore not covered by motor third-party "
            "liability insurance."
        ),
        quote_de=(
            "Ersatzansprüche wegen Beschädigung, Zerstörung oder Abhandenkommens des "
            "versicherten Fahrzeuges"
        ),
    ),
    Clause(
        clause_id="AKHB Art 8.1",
        document="AKHB-2023",
        section="Artikel 8 Punkt 1 — Risikoausschlüsse",
        section_en="Article 8 (1) — Exclusions",
        page=3,
        products=("Haftpflicht",),
        title="Claims by the owner or keeper against co-insured persons are excluded",
        text_de=(
            "Nicht versichert sind Ersatzansprüche des Eigentümers, des Halters und – bei "
            "Vermietung ohne Beistellung eines Lenkers – des Mieters gegen mitversicherte "
            "Personen wegen Sach- oder bloßer Vermögensschäden."
        ),
        text_en=(
            "Claims by the owner, the keeper, or — where the vehicle is hired without a "
            "driver — the hirer, against co-insured persons for property damage or pure "
            "financial loss are not insured."
        ),
    ),
    Clause(
        clause_id="AKHB Art 9",
        document="AKHB-2023",
        section="Artikel 9 — Obliegenheiten im Versicherungsfall",
        section_en="Article 9 — Duties on a claim",
        page=4,
        products=ALL,
        title="Duties after a loss — notify, mitigate, and provide what is needed",
        text_de=(
            "Der Versicherungsnehmer hat den Versicherungsfall unverzüglich anzuzeigen, den "
            "Schaden nach Möglichkeit zu mindern und dem Versicherer die zur Feststellung "
            "des Sachverhaltes erforderlichen Auskünfte und Unterlagen zu erteilen. Bei "
            "Personenschäden, Entwendung und Fahrerflucht ist zusätzlich eine polizeiliche "
            "Anzeige zu erstatten."
        ),
        text_en=(
            "The policyholder must notify the insured event without delay, mitigate the loss "
            "so far as possible, and provide the insurer with the information and documents "
            "needed to establish the facts. In cases of personal injury, theft or a "
            "hit-and-run, a police report must also be filed."
        ),
    ),
    # ── Procedure — how the department handles two specific situations ──
    Clause(
        clause_id="PROC-INJ-01",
        document="AKKB-2023",
        section="Schadenbearbeitung — Personenschaden",
        section_en="Claims procedure — personal injury",
        page=0,
        products=ALL,
        title="Injury claims are never adjudicated automatically",
        text_de=(
            "Wird bei einem Schadenfall eine Personenverletzung angegeben, ist die "
            "automatisierte Erledigung sofort auszusetzen und der Fall an das "
            "Personenschadenteam zu übergeben."
        ),
        text_en=(
            "Where a personal injury is reported on a claim, automated handling is suspended "
            "immediately and the case is referred to the bodily-injury team."
        ),
    ),
    Clause(
        clause_id="PROC-SIU-02",
        document="AKKB-2023",
        section="Schadenbearbeitung — Sonderermittlung",
        section_en="Claims procedure — special investigations",
        page=0,
        products=ALL,
        title="An elevated duplicate or relationship signal freezes progression",
        text_de=(
            "Bei einem erhöhten Duplikats- oder Beziehungssignal ist die autonome "
            "Weiterverarbeitung einzufrieren, der Beweispfad zu sichern und ein "
            "Untersuchungsauftrag zu erstellen. Eine Ablehnung allein auf Grund eines "
            "Signals ist nicht zulässig."
        ),
        text_en=(
            "Where a duplicate or relationship signal is elevated, autonomous progression is "
            "frozen, the evidence trail is preserved, and an investigation task is raised. A "
            "declinature on a signal alone is not permitted."
        ),
    ),
]


# --------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "for", "to", "in", "on", "and",
    "or", "my", "i", "it", "this", "that", "be", "does", "do", "der", "die", "das",
    "und", "ist", "für", "mit", "ein", "eine", "im", "am", "bei", "von", "nicht", "auf",
    "dem", "den", "des", "sind", "wird", "werden", "kann", "wenn",
    # Interrogatives carry no retrieval signal, and every article heading in the Austrian
    # standard-form conditions is phrased as a question — so leaving these in makes
    # "What is the interest rate on my savings account?" match "Was ist versichert?".
    "what", "when", "where", "which", "who", "whom", "how", "why", "whether",
    "wie", "wo", "wer", "wen", "wem", "welche", "welcher", "welches", "warum", "wann",
    "gilt", "besteht", "leistet", "erbringt",
    # Coverage verbs. Every coverage question contains one and so does nearly every
    # clause, so they discriminate nothing while inflating the concept count a match has
    # to clear.
    "gedeckt", "deckt", "versichert", "versicherte", "versicherten", "ersetzt",
    "bezahlt", "zahlt", "übernommen", "covered", "cover", "covers", "insured",
    "insures", "pay", "pays", "paid", "reimbursed",
    # Possessives and the word "insurance" itself: present in most questions and most
    # clauses, discriminating in neither.
    "mein", "meine", "meinem", "meinen", "meiner", "ihr", "ihre", "ihrem", "ihren",
    "versicherung", "versicherungen", "insurance", "policy", "polizze",
}

_EXPANSIONS: dict[str, tuple[str, ...]] = {
    # AKKB Art 1.2 insures "mut- oder böswillige Handlungen betriebsfremder Personen".
    # Nobody asks about it in those words.
    "vandalismus": ("mutwillige", "böswillige", "handlungen", "betriebsfremder"),
    "vandalism": ("mutwillige", "böswillige", "handlungen", "betriebsfremder"),
    "collision": ("accident", "unfall", "crash", "mechanical", "kollision", "sudden"),
    "accident": ("collision", "unfall", "mechanical", "sudden", "gewalt"),
    "own": ("policyholder", "eigenen", "versicherten", "insured", "fahrzeuges"),
    "damage": ("schaden", "beschädigung", "indemnify", "zerstörung"),
    "liability": ("haftpflicht", "third", "party", "ersatzansprüche", "dritter"),
    "excess": ("selbstbeteiligung", "deducted", "abgezogen", "deductible"),
    "glass": ("glasbruch", "windscreen", "windschutz", "scheiben", "bruchschäden"),
    "hail": ("hagel", "storm", "sturm", "naturgewalten", "perils"),
    "theft": ("entwendung", "diebstahl", "stolen", "raub"),
    "injury": ("verletzung", "personenschaden", "bodily", "personen"),
    "police": ("polizei", "polizeiliche", "anzeige", "report"),
    "total": ("totalschaden", "replacement", "wiederbeschaffungswert", "destroyed"),
    "repairable": ("totalschaden", "wiederherstellungskosten", "reparaturkosten", "70"),
    "fraud": ("duplicate", "duplikat", "beziehungssignal", "untersuchung"),
    "parking": ("parkschaden", "car", "park", "polizeidienststelle", "collision"),
    "recovery": ("bergungskosten", "regress", "abschleppkosten", "ersatzansprüche"),
    "storm": ("sturm", "naturgewalten", "hagel", "hochwasser"),
    "wild": ("haarwild", "game", "berührung"),
    "due": ("fällig", "fälligkeit", "rechnung", "erhebungen"),
}


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-zäöüß]+", (text or "").lower())
        if t not in _STOPWORDS and len(t) > 2
    }


# German builds its claims vocabulary by compounding, and the head of the compound is the
# part the conditions are written in: the corpus says "Hagel", a customer says
# "Hagelschaden". Splitting on the handful of heads that actually appear in motor claims is
# enough — a full decompounder would be the wrong tool for a closed vocabulary, and would
# introduce failure modes of its own on a corpus this size.
_COMPOUND_TAILS = (
    "schaden", "schäden", "schadens", "schadenfall", "schadensfall",
    "versicherung", "deckung", "ersatz", "kosten", "bruch", "verlust",
)

# A few compounds decompose into a head the corpus does not use. These are the ones a
# customer or a handler actually types.
_COMPOUND_HEADS: dict[str, tuple[str, ...]] = {
    "glasbruch": ("glas", "verglasung", "bruch"),
    "wildschaden": ("haarwild", "wild"),
    "parkschaden": ("parken", "abstellen"),
    "totalschaden": ("totalschaden", "zerstört"),
    "vorschaden": ("vorschaden",),
    "blechschaden": ("blech",),
}


def _decompound(term: str) -> set[str]:
    """The head of a German compound, where the corpus is written in the head.

    Returns the parts to add, never replacing the original — an exact match on the whole
    compound must still win where the corpus happens to carry it.
    """
    out: set[str] = set()
    out.update(_COMPOUND_HEADS.get(term, ()))
    for tail in _COMPOUND_TAILS:
        if term.endswith(tail) and len(term) - len(tail) >= 4:
            head = term[: -len(tail)]
            out.add(head)
            # "Sturmschaden" -> "sturm"; strip a linking -s where one was used.
            if head.endswith("s") and len(head) > 4:
                out.add(head[:-1])
            break
    return {p for p in out if len(p) > 2}


def _expand(terms: set[str]) -> set[str]:
    out = set(terms)
    for t in terms:
        out.update(_EXPANSIONS.get(t, ()))
        out.update(_decompound(t))
    # A compound's head can itself carry an expansion ("hagel" -> "hail").
    for t in set(out) - terms:
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
    min_score: float = 0.10,
    min_terms: int = 2,
) -> list[RetrievedClause]:
    """Hybrid retrieval with the product filter applied during the search.

    A citation has to be earned. One term in common is a coincidence, not grounding, so a
    match needs at least `min_terms` distinct overlapping terms before it counts — unless
    the query itself is that short. Returning nothing is a legitimate answer: it means the
    agent abstains, which the citation rule downstream then enforces.

    The floor counts *concepts the asker raised*, not the expanded term set. Expansions and
    compound heads are synonyms of a concept already counted, so scoring them separately
    would make every expansion raise the bar it was added to clear — which is what made
    "Hagelschaden" abstain while "Hagel" matched.
    """
    asked = _tokens(query)
    q = _expand(asked)
    if not q:
        return []
    required = min(min_terms, len(asked))

    # Which expanded terms belong to which concept the asker actually raised, so overlap
    # can be counted per concept rather than per token.
    concepts: list[set[str]] = [{t} | _expand({t}) for t in asked]

    scored: list[RetrievedClause] = []
    for clause in CORPUS:
        if product and product not in clause.products:
            continue

        body = _tokens(
            f"{clause.title} {clause.section} {clause.section_en} "
            f"{clause.text_en} {clause.text_de}"
        )
        overlap = q & body
        matched_concepts = sum(1 for c in concepts if c & body)
        if matched_concepts < required:
            continue

        title_terms = _tokens(f"{clause.title} {clause.section} {clause.section_en}")
        boost = 0.25 * sum(1 for c in concepts if c & title_terms)
        score = (matched_concepts / max(len(concepts), 1)) + boost
        scored.append(RetrievedClause(clause, round(score, 4), sorted(overlap)))

    scored.sort(key=lambda r: (-r.score, r.clause.clause_id))
    return [r for r in scored if r.score >= min_score][:top_k]


def citations_for(
    results: list[RetrievedClause], language: str = "en"
) -> list[dict[str, Any]]:
    return [
        {
            **r.clause.citation(language),
            "retrieval_score": r.score,
            "matched_terms": r.matched_terms,
        }
        for r in results
    ]


def clause_by_id(clause_id: str) -> Clause | None:
    return next((c for c in CORPUS if c.clause_id == clause_id), None)


def corpus_summary() -> dict[str, Any]:
    return {
        "version": CORPUS_VERSION,
        "jurisdiction": JURISDICTION,
        "clause_count": len(CORPUS),
        "documents": [
            {"id": key, **meta, "clauses": sum(1 for c in CORPUS if c.document == key)}
            for key, meta in SOURCES.items()
        ],
        "chunking": "layout-aware, one chunk per clause unit",
        "embedding": "vertex-ai-text-embedding (target) / lexical+expansion (demo)",
        "filters": ["product", "jurisdiction", "version", "effective_from"],
        "note": (
            "Built from the Austrian standard-form motor conditions (AKKB 2023, AKHB 2023) "
            "that every Austrian insurer publishes and files with the supervisor. Summarised "
            "faithfully with short quotations and real article references. This is a "
            "demonstration corpus, not a specific insurer's policy document."
        ),
    }
