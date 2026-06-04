"""
KYC Name Screening — Flask app for Vercel
==========================================
A web version of the desktop name-screening tool, designed for serverless
deployment on Vercel. Renders a Google-style results page with numbered
badges (1–20) and risk classification for each result.

Data sources, in order of preference:
  1. SerpAPI (real Google results) — set env var SERPAPI_API_KEY
  2. Demo mode — realistic sample results, used when no key is set

Why no Playwright/headed Chrome? Vercel's serverless runtime has no GUI,
no display server, and a hard 10s execution limit on the Hobby tier, so
the original desktop approach (open Chrome, solve CAPTCHA, screenshot)
cannot run there. Instead, this version pulls structured search data via
API and renders a faithful Google-styled view with numbered overlays —
the visual output a bank reviewer would see, generated server-side.
"""

import os
import re
import urllib.parse
from datetime import datetime

import requests
from flask import Flask, render_template, request

app = Flask(__name__, template_folder="../templates", static_folder="../static")


# ─── QUERY TEMPLATES (same logic as the desktop script) ─────────────────────
QUERIES = [
    {
        "id": "Q1",
        "label": "Adverse News",
        "description": "Fraud, crime, corruption, legal proceedings",
        "is_adverse": True,
        "template": (
            '"{name}" AND (launde* OR lawsuit OR scandal OR fraud OR illegal '
            'OR criminal OR crime OR convic* OR guilt OR arrest OR corrup* '
            'OR accused OR kickback OR investigat* OR bribe* OR unethical '
            'OR Ponzi OR terrorist OR terrorism OR "Tax crime" '
            'OR "Tax evasion" OR "evade tax")'
        ),
    },
    {
        "id": "Q2",
        "label": "PEP & Associations",
        "description": "Political exposure, ownership, affiliations",
        "is_adverse": False,
        "template": (
            '"{name}" AND (stat* OR owner* OR politic* OR expos* OR government* '
            'OR agenc* OR ministr* OR nationa* OR officia* OR famil* '
            'OR associat* OR direct* OR busines* OR parent* OR siblin* '
            'OR childre*)'
        ),
    },
]


CLASS_META = {
    "FULL_MATCH_ADVERSE":  {"label": "Full match — adverse news",     "tone": "danger"},
    "FULL_MATCH_CLEAN":    {"label": "Full match — no adverse news",  "tone": "success"},
    "PARTIAL_MATCH_CLEAN": {"label": "Partial match — no adverse news", "tone": "warning"},
    "FALSE_MATCH":         {"label": "False name match",              "tone": "info"},
    "UNRELATED":           {"label": "Unrelated / unclear",           "tone": "muted"},
}

ADVERSE_KEYWORDS = [
    "fraud", "scam", "scandal", "launder", "money laundering", "convicted",
    "conviction", "arrest", "arrested", "charged", "guilty", "guilt",
    "corrupt", "corruption", "bribe", "bribery", "kickback", "investigat",
    "indict", "embezz", "fined", "penalty", "sanction", "blacklist",
    "lawsuit", "litigat", "court", "prosecut", "criminal", "crime",
    "illegal", "unethical", "ponzi", "terror", "tax evasion", "tax crime",
    "evade tax", "evading tax", "accused", "alleged",
]
PEP_KEYWORDS = [
    "minister", "ministry", "government", "official", "politician",
    "political", "state-owned", "state owned", "parliament", "senator",
    "president", "ambassador", "judge", "central bank", "regulator",
    "agency", "diplomat", "appointee", "appointed by", "head of state",
]
POSITIVE_CONTEXT = [
    "linkedin", "biography", "wikipedia", "interview", "announces",
    "appointed", "celebrates", "awards", "graduated", "speaker",
]
FALSE_MATCH_SIGNALS = [
    "different", "another person", "not to be confused", "namesake",
    "person of the same name", "homonym",
]


