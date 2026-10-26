
"""Evidence engine: checks whether news sources support or contradict a claim."""

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

# ---------- rules ----------

STOP = set("""
the a an is are was were has have had to of in on for and or with this that
from by will be been its their they it as at into about after before according
says said news report reports new latest claim claims reported but can who how
why you our his her all any may now
""".split())

RULES_PATH = Path(__file__).resolve().parent / "data" / "evidence_rules.csv"
with RULES_PATH.open(encoding="utf-8", newline="") as f:
    RULES = list(csv.DictReader(f))

COUNTRIES = {r["value"] for r in RULES if r["type"] == "country"}
ALIASES = {r["value"]: r["category"] for r in RULES if r["type"] == "alias"}
SATIRE = ("the onion", "theonion.com", "babylonbee", "babylon bee", "fakingnews",
          "faking news", "newsthump", "the fauxy", "thefauxy", "waterford whispers")

# Fact-check verdict words (fact-check headlines usually say "viral"/"claim",
# which the general filters treat as neutral, so they get their own rules).
FC_FALSE = re.compile(r"\b(?:false|fake|hoax|misleading|myth|debunk\w*|no evidence|not true|baseless"
                      r"|fabricated|morphed|doctored|edited|old video|old image|satire|scam|incorrect|wrong)\b|^no,")
FC_TRUE = re.compile(r"\b(?:true|correct|genuine|accurate|real|authentic|confirmed)\b")

NUMBER_WORDS = {
    w: str(i) for i, w in enumerate(
        "one two three four five six seven eight nine ten".split(), 1
    )
}

SCALE_WORDS = {
    "thousand": 1_000,
    "lakh": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "million": 1_000_000,
    "crore": 10_000_000,
    "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
}


def rx(pattern):
    return re.compile(r"\b(?:" + pattern + r")\b")


NEGATION = rx(r"not|never|cannot|\w+n't")
DENIAL = rx(r"false|fake|wrong|busted|debunked|refut\w*|dismiss\w*|contrary to")
QUESTION = re.compile(r"\?")
ATTRIBUTION = rx(
    r"say|says|said|told|claim\w*|report\w*|believ\w*|belief|convinced|think\w*"
    r"|thought|argu(?:e|es|ed)|according to|reject\w*|den(?:y|ies|ied)"
    r"|criticiz\w*|promis\w*|insist\w*|opinion|survey|poll"
)
ATTEMPT = rx(
    r"prov(?:e|es|ing)|convinc(?:e|es|ing)|attempt\w*|tri(?:es|ed)|trying"
    r"|plan|planned|plans|intend|intends|intended"
)
CONTEXT = rx(
    r"earth week|campaign|event|conference|program|theme|project|initiative"
    r"|barycent(?:er|re)|cent(?:er|re) of mass|reference frame"
    r"|relative (?:to|motion)|technically|strictly speaking|in physics"
    r"|new (?:insight|findings)|what would happen if|hypothetical"
    r"|like (?:believing|saying)|as if|just as|metaphor\w*|analogy|akin to"
    r"|rather than|instead of|something else|(?:another|different) object"
    r"|statement|quoted?|remarks?|comments?|reaction|response|controversy"
    r"|controversial|viral|april fools?|april 1|satir(?:e|ical)|parody|jokes?"
    r"|funny|humorous|just kidding|for fun|cent(?:er|re)[sd]? around"
    r"|focus(?:es|ed) on|dedicated to|aims to"
)
FUTURE = rx(
    r"forecast|forecasted|predict|predicts|predicted|projection|projected|might"
)
GLOBAL_SCOPE = rx(
    r"worldwide|global|world|international|across the world|around the world"
)
LIMITED_SCOPE_ACTION = rx(
    r"shutdown|shut down|closed|closing|halted|suspended|suspend|exit"
    r"|withdraw|withdrawal"
)
RELATION = rx(r"(?:revolves?|rotates?|moves?|travels?|goes|go) around|orbits|circles")

UNITS = rx(
    r"meters?|metres?|kilometers?|kilometres?|miles?|feet|foot"
    r"|kg|kilograms?|grams?|degrees?|celsius|fahrenheit|percent|%"
    r"|million|billion|trillion|thousand|crores?|crore|lakhs?|lakh|lacs?|lac"
)

