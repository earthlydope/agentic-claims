"""The guided notification: one question at a time, chosen from what is still missing.

How a motor claim is actually taken today, on the phone, is a conversation. The handler
does not read a form top to bottom — they listen to what happened and then ask the two or
three things that were left out. A form makes the customer do that work instead, which is
why forms are abandoned and why the fields that matter most are the ones most often left
blank.

So this is the conversation, held by the platform. It reads what the customer has already
said, works out which facts are still missing, and asks for the most important one in plain
language. When nothing important is missing it stops asking and hands back the structured
notification it assembled — which is the same shape the form produces, so both routes reach
the same intake.

Two properties are deliberate:

* Every answer is screened before it reaches a model, exactly as the free-text route is.
  A guided conversation is not a trusted channel.
* The model never invents a fact. It may only carry across what the customer said, and the
  fields it fills are checked against the answers it was given.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal

from pydantic import Field

from app.schemas import Strict
from app.zero_trust.semantic_gateway import PolicyAction, PromptFirewall, Surface

# The facts a motor notification cannot be worked without, in the order a handler asks for
# them. "What happened" comes first because it is the question the customer arrived wanting
# to answer, and because the answer usually contains two or three of the others.
REQUIRED = ("what_happened", "incident_date", "incident_region", "damage_description")

# Worth having, asked only while the important things are already answered.
USEFUL = ("third_party", "injury", "police_report", "drivable", "where_exactly")

MAX_QUESTIONS = 7


class NextQuestion(Strict):
    """One question to put to the customer, or the signal to stop asking."""

    done: bool = Field(
        description="True when enough is known to file the claim without asking more.",
    )
    question: str = Field(
        default="",
        description=(
            "The single next question, addressed to the customer in their language. One "
            "sentence. No preamble, no restating what they already said."
        ),
    )
    why: str = Field(
        default="",
        description=(
            "One short line telling the customer why this is being asked. Plain language, "
            "no jargon, no internal reasoning."
        ),
    )
    field: str = Field(
        default="",
        description="Which fact this question is trying to establish.",
    )
    examples: list[str] = Field(
        default_factory=list,
        description=(
            "Up to three short example answers the customer could tap instead of typing. "
            "Only where the answer is genuinely a small set of options."
        ),
        max_length=3,
    )
    still_missing: list[str] = Field(
        default_factory=list,
        description="The facts still unknown, most important first.",
    )


class Notification(Strict):
    """The structured claim assembled from the conversation."""

    fnol_text: str = Field(
        description=(
            "What happened, in the customer's own words, joined into a paragraph. Use only "
            "what they said. Do not add detail, do not interpret, do not assign blame."
        ),
    )
    incident_date: str = Field(description="ISO date, YYYY-MM-DD.")
    incident_type: Literal[
        "parking_collision", "junction_collision", "rear_end_collision", "hail",
        "glass_breakage", "single_vehicle", "wild_game", "theft_attempt", "vandalism",
        "storm_damage", "flood", "fire",
    ] = Field(
        description=(
            "The closest match to what the customer described. Prefer the specific "
            "category over the general one where both fit — manoeuvring into a post or a "
            "wall is parking_collision, not single_vehicle, because the conditions treat "
            "parking damage differently. Use single_vehicle only when nothing more "
            "specific applies."
        ),
    )
    incident_region: str = Field(description="Austrian Bundesland.")
    incident_city: str = Field(default="", description="Town or city, if given.")
    injury_reported: bool = Field(
        default=False,
        description="True only if the customer said someone was hurt.",
    )
    third_party_involved: bool = Field(
        default=False,
        description="True only if the customer said another party was involved.",
    )
    police_report_ref: str | None = Field(
        default=None, description="The reference the customer gave, or null.",
    )
    language: Literal["de", "en"] = Field(description="The language they answered in.")
    unanswered: list[str] = Field(
        default_factory=list,
        description="Anything asked that the customer could not answer.",
    )


SYSTEM = """
You are taking a motor claim notification for an Austrian insurer, the way an experienced
claims handler takes one over the phone.

Your job is to ask the fewest questions that make the claim workable — not to complete a
form. Read what the customer has already told you and ask only for what is genuinely
missing and genuinely needed.

Rules
- One question at a time. One sentence. Their language, not yours: no "Vorschadensfreiheit",
  no "third-party liability", no reference numbers.
- Never ask for something they have already told you, even if they said it loosely. If they
  said "yesterday morning", the date is answered.
- Never ask for their policy number, their name, their address or their bank details. You
  already have the policy, and payment details are never collected in a claim conversation.
- Never ask whether they were at fault, and never suggest an answer that admits fault.
- If they said someone was hurt, ask nothing further about the injury beyond who; an injury
  claim is handled by a person and you must not appear to assess it.