# ─── CLASSIFY ────────────────────────────────────────────────────────────────
def classify(name, snippet, title, is_adverse_query):
    text = f"{title} {snippet}".lower()
    name_lower = name.lower()
    name_mentioned = name_lower in text or any(
        part.lower() in text for part in name.split() if len(part) > 2
    )
    adverse_hits = [kw for kw in ADVERSE_KEYWORDS if kw in text]
    pep_hits = [kw for kw in PEP_KEYWORDS if kw in text]
    relevant_hits = adverse_hits if is_adverse_query else pep_hits

    if any(s in text for s in FALSE_MATCH_SIGNALS):
        return {"match_type": "FALSE_MATCH", "detail": None,
                "reason": "Different person sharing the name"}
    if not name_mentioned:
        return {"match_type": "UNRELATED", "detail": None,
                "reason": "Subject name not mentioned"}
    if relevant_hits:
        return {
            "match_type": "FULL_MATCH_ADVERSE",
            "detail": f"Keywords detected: {', '.join(relevant_hits[:5])}",
            "reason": f"Name alongside {'adverse' if is_adverse_query else 'PEP'} keywords",
        }
    if any(p in text for p in POSITIVE_CONTEXT):
        return {"match_type": "FULL_MATCH_CLEAN", "detail": None,
                "reason": "Positive/neutral context"}
    return {"match_type": "PARTIAL_MATCH_CLEAN", "detail": None,
            "reason": "Name mentioned but unclear context"}


# ─── DATA SOURCES ────────────────────────────────────────────────────────────
def fetch_serpapi(query, num=20):
    """Real Google results via SerpAPI. Returns list of dicts or None on error."""
    key = os.environ.get("SERPAPI_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": query,
                "num": num,
                "hl": "en",
                "gl": "sg",
                "api_key": key,
            },
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        organic = data.get("organic_results", [])[:num]
        return [
            {
                "title": o.get("title", ""),
                "url": o.get("link", ""),
                "snippet": o.get("snippet", ""),
                "displayed_url": o.get("displayed_link", ""),
            }
            for o in organic
        ]
    except Exception:
        return None