QUANTITY = re.compile(
    r"(?<![a-z])(\d+(?:\.\d+)?)\s*"
    r"(meters?|metres?|kilometers?|kilometres?|miles?|feet|foot|"
    r"kg|kilograms?|grams?|degrees?|celsius|fahrenheit|percent|%|"
    r"thousand|million|billion|trillion|crores?|lakhs?|lacs?|lac|cr)"
    r"(?![a-z])"
)

NEGATED_ACTION = rx(
    r"(?:not|never|no longer)\s+(?:been\s+)?"
    r"(?:cancel\w*|deny\w*|refus\w*|reject\w*|block\w*|postpon\w*)"
)
NEGATIVE_ACTION = rx(
    r"cancel\w*|deny\w*|refus\w*|reject\w*|block\w*|"
    r"postpon\w*|suspend\w*|withdraw\w*|debunk\w*|refut\w*"
)
POSITIVE_ACTION = rx(
    r"confirm\w*|grant\w*|approv\w*|clear\w*|"
    r"go(?:es|ing)? ahead|proceed\w*"
)

RELATION_GROUPS = [set(g.split()) for g in (
    "tall taller height high higher short shorter meters metres meter metre",
    "visible visibility see seen sight",
    "independent independence freedom liberated liberation",
    "landed landing land arrived arrival",
    "built build constructed construction",
    "died death killed dead",
    "won win victory defeated lost loss",
    "born birth",
    "launched launch released release",
    "opened open closed close closing",
    "acquired acquisition bought buy purchased purchase",
    "announced announcement announces announce",
    "approved approval passed pass policy policies",
    "shutdown shut closed closing halted suspended suspend exit withdraw",
)]

ACTION_CONFLICTS = [(set(a.split()), set(b.split())) for a, b in (
    ("independent independence freedom", "rule ruled ruler ruling"),
    ("won win victory", "lost loss defeated"),
    ("opened open", "closed close closing"),
    ("launched launch released release", "planned plan expected upcoming"),
)]


# ---------- text helpers ----------

def clean(text):
    text = str(text or "").lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return text


def tokens(text):
    return re.findall(r"[a-z0-9']+", clean(text))


def stem(word):
    for _ in range(2):
        for suffix in ("ies", "ing", "ed", "es", "s"):
            if (
                word.endswith(suffix)
                and not word.endswith("ss")
                and len(word) - len(suffix) >= 3
            ):
                word = word[:-len(suffix)] + (
                    "y" if suffix == "ies" else ""
                )
                break
    return word[:-1] if word.endswith("e") and len(word) > 3 else word


def words(text):
    return {stem(w) for w in tokens(text)}


def entities(text):
    return {
        stem(w) for w in tokens(text)
        if len(w) > 2 and w not in STOP
        and not NEGATION.fullmatch(w) and not w.isdigit()
    }


def numbers(text):
    """Meaningful numbers; ordinary years (1900-2099) are ignored."""
    return {
        NUMBER_WORDS.get(t, t) for t in tokens(text)
        if t in NUMBER_WORDS or (t.isdigit() and not 1900 <= int(t) <= 2099)
    }


def quantities(text):
    """Normalize quantities and avoid counting their numbers twice."""
    text = clean(text)
    found = set()
    matches = list(QUANTITY.finditer(text))

    for match in matches:
        number, unit = match.groups()
        unit = unit.rstrip("s")
        value = float(number)

        if unit in {"cr", "crore"}:
            found.add(value * SCALE_WORDS["crore"])
        elif unit in {"lac", "lakh"}:
            found.add(value * SCALE_WORDS["lakh"])
        elif unit in SCALE_WORDS:
            found.add(value * SCALE_WORDS[unit])
        else:
            found.add((value, stem(unit)))

    # Include standalone numbers only if they are not part of a quantity.
    for match in re.finditer(r"\b\d+(?:\.\d+)?\b", text):
        if any(
            quantity.start() <= match.start() < quantity.end()
            for quantity in matches
        ):
            continue

        value = float(match.group())
        if not 1900 <= value <= 2099:
            found.add(value)

    # Number words count only when they quantify something ("two million"),
    # so "One of India's..." is not read as the quantity 1.
    for word, value in NUMBER_WORDS.items():
        if re.search(r"\b" + word + r"\s+(?:" + UNITS.pattern + r")", text):
            found.add(float(value))

    return found