- Stop as soon as {required} are all known. Asking more than {max_questions} questions in
  total is a failure, not thoroughness.
- Facts are the customer's. You may not fill a field from inference, from the region's
  weather, or from what usually happens.
""".strip()


def _screen(text: str) -> tuple[bool, dict[str, Any]]:
    """Screen one customer answer. A guided conversation is not a trusted channel."""
    verdict = PromptFirewall.inspect(text, Surface.USER_MESSAGE)
    return verdict.action is not PolicyAction.BLOCK, verdict.as_dict()


def _transcript(answers: list[dict[str, str]]) -> str:
    if not answers:
        return "(nothing yet — this is the first question)"
    lines = []
    for turn in answers:
        q = (turn.get("question") or "").strip()
        a = (turn.get("answer") or "").strip()
        if q:
            lines.append(f"You asked: {q}")
        lines.append(f"They said: {a}")
    return "\n".join(lines)


# Dates arrive as words far more often than as dates. These are the ones that actually
# turn up, and resolving them here means the model is never asked to do arithmetic.
# Longest first, because "gestern" is a substring of "vorgestern".
_RELATIVE = (
    ("vorgestern", 2),
    ("day before yesterday", 2),
    ("gestern", 1),
    ("yesterday", 1),
    ("heute", 0),
    ("today", 0),
)

# Weekday names, which is how most people date an accident that happened this week.
_WEEKDAYS = {
    "montag": 0, "monday": 0,
    "dienstag": 1, "tuesday": 1,
    "mittwoch": 2, "wednesday": 2,
    "donnerstag": 3, "thursday": 3,
    "freitag": 4, "friday": 4,
    "samstag": 5, "sonnabend": 5, "saturday": 5,
    "sonntag": 6, "sunday": 6,
}


def _resolve_date(text: str, *, today: dt.date) -> str | None:
    """An ISO date from what the customer wrote, or None if it is not stated."""
    lowered = text.lower()
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso:
        return iso.group(0)
    # 24.8.2026, 24.08.26, 24/8/2026
    euro = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b", text)
    if euro:
        day, month, year = (int(g) for g in euro.groups())
        year += 2000 if year < 100 else 0
        try:
            return dt.date(year, month, day).isoformat()
        except ValueError:
            return None
    for word, back in _RELATIVE:
        if word in lowered:
            return (today - dt.timedelta(days=back)).isoformat()
    # "on Tuesday" means the most recent Tuesday. It is what a handler would write down,
    # and it is confirmed back to the customer before the claim is filed.
    for word, weekday in _WEEKDAYS.items():
        if word in lowered:
            back = (today.weekday() - weekday) % 7 or 7
            return (today - dt.timedelta(days=back)).isoformat()
    return None


def known_facts(answers: list[dict[str, str]], *, today: dt.date) -> set[str]:
    """Which required facts the transcript already establishes.

    Deliberately generous about *what* was said and strict about *whether* it was said:
    the cost of asking twice is an abandoned claim, and the cost of a missing fact is one
    more question.
    """
    blob = " ".join((t.get("answer") or "") for t in answers)
    lowered = blob.lower()
    known: set[str] = set()

    if _resolve_date(blob, today=today):
        known.add("incident_date")
    # Any real account of an accident runs past a few words.
    if len(blob.split()) >= 8:
        known.add("what_happened")
    if re.search(
        r"wien|nieder[öo]sterreich|ober[öo]sterreich|steiermark|salzburg|tirol|"
        r"vorarlberg|k[äa]rnten|burgenland|graz|linz|innsbruck|klagenfurt|villach|"
        r"wels|st\.? p[öo]lten|dornbirn|vienna",
        lowered,
    ):
        known.add("incident_region")
    if re.search(
        r"sto[ßs]stange|bumper|kotfl[üu]gel|fender|t[üu]r\b|door|spiegel|mirror|"
        r"scheibe|windscreen|windshield|glass|glas|heckklappe|tailgate|motorhaube|"
        r"bonnet|hood|dach|roof|delle|dent|kratz|scratch|beschädigt|damaged|"
        r"eingedr[üu]ckt|verbeult|gebrochen|broken",
        lowered,
    ):
        known.add("damage_description")
    return known


async def next_question(
    *,
    answers: list[dict[str, str]],
    language: str = "de",
    policy_product: str = "",
    today: dt.date | None = None,
) -> dict[str, Any]:
    """The next question to ask, or done.

    Falls back to a fixed sequence when no model is reachable, so the guided route works
    on a laptop with no key just as the rest of the platform does.
    """
    today = today or dt.datetime.now(dt.timezone.utc).date()

    # Screen the newest answer before it can reach a model.
    if answers:
        ok, verdict = _screen(answers[-1].get("answer") or "")
        if not ok:
            return {
                "done": False,
                "blocked": True,
                "question": (
                    "Bitte beschreiben Sie einfach, was passiert ist."
                    if language == "de"
                    else "Please just describe what happened."
                ),
                "why": (
                    "Diese Eingabe wurde nicht weitergegeben."
                    if language == "de"
                    else "That input was not passed on."
                ),
                "field": "what_happened",
                "examples": [],
                "still_missing": sorted(set(REQUIRED) - known_facts(answers[:-1],
                                                                    today=today)),
                "firewall": verdict,
            }

    known = known_facts(answers, today=today)
    missing = [f for f in REQUIRED if f not in known]
    asked = len([t for t in answers if t.get("question")])

    # The opening question is always the same one, so it does not need a model to choose it
    # — and asking anything else first ("when did it happen?") reads as an interrogation
    # rather than someone listening.
    if not answers:
        return {**_scripted("what_happened", language), "blocked": False,
                "still_missing": missing}

    # Enough is known, or enough has been asked. Either way, stop.
    if not missing or asked >= MAX_QUESTIONS:
        return {
            "done": True, "blocked": False, "question": "", "why": "", "field": "",
            "examples": [], "still_missing": missing,
        }

    from app.config import live_model_available

    if not live_model_available():
        return {**_scripted(missing[0], language), "blocked": False,
                "still_missing": missing}

    try:
        return {**await _ask_model(answers, language, policy_product, missing, today),
                "blocked": False}
    except Exception:  # noqa: BLE001 — a model that will not answer must not stop intake
        return {**_scripted(missing[0], language), "blocked": False,
                "still_missing": missing}


async def _ask_model(answers, language, policy_product, missing, today) -> dict[str, Any]:
    from pydantic_ai import Agent

    from app.agents.providers import _model_settings, _throttled_google_model
    from app.config import resolve_model_name_for

    agent = Agent(
        _throttled_google_model(resolve_model_name_for("fast")),
        output_type=NextQuestion,
        instructions=SYSTEM.format(required=", ".join(REQUIRED),
                                   max_questions=MAX_QUESTIONS),
        model_settings=_model_settings(),
        retries=2,
        name="notification.interviewer",
    )
    prompt = (
        f"Today is {today.isoformat()}. The customer holds a {policy_product or 'motor'} "
        f"policy and is answering in {'German' if language == 'de' else 'English'}.\n\n"
        f"The conversation so far:\n{_transcript(answers)}\n\n"
        f"Still unknown: {', '.join(missing)}.\n\n"
        "Ask for the first of those, in their language."
    )
    result = await agent.run(prompt)
    out = result.output
    return {
        "done": out.done,
        "question": out.question,
        "why": out.why,
        "field": out.field or missing[0],
        "examples": list(out.examples),
        "still_missing": out.still_missing or missing,
        "model": resolve_model_name_for("fast"),
    }


# The fallback sequence. Not a lesser experience — just a fixed one.
_SCRIPTED: dict[str, dict[str, dict[str, Any]]] = {
    "what_happened": {
        "de": {"question": "Was ist passiert?",
               "why": "Erzählen Sie es einfach in Ihren Worten.",
               "examples": []},
        "en": {"question": "What happened?",
               "why": "Just tell it in your own words.",
               "examples": []},
    },
    "incident_date": {
        "de": {"question": "Wann ist es passiert?",
               "why": "Das Datum brauchen wir für die Prüfung der Deckung.",
               "examples": ["Heute", "Gestern", "Vorgestern"]},
        "en": {"question": "When did it happen?",
               "why": "We need the date to check your cover.",
               "examples": ["Today", "Yesterday", "The day before"]},
    },
    "incident_region": {
        "de": {"question": "In welchem Bundesland ist es passiert?",
               "why": "Die Werkstattsätze unterscheiden sich je Bundesland.",
               "examples": ["Wien", "Niederösterreich", "Steiermark"]},
        "en": {"question": "Which part of Austria did it happen in?",
               "why": "Repair rates differ from one Bundesland to the next.",
               "examples": ["Wien", "Niederösterreich", "Steiermark"]},
    },
    "damage_description": {
        "de": {"question": "Welche Teile des Fahrzeugs sind beschädigt?",
               "why": "So können wir den Reparaturumfang einschätzen.",
               "examples": ["Stoßstange hinten", "Tür links", "Spiegel"]},
        "en": {"question": "Which parts of the car are damaged?",
               "why": "It tells us how much repair work is involved.",
               "examples": ["Rear bumper", "Left-hand door", "Mirror"]},
    },
}


def _scripted(field: str, language: str) -> dict[str, Any]:
    row = _SCRIPTED.get(field, _SCRIPTED["what_happened"])
    body = row.get(language) or row["en"]
    return {"done": False, "field": field, **body}


async def assemble(
    *,
    answers: list[dict[str, str]],
    language: str = "de",
    today: dt.date | None = None,
) -> dict[str, Any]:
    """Turn the conversation into the structured notification.

    Every field is checked back against what the customer actually said. The date is
    resolved here rather than by the model, and a claim date the transcript does not support
    is dropped rather than guessed — a wrong incident date is a wrong coverage decision.
    """
    today = today or dt.datetime.now(dt.timezone.utc).date()
    blob = " ".join((t.get("answer") or "") for t in answers)
    resolved_date = _resolve_date(blob, today=today)

    from app.config import live_model_available

    if not live_model_available():
        return _assemble_locally(answers, language, resolved_date, today)

    try:
        from pydantic_ai import Agent

        from app.agents.providers import _model_settings, _throttled_google_model
        from app.config import resolve_model_name_for

        agent = Agent(
            _throttled_google_model(resolve_model_name_for("fast")),
            output_type=Notification,
            instructions=(
                "Turn this claim conversation into a structured notification. Use only "
                "what the customer said. Where something was not said, leave the field at "
                "its default — never infer, never fill a gap with what is usual. The "
                "narrative must read as their account, not as an assessment."
            ),
            model_settings=_model_settings(),
            retries=2,
            name="notification.assembler",
        )
        result = await agent.run(
            f"Today is {today.isoformat()}.\n\n{_transcript(answers)}",
        )
        draft = result.output.model_dump()
    except Exception:  # noqa: BLE001
        return _assemble_locally(answers, language, resolved_date, today)

    # The date is ours, not the model's, whenever the transcript supports one.
    if resolved_date:
        draft["incident_date"] = resolved_date
    # A claim cannot have happened tomorrow.
    try:
        if dt.date.fromisoformat(draft["incident_date"]) > today:
            draft["incident_date"] = today.isoformat()
    except (ValueError, KeyError, TypeError):
        draft["incident_date"] = (resolved_date or today.isoformat())

    # An injury or a third party is only ever true because the customer said so.
    lowered = blob.lower()
    if draft.get("injury_reported") and not re.search(
        r"verletz|schmerz|weh\b|hurt|injur|pain|whiplash|hws|nacken|neck|"
        r"krankenhaus|hospital|arzt|doctor|rettung|ambulance",
        lowered,
    ):
        draft["injury_reported"] = False
    if draft.get("third_party_involved") and not re.search(
        r"anderer|andere[sn]?\b|other (car|driver|vehicle|party)|zweiter|"
        r"fremdfahrzeug|gegner|dritter|third part|jemand|someone|lkw|radfahrer|"
        r"fu[ßs]g[äa]nger|pedestrian|cyclist",
        lowered,
    ):
        draft["third_party_involved"] = False

    draft["source"] = "guided"
    return draft


def _assemble_locally(answers, language, resolved_date, today) -> dict[str, Any]:
    """The notification, assembled without a model."""
    blob = " ".join((t.get("answer") or "").strip() for t in answers if t.get("answer"))
    lowered = blob.lower()

    region = "Wien"
    for candidate in ("Niederösterreich", "Oberösterreich", "Steiermark", "Salzburg",
                      "Tirol", "Vorarlberg", "Kärnten", "Burgenland", "Wien"):
        if candidate.lower() in lowered:
            region = candidate
            break

    kind = "parking_collision"
    for pattern, value in (
        (r"hagel|hail", "hail"),
        (r"scheibe|glas|glass|windscreen|windshield", "glass_breakage"),
        (r"wild|reh|hirsch|deer|boar", "wild_game"),
        (r"auffahr|rear.?end|von hinten|behind", "rear_end_collision"),
        (r"kreuzung|junction|vorrang|right of way", "junction_collision"),
        (r"sturm|storm|umgest[üu]rzt|fallen tree", "storm_damage"),
        (r"brand|feuer|fire|explosion|ausgebrannt|gebrannt", "fire"),
        (r"aufgebrochen|einbruch|gestohlen|stolen|theft", "theft_attempt"),
        (r"zerkratzt|vandal|mutwillig", "vandalism"),
        (r"parken|ausparken|parkl[üu]cke|parking|bollard|poller|pfeiler", "parking_collision"),
    ):
        if re.search(pattern, lowered):
            kind = value
            break

    return {
        "fnol_text": blob or "(no description given)",
        "incident_date": resolved_date or today.isoformat(),
        "incident_type": kind,
        "incident_region": region,
        "incident_city": region,
        "injury_reported": bool(re.search(
            r"verletz|schmerz|hurt|injur|pain|whiplash|nacken|neck", lowered)),
        "third_party_involved": bool(re.search(
            r"anderer|other (car|driver|vehicle)|fremdfahrzeug|dritter|someone", lowered)),
        "police_report_ref": None,
        "language": language,
        "unanswered": [],
        "source": "guided-offline",
    }