def demo_results(name, is_adverse):
    """Realistic sample data for the demo when no SerpAPI key is configured."""
    safe = name.strip() or "Subject"
    if is_adverse:
        templates = [
            ("LinkedIn", f"{safe} - Profile", f"{safe} is a finance professional based in Singapore...", "linkedin.com/in/profile"),
            ("Bloomberg", f"Court filing names {safe} in alleged fraud probe", f"Regulators have opened an investigation into transactions linked to {safe}, sources said.", "bloomberg.com/news"),
            ("Wikipedia", f"{safe} — Wikipedia", f"{safe} is an entrepreneur known for several ventures across Southeast Asia.", "en.wikipedia.org/wiki"),
            ("Straits Times", f"{safe} charged with bribery offences", f"Authorities have charged {safe} with corruption and bribery linked to a 2022 contract.", "straitstimes.com/singapore"),
            ("Crunchbase", f"{safe} - Founder & CEO", f"Profile and funding history of {safe}, founder of a regional fintech.", "crunchbase.com/person"),
            ("Reuters", f"Money laundering case: {safe} named", f"Court documents reviewed by Reuters name {safe} among defendants in an alleged money laundering scheme.", "reuters.com/world"),
            ("Forbes", f"{safe} — interview with Forbes", f"In a recent interview, {safe} discussed regional expansion plans.", "forbes.com/profile"),
            ("Channel News Asia", f"Tax evasion probe widens; {safe} questioned", f"Inland Revenue officers have questioned {safe} over alleged tax evasion.", "channelnewsasia.com"),
            ("Nikkei Asia", f"Investor profile: {safe}", f"{safe} holds stakes in several listed entities across ASEAN markets.", "asia.nikkei.com"),
            ("Yahoo Finance", f"{safe} — different person, not the businessman", f"Another person of the same name is a teacher — not to be confused with the executive.", "finance.yahoo.com"),
            ("South China Morning Post", f"{safe} fined over kickback allegations", f"Regulator imposes penalty after {safe} found to have received kickbacks.", "scmp.com/business"),
            ("Tech in Asia", f"{safe} announces Series B funding", f"Startup led by {safe} closes Series B at undisclosed valuation.", "techinasia.com"),
            ("MAS Enforcement", f"Enforcement action against {safe}", f"MAS announces civil penalty against {safe} for breaches of securities rules.", "mas.gov.sg/news"),
            ("Twitter / X", f"Tweet by @{safe.split()[0].lower()}", f"Public posts attributed to {safe} discussing market views.", "twitter.com/user"),
            ("Local blog", f"Who is {safe}?", f"An unofficial blog post discussing the career of {safe}.", "wordpress.com/blog"),
            ("Court Records SG", f"Civil suit filed against {safe}", f"Commercial dispute filed in the High Court naming {safe} as defendant.", "elitigation.sg"),
            ("YouTube", f"{safe} keynote — fintech summit", f"Recording of {safe} giving a keynote address at a 2024 fintech event.", "youtube.com/watch"),
            ("Glassdoor", f"Reviews mentioning {safe}", f"Employee reviews reference leadership under {safe}.", "glassdoor.com/Reviews"),
            ("FT.com", f"Audit committee scrutinises {safe}", f"Financial Times reports that auditors flagged transactions involving {safe}.", "ft.com/content"),
            ("Wayback Machine", f"Archived bio of {safe}", f"Historical archive of biographical material on {safe}.", "web.archive.org"),
        ]
    else:
        templates = [
            ("LinkedIn", f"{safe} - Director", f"{safe} serves on the board of several private companies in Singapore.", "linkedin.com/in/profile"),
            ("Government Gazette", f"Appointment notice: {safe}", f"{safe} appointed as advisor to a government statutory board.", "sso.agc.gov.sg"),
            ("Wikipedia", f"{safe} — Wikipedia", f"{safe} is a businessperson with ties to several political figures.", "en.wikipedia.org/wiki"),
            ("Bloomberg", f"State-owned firm names {safe} to board", f"A state-owned enterprise has appointed {safe} as non-executive director.", "bloomberg.com/news"),
            ("Channel News Asia", f"Minister meets business leaders including {safe}", f"The Minister for Trade met executives, among them {safe}.", "channelnewsasia.com"),
            ("Companies House", f"Directorship record — {safe}", f"Filing record showing {safe} as director of three active companies.", "data.gov.sg"),
            ("Straits Times", f"{safe} family business profile", f"Profile of the {safe.split()[-1]} family's regional business holdings.", "straitstimes.com/business"),
            ("Reuters", f"{safe} attends parliamentary committee", f"Industry representative {safe} testified before a parliamentary committee.", "reuters.com/asia"),
            ("Forbes", f"{safe} — Asia's businesspeople to watch", f"Forbes profiles {safe} among rising business figures in the region.", "forbes.com/profile"),
            ("Yahoo News", f"Another {safe} — different person, schoolteacher", f"Local teacher of the same name — not to be confused with the businessman.", "news.yahoo.com"),
            ("Nikkei Asia", f"Ownership structure: {safe} group", f"Analysis of the holdings and beneficial ownership tied to {safe}.", "asia.nikkei.com"),
            ("Tech in Asia", f"{safe} joins startup advisory board", f"Veteran investor {safe} joins advisory board of a regional startup.", "techinasia.com"),
            ("South China Morning Post", f"{safe} on Belt and Road projects", f"Comments by {safe} on regional infrastructure projects.", "scmp.com/business"),
            ("Twitter / X", f"Posts by @{safe.split()[0].lower()}", f"Public posts attributed to {safe} on policy and business topics.", "twitter.com/user"),
            ("Local blog", f"Profile: {safe}", f"Independent blog discussing the career arc of {safe}.", "medium.com/blog"),
            ("ACRA BizFile", f"BizFile entity search — {safe}", f"Public registry showing director and shareholder entries for {safe}.", "bizfile.gov.sg"),
            ("YouTube", f"{safe} speaks at industry forum", f"Conference recording featuring {safe} as panellist.", "youtube.com/watch"),
            ("News.gov", f"Officials welcome {safe} delegation", f"A trade delegation led by {safe} met with government officials.", "news.gov"),
            ("FT.com", f"Family office of {safe} expands", f"FT reports the family office of {safe} is expanding into private credit.", "ft.com/content"),
            ("Wayback Machine", f"Archived corporate bio of {safe}", f"Historical archive of {safe}'s corporate biography.", "web.archive.org"),
        ]
    return [
        {"title": t[1], "url": f"https://{t[3]}", "snippet": t[2],
         "displayed_url": t[3], "source": t[0]}
        for t in templates
    ]


