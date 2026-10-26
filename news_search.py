
"""Search Google News RSS and rank relevant news articles."""

import csv
import re
import time
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup


STOP = {
    "the", "and", "for", "with", "that", "this", "from", "have",
    "has", "was", "were", "are", "will", "its", "into", "about",
    "after", "before", "been", "being", "their", "they", "said",
    "says", "news", "report", "reports", "latest", "new", "claim"
}

RULES_PATH = Path(__file__).resolve().parent / "data" / "evidence_rules.csv"

with RULES_PATH.open(encoding="utf-8", newline="") as file:
    RULES = list(csv.DictReader(file))

GLOBAL_TERMS = {
    r["value"].lower() for r in RULES
    if r["type"] == "scope" and r["category"] == "global"
}

# Professional fact-checkers: strongest evidence for or against a claim
FACT_CHECKERS = {
    "factcheck.pib.gov.in": 5, "pib.gov.in": 5, "altnews.in": 5, "boomlive.in": 5,
    "factly.in": 5, "vishvasnews.com": 5, "newschecker.in": 5, "thequint.com": 4,
    "snopes.com": 5, "politifact.com": 5, "factcheck.org": 5, "fullfact.org": 5,
    "factcheck.afp.com": 5, "leadstories.com": 4, "logicallyfacts.com": 4
}
FACT_CHECK_NAMES = (
    "pib fact check", "alt news", "boom", "factly", "vishvas news", "newschecker",
    "snopes", "politifact", "factcheck.org", "full fact", "afp fact check", "lead stories"
)

# Known publisher domains and configured source scores
NEWS_SOURCES = {
    "reuters.com": 5,
    "apnews.com": 5,
    "bbc.com": 5,
    "bbc.co.uk": 5,
    "thehindu.com": 4,
    "indianexpress.com": 4,
    "ndtv.com": 4,
    "hindustantimes.com": 4,
    "wionews.com": 4,
    "indiatimes.com": 4,
    "ipowatch.in": 3,
    "economictimes.indiatimes.com": 3,
    "cnbctv18.com": 3,
    "theindianpanorama.news": 3,
    "theguardian.com": 4,
    "aljazeera.com": 4,
    "bloomberg.com": 4,
    "ft.com": 4,
    "washingtonpost.com": 4,
    "nytimes.com": 4,
    "cnbc.com": 4,
    "moneycontrol.com": 3,
    "business-standard.com": 3,
    "livemint.com": 3,
    "indiatoday.in": 3,
    "cnn.com": 3,
    "forbes.com": 3,
    "techcrunch.com": 3,
    "theverge.com": 3,
    "scroll.in": 3,
    "deccanherald.com": 3,
    "yourstory.com": 3,
    "inc42.com": 3,
    "financialexpress.com": 3,
    "economictimes.com": 3,
    "theprint.in": 3,
    "firstpost.in": 3,
    "firstpost.com": 3
}

SOCIAL_DOMAINS = {
    "facebook.com", "instagram.com", "x.com", "twitter.com",
    "youtube.com", "youtu.be", "linkedin.com", "tiktok.com",
    "reddit.com", "threads.net", "pinterest.com", "snapchat.com",
    "whatsapp.com", "t.me", "telegram.org"
}

OFFICIAL_ACCOUNTS = {
    "press information bureau": 5,
    "pib india": 5,
    "isro": 5,
    "nasa": 5,
    "world health organization": 5,
    "who": 5,
    "united nations": 5,
    "reserve bank of india": 5,
    "rbi": 5,
    "election commission of india": 5,
    "ministry of health and family welfare": 5
}

# Publisher-name fallbacks for Google News RSS results
PUBLISHER_SCORES = {
    5: [
        "reuters", "associated press", "ap news",
        "bbc", "nasa", "isro"
    ],
    4: [
        "the hindu", "indian express", "ndtv",
        "hindustan times", "wion", "times of india",
        "the guardian", "al jazeera", "bloomberg",
        "economic times", "news on air", "newsonair",
        "france 24", "new indian express", "cnbc tv18"
    ],
    3: [
        "assam tribune", "moneycontrol", "business standard",
        "livemint", "india today", "cnn", "forbes",
        "techcrunch", "swarajya", "news24online",
        "free press journal", "rediff", "the statesman",
        "outlook india", "cricket addictor", "gujarat samachar",
        "open magazine", "news mobile", "daily excelsior",
        "etv bharat", "upstox", "apa.az", "swarajyamag",
        "times now", "telangana today", "news18",
        "lokmat times", "free press kashmir",
        "marine insight", "firstpost"
    ]
}


def get_domain(url):
    if not url:
        return ""

    url = str(url).strip()
    if "://" not in url:
        url = "//" + url

    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def is_social_source(source, link=""):
    domains = (get_domain(source), get_domain(link))
    return any(
        domain == site or domain.endswith("." + site)
        for site in SOCIAL_DOMAINS
        for domain in domains
        if domain
    )


def is_fact_checker(source, link=""):
    name, domains = str(source or "").lower(), (get_domain(link), get_domain(source))
    return any(n in name for n in FACT_CHECK_NAMES) or any(
        d and (d == s or d.endswith("." + s)) for d in domains for s in FACT_CHECKERS)