def units(text):
    """Return measurement units, excluding numerical scale words."""
    return set(UNITS.findall(clean(text))) - {
        "thousand", "million", "billion", "trillion",
        "crore", "crores", "lakh", "lakhs", "lac", "lacs",
    }


def overlap(claim, title):
    ce, te = entities(claim), entities(title)
    cw, tw = words(claim), words(title)
    return (
        len(ce & te) / max(min(len(ce), len(te)), 1),
        len(cw & tw) / max(min(len(cw), len(tw)), 1),
    )


def phrase_score(claim, title):
    return SequenceMatcher(None, clean(claim), clean(title)).ratio()


# ---------- classification helpers ----------

def reported_statement(title):
    return bool(ATTRIBUTION.search(clean(title)))


def future(title):
    return bool(FUTURE.search(clean(title)))


def satire(title):
    return bool(re.search(
        r"\b(?:satire|satirical|parody|joke|jokes|funny|humorous|onion)\b",
        clean(title)
    ))


def contextual_negation(title):
    text = clean(title)
    return bool(
        CONTEXT.search(text)
        or re.search(r"\bnot\b[^.?!]{0,80}\b(?:but|rather|instead)\b", text)
    )


def attribution_only(title):
    text = clean(title)
    return bool(
        QUESTION.search(text) or ATTEMPT.search(text)
        or re.search(r"\b(?:myth|rumou?r|alleged|opinion|belief|survey|poll)\b", text)
    )


def relation_match(claim, title):
    cw, tw = words(claim), words(title)
    return any(cw & group and tw & group for group in RELATION_GROUPS)


def relation_conflict(claim, title):
    cw, tw = words(claim), words(title)
    return any(
        (cw & a and tw & b) or (cw & b and tw & a)
        for a, b in ACTION_CONFLICTS
    )


def scope_mismatch(claim, title):
    return bool(
        GLOBAL_SCOPE.search(clean(claim))
        and LIMITED_SCOPE_ACTION.search(clean(title))
        and not GLOBAL_SCOPE.search(clean(title))
    )


def relation(text):
    text = clean(text)
    match = RELATION.search(text)
    if not match:
        return None

    def side(part):
        return [
            stem(w) for w in re.findall(r"[a-z0-9]+", part)
            if w not in STOP and len(w) > 2
        ]

    before, after = side(text[:match.start()]), side(text[match.end():])
    return (before[-1], after[0]) if before and after else None


def denies(claim, title):
    cw = entities(claim)
    return any(
        len(cw & entities(clause)) >= min(2, len(cw))
        and (NEGATION.search(clause) or DENIAL.search(clause))
        for clause in re.split(
            r"[.!?:;]|\b(?:but|however|although|while)\b", clean(title)
        )
    )


def headline_polarity(text):
    """Return 1 for positive, -1 for negative, or 0 if unclear."""
    text = clean(text)

    if NEGATED_ACTION.search(text):
        return 1
    if NEGATIVE_ACTION.search(text):
        return -1
    if POSITIVE_ACTION.search(text) or re.search(
        r"\bnot\s+(?:cancelled|canceled|denied|rejected|postponed)\b", text
    ):
        return 1

    return 0


# ---------- relevance ----------

def relevant(claim, title):
    claim, title = clean(claim), clean(title)

    if not words(claim) or not words(title):
        return False

    claim_quantities = quantities(claim)
    title_quantities = quantities(title)

    # If both texts state quantities, they must agree.
    # Do not reject a headline solely because it omits the number.
    if (
        claim_quantities and title_quantities
        and not claim_quantities.intersection(title_quantities)
    ):
        return False

    claim_units, title_units = units(claim), units(title)
    if (
        claim_units and title_units
        and not claim_units.intersection(title_units)
    ):
        return False

    ent, word = overlap(claim, title)
    phrase = phrase_score(claim, title)

    if relation_match(claim, title):
        return ent >= 0.40 and word >= 0.25

    return (
        (ent >= 0.40 and word >= 0.25)
        or (ent >= 0.35 and phrase >= 0.30)
        or (word >= 0.40 and phrase >= 0.30)
    )