# ─── ASSEMBLE A QUERY RESULT BLOCK ──────────────────────────────────────────
def run_query(name, q):
    query_string = q["template"].format(name=name)
    raw = fetch_serpapi(query_string, num=20)
    used_demo = False
    if raw is None:
        raw = demo_results(name, q["is_adverse"])
        used_demo = True

    results = []
    for i, r in enumerate(raw[:20], start=1):
        cls = classify(name, r.get("snippet", ""), r.get("title", ""), q["is_adverse"])
        meta = CLASS_META[cls["match_type"]]
        results.append({
            "number": i,
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "displayed_url": r.get("displayed_url") or _displayable(r.get("url", "")),
            "snippet": r.get("snippet", ""),
            "match_type": cls["match_type"],
            "match_label": meta["label"],
            "tone": meta["tone"],
            "detail": cls["detail"],
            "reason": cls["reason"],
        })

    summary = build_summary(results, q["is_adverse"])
    google_url = (
        "https://www.google.com/search?q=" +
        urllib.parse.quote_plus(query_string) + "&hl=en&gl=sg"
    )
    return {
        "id": q["id"],
        "label": q["label"],
        "description": q["description"],
        "query_string": query_string,
        "google_url": google_url,
        "results": results,
        "summary": summary,
        "used_demo": used_demo,
    }


def _displayable(url):
    try:
        p = urllib.parse.urlparse(url)
        return f"{p.netloc}{p.path}".rstrip("/")
    except Exception:
        return url


def build_summary(results, is_adverse):
    buckets = {k: [] for k in CLASS_META}
    for r in results:
        buckets[r["match_type"]].append(r["number"])
    n_adverse = len(buckets["FULL_MATCH_ADVERSE"])
    n_partial = len(buckets["PARTIAL_MATCH_CLEAN"])
    overall = "HIGH" if n_adverse else ("MEDIUM" if n_partial else "CLEAR")
    if overall == "HIGH":
        note = (f"{n_adverse} result(s) flagged as full-match adverse "
                f"({'adverse news' if is_adverse else 'PEP exposure'}). "
                "Escalate to senior compliance.")
    elif overall == "MEDIUM":
        note = (f"No confirmed adverse findings, but {n_partial} partial match(es) "
                "require manual identity verification.")
    else:
        note = "No adverse findings detected. Standard review pathway."

    breakdown = []
    for key, meta in CLASS_META.items():
        breakdown.append({
            "key": key,
            "label": meta["label"],
            "tone": meta["tone"],
            "numbers": buckets[key],
            "count": len(buckets[key]),
        })
    return {
        "overall_risk": overall,
        "risk_message": {
            "HIGH":   "Escalate to compliance",
            "MEDIUM": "Senior review required",
            "CLEAR":  "No adverse news found",
        }[overall],
        "analyst_note": note,
        "breakdown": breakdown,
    }


# ─── ROUTES ──────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/screen", methods=["POST", "GET"])
def screen():
    name = (request.values.get("name") or "").strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        return render_template("index.html", error="Please enter a client name.")
    if len(name) > 120:
        return render_template("index.html", error="Name is too long.")

    sections = [run_query(name, q) for q in QUERIES]
    using_real = any(not s["used_demo"] for s in sections)
    timestamp = datetime.utcnow().strftime("%d %B %Y, %H:%M UTC")

    return render_template(
        "results.html",
        name=name,
        timestamp=timestamp,
        sections=sections,
        using_real=using_real,
    )


@app.route("/health")
def health():
    return {"status": "ok", "serpapi_configured": bool(os.environ.get("SERPAPI_API_KEY"))}


# Vercel's @vercel/python runtime imports `app` from this file.
# Local dev:  python api/index.py
if __name__ == "__main__":
    app.run(debug=True, port=5000)