def get_source_score(source, link=""):
    source_name = re.sub(r"\s+", " ", str(source or "").lower()).strip()

    # Match recognized publisher domains, most specific first
    # (economictimes.indiatimes.com before indiatimes.com).
    for domain in (get_domain(link), get_domain(source)):
        for site, score in sorted({**NEWS_SOURCES, **FACT_CHECKERS}.items(), key=lambda kv: -len(kv[0])):
            if domain and (domain == site or domain.endswith("." + site)):
                return score

    # Match official institutional publishers.
    if source_name in OFFICIAL_ACCOUNTS:
        return OFFICIAL_ACCOUNTS[source_name]

    # Match publisher names supplied by Google News RSS.
    for score, names in PUBLISHER_SCORES.items():
        if any(name in source_name for name in names):
            return score

    # Social accounts are not automatically credible.
    if is_social_source(source, link):
        return 0

    return 1


def clean_text(text):
    text = str(text or "")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s-]", " ", text)).strip()


def create_search_queries(text):
    cleaned = clean_text(text)
    if not cleaned:
        return []

    words = [
        word for word in cleaned.split()
        if len(word) > 3 and word.lower() not in STOP
    ]

    if not words:
        return [cleaned]

    main = " ".join(words[:10])
    # Exact-phrase search only for short claims; a long article makes a useless URL.
    queries = ([f'"{cleaned}"'] if len(cleaned.split()) <= 14 else []) + [main, main + " fact check"]

    if any(term in cleaned.lower() for term in GLOBAL_TERMS):
        queries += [
            main + " worldwide",
            main + " global operations",
            main + " continues operations",
            main + " expansion"
        ]

        if re.search(
            r"\b(shut down|shutdown|close|closure|exit|withdraw)\b",
            cleaned.lower()
        ):
            subject = " ".join(words[:2])
            queries += [
                f"{subject} continues operations worldwide",
                f"{subject} global operations",
                f"{subject} expansion"
            ]

    # Keep each search query only once.
    return list(dict.fromkeys(q for q in queries if q.strip()))


def headline(title, source=""):
    """Google News titles end with " - Publisher"; drop it so it isn't matched as claim text."""
    title = str(title or "").strip()
    if source and title.lower().endswith(" - " + str(source).lower()):
        return title[:-(len(source) + 3)].strip()
    return re.sub(r"\s+[-|]\s+[^-|]{2,60}$", "", title).strip() or title


def published_ts(value):
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, IndexError):
        return 0


def result_score(title, claim):
    """Measure how much of the claim's meaningful vocabulary appears in a title."""
    title_words = {
        word.lower() for word in clean_text(title).split()
        if len(word) > 3 and word.lower() not in STOP
    }
    claim_words = {
        word.lower() for word in clean_text(claim).split()
        if len(word) > 3 and word.lower() not in STOP
    }

    if not claim_words:
        return 0

    return len(title_words & claim_words) / len(claim_words)


def get_article_body(url):
    """Attempt to retrieve article text; return an empty string if unavailable."""
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=3
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        paragraphs = soup.find_all("p")
        return " ".join(
            paragraph.get_text(" ", strip=True)
            for paragraph in paragraphs
        )[:8000]

    except (requests.RequestException, ValueError):
        return ""
    except Exception:
        return ""


_CACHE = {}
CACHE_SECONDS = 600


def fetch_feed(search):
    """Fetch one Google News RSS query; results are cached for 10 minutes."""
    hit = _CACHE.get(search)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]

    print("\nTRUTHLENS SEARCH QUERY:")
    print(search)
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(search)}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        response.raise_for_status()
        entries = feedparser.parse(response.content).entries
        _CACHE[search] = (time.time(), entries)
        return entries
    except requests.RequestException as error:
        print("Search error:", error)
    except Exception as error:
        print("Feed processing error:", error)
    return []


def search_news(query, max_results=5):
    """Search Google News and return ranked, deduplicated article metadata."""
    try:
        max_results = max(1, int(max_results))
    except (TypeError, ValueError):
        max_results = 5

    results = []
    seen_articles = set()
    queries = create_search_queries(query)

    # Run all queries at the same time instead of one after another.
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(queries)))) as pool:
        feeds = list(pool.map(fetch_feed, queries))

    for entries in feeds:
        for entry in entries:
            raw_title = str(entry.get("title", "")).strip()
            link = str(entry.get("link", "")).strip()

            if not raw_title or not link:
                continue

            publisher = entry.get("source", {})
            source = (
                str(publisher.get("title", "")).strip()
                if hasattr(publisher, "get") else ""
            )
            # Real publisher site (the link itself is a Google redirect).
            site = str(publisher.get("href", "")).strip() if hasattr(publisher, "get") else ""

            if not source:
                source = get_domain(link) or "Unknown Source"

            # Skip social-media results unless identified as an official account.
            if is_social_source(source, site or link):
                if source.lower().strip() not in OFFICIAL_ACCOUNTS:
                    continue

            title = headline(raw_title, source)

            # Same story syndicated under different links counts once.
            key = re.sub(r"\W+", " ", title.lower()).strip()
            if key in seen_articles:
                continue
            seen_articles.add(key)

            results.append({
                "title": title,
                "link": link,
                "published": entry.get("published", ""),
                "published_ts": published_ts(entry.get("published", "")),
                "source": source,
                "site": get_domain(site),
                "source_score": get_source_score(source, site or link),
                "fact_check": is_fact_checker(source, site),
                "search_score": result_score(title, query),
                "body": ""
            })

    results.sort(
        key=lambda item: (
            round(item["search_score"], 1),
            item["fact_check"],
            item["source_score"],
            item["published_ts"]
        ),
        reverse=True
    )

    results = results[:max_results * 2]

    print(f"\nTOP RESULTS SELECTED: {len(results)}")
    return results