# ---------- evidence classification ----------

def measurement_match(claim, title):
    cq, tq = quantities(claim), quantities(title)
    return bool(
        cq and tq and cq.intersection(tq)
        and entities(claim).intersection(entities(title))
    )


def contradiction(claim, title):
    claim, title = clean(claim), clean(title)

    if future(title) or contextual_negation(title) or attribution_only(title):
        return False

    if scope_mismatch(claim, title):
        return True

    if not relevant(claim, title):
        return False

    claim_polarity = headline_polarity(claim)
    title_polarity = headline_polarity(title)

    if claim_polarity and title_polarity:
        return claim_polarity != title_polarity

    claim_neg = bool(NEGATION.search(claim))
    title_neg = bool(NEGATION.search(title))

    if claim_neg != title_neg:
        return True

    claim_rel, title_rel = relation(claim), relation(title)
    return bool(
        (claim_rel and title_rel and claim_rel == title_rel[::-1])
        or DENIAL.search(title)
        or denies(claim, title)
    )


def fact_check_type(claim, title):
    """Fact-check headlines paraphrase the claim, so judge them on entity overlap + verdict words."""
    if overlap(claim, title)[0] < 0.30:
        return "neutral"
    if FC_FALSE.search(title):
        return "direct_contradiction"
    return "direct_support" if FC_TRUE.search(title) and not NEGATION.search(title) else "neutral"


def evidence_type(claim, title, fact_check=False):
    claim, title = clean(claim), clean(title)

    if fact_check or title.startswith(("fact check", "factcheck", "fact-check")):
        return fact_check_type(claim, title)

    if satire(title) or attribution_only(title) or contextual_negation(title):
        return "neutral"

    if not relevant(claim, title):
        return "neutral"

    ent, word = overlap(claim, title)
    claim_polarity = headline_polarity(claim)
    title_polarity = headline_polarity(title)

    if claim_polarity and title_polarity:
        return (
            "direct_support"
            if claim_polarity == title_polarity
            else "direct_contradiction"
        )

    if relation_conflict(claim, title) and ent >= 0.35 and word >= 0.25:
        return "direct_contradiction"

    if contradiction(claim, title):
        return "direct_contradiction"

    if measurement_match(claim, title):
        return "direct_support"

    claim_rel, title_rel = relation(claim), relation(title)
    if claim_rel and title_rel:
        return "direct_support" if claim_rel == title_rel else "neutral"

    return "direct_support" if ent >= 0.60 and word >= 0.25 else "neutral"


def stance(claim, title, fact_check=False):
    return {
        "direct_support": "supporting",
        "direct_contradiction": "contradicting",
    }.get(evidence_type(claim, title, fact_check), "neutral")


def focus(claim, limit=40):
    """For a pasted article, match evidence against its headline / first sentence."""
    claim = re.sub(r"\s+", " ", str(claim or "")).strip()
    if len(claim.split()) <= limit:
        return claim
    first = re.split(r"(?<=[.!?])\s|\n", claim)[0]
    return " ".join(first.split()[:limit])


def weight(item):
    """Evidence weight: publisher credibility, doubled for professional fact-checkers."""
    score = item.get("source_score", 1)
    score = int(score) if str(score).isdigit() else 0
    return max(score, 1) * (2 if item.get("fact_check") else 1)


# ---------- source handling ----------

def is_satirical_source(source, link=""):
    source, link = clean(source), clean(link)
    return any(s in source or s in link for s in SATIRE)


def independent_count(sources):
    groups = []

    for item in sources:
        title = clean(item.get("title", ""))
        countries = {
            ALIASES.get(w, w) for w in re.findall(r"[a-z]+", title)
        } & COUNTRIES

        if not any(
            SequenceMatcher(None, title, other).ratio()
            >= (0.30 if countries & old else 0.60)
            for old, other in groups
        ):
            groups.append((countries, title))

    return len(groups)


def analyze_evidence(results, claim="", ml_prediction=None, ml_confidence=None):
    buckets = {"supporting": [], "contradicting": [], "neutral": []}
    seen = set()
    claim = focus(claim)

    for item in results or []:
        source = str(item.get("source", "")).strip().lower()
        if not source:
            continue

        key = (
            source,
            str(item.get("link", "")).strip().lower()
            or clean(item.get("title", ""))
        )

        if key in seen:
            continue
        seen.add(key)

        if is_satirical_source(source, item.get("link", "")):
            buckets["neutral"].append(item)
            continue

        buckets[stance(claim, item.get("title", ""), item.get("fact_check", False))].append(item)

    sup = buckets["supporting"]
    con = buckets["contradicting"]
    other = buckets["neutral"]

    n_sup, n_con = len(sup), len(con)

    def credible(items):
        return sum(
            (
                int(item.get("source_score", 1) or 0)
                if str(item.get("source_score", 1)).isdigit()
                else 0
            ) >= 3
            for item in items
        )

    cred_sup, cred_con = credible(sup), credible(con)
    ind_sup, ind_con = independent_count(sup), independent_count(con)
    w_sup, w_con = sum(map(weight, sup)), sum(map(weight, con))
    fc_sup = sum(bool(i.get("fact_check")) for i in sup)
    fc_con = sum(bool(i.get("fact_check")) for i in con)

    ml_label = None if ml_prediction is None else ("Real" if int(ml_prediction) == 1 else "Fake")
    reasons = [r for r in (
        fc_con and f"{fc_con} fact-check(s) rate this claim false or misleading",
        fc_sup and f"{fc_sup} fact-check(s) support this claim",
        n_sup and f"{n_sup} report(s) support the claim ({cred_sup} from credible outlets)",
        n_con and f"{n_con} report(s) contradict the claim ({cred_con} from credible outlets)",
        ml_label and f"Language model reads it as {ml_label.lower()} news ({ml_confidence}% confidence)",
    ) if r]

    def build(verdict, strength, explanation):
        if ml_label and verdict == "Unable to Verify":
            explanation += f" The language model leans {ml_label.lower()} ({ml_confidence}%)."
        return {
            "score": round(100 * w_sup / (w_sup + w_con)) if w_sup + w_con else None,
            "ml_label": ml_label,
            "fact_checks": fc_sup + fc_con,
            "reasons": reasons,
            "verdict": verdict,
            "evidence_strength": strength,
            "supporting_count": n_sup,
            "contradicting_count": n_con,
            "neutral_count": len(other),
            "supporting_sources": sup,
            "contradicting_sources": con,
            "other_sources": other,
            "credible_sources": cred_sup + cred_con,
            "independent_sources": max(ind_sup, ind_con),
            "explanation": explanation,
        }

    if not results:
        return build(
            "Unable to Verify", "Low",
            "No news search results were returned."
        )

    if fc_con and not fc_sup:
        return build(
            "Likely Misinformation", "High" if fc_con >= 2 or cred_con >= 2 else "Medium",
            "Professional fact-checkers have rated this claim false or misleading."
        )

    if n_sup and n_con:
        verdict = (
            "Possibly Misinformation" if w_con > w_sup * 1.25
            else "Possibly Reliable" if w_sup > w_con * 1.25
            else "Conflicting Evidence"
        )
        return build(
            verdict,
            "Medium" if cred_sup + cred_con >= 2 else "Low",
            "Both supporting and contradicting reports were found."
        )

    if ind_con >= 2 and not n_sup:
        return build(
            "Likely Misinformation",
            "High" if cred_con >= 2 else "Medium",
            "Multiple independent reports contradict the claim."
        )

    if ind_sup >= 2 and not n_con:
        return build(
            "Likely Reliable",
            "High" if cred_sup >= 2 else "Medium",
            "Multiple independent reports support the claim."
        )

    if n_con:
        return build(
            "Possibly Misinformation",
            "Medium" if cred_con else "Low",
            "A relevant report contradicts the claim."
        )

    if n_sup:
        return build(
            "Possibly Reliable",
            "Medium" if cred_sup else "Low",
            "A relevant report supports the claim."
        )

    return build(
        "Unable to Verify", "Low",
        "The ML model produced a prediction, but the retrieved articles "
        "did not provide enough classified evidence to verify the claim."
    )
