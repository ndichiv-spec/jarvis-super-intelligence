"""
PHASE 2 — Data Acquisition: WikiBooks Textbooks (CC BY-SA 3.0)

Downloads textbook content from WikiBooks, covering STEM topics.
Uses the parse API to get full page text.
Targets ~2M tokens from high-quality educational content.

Modular: Run independently, produces raw JSONL.
"""
import json
import os
import time
import re
import urllib.parse
import urllib.request
from pathlib import Path

WIKIBOOKS_API = "https://en.wikibooks.org/w/api.php"
USER_AGENT = "Silverwing-12M/1.0 (educational research; contact@example.com)"
OUTPUT_DIR = Path("silverwing/data_pipeline/raw/wikibooks")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# High-quality WikiBooks covering STEM and other subjects
BOOKS = [
    "Python_Programming",
    "Computer_Science",
    "Algorithms",
    "Data_Structures",
    "Circuit_Theory",
    "Calculus",
    "Linear_Algebra",
    "General_Chemistry",
    "Machine_Learning",
    "Statistics",
    "Physics_Study_Guide",
    "Quantum_Mechanics",
    "Engineering_Thermodynamics",
    "Strength_of_Materials",
    "Control_Systems",
    "Digital_Design",
    "Discrete_Mathematics",
    "Probability_and_Statistics",
    "Electronics_Anatomy",
    "Artificial_Intelligence",
]


def api_request(params, retries=5, base_delay=0.5):
    """Make a MediaWiki API request with retry logic and backoff.

    Note: respects the 'action' parameter set by the caller
    (query, parse, etc.) instead of forcing 'query'.
    """
    if "action" not in params:
        params["action"] = "query"
    params["format"] = "json"
    params["formatversion"] = "2"
    url = WIKIBOOKS_API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read())
        except Exception as e:
            wait = base_delay * (2 ** attempt)
            print(f"  API retry {attempt+1}/{retries} after {wait:.1f}s: {e}")
            time.sleep(wait)
    return None


def get_full_book(title):
    """
    Get the full text of a WikiBook using the parse API.
    """
    result = api_request({
        "page": title,
        "action": "parse",  # This will be preserved
        "prop": "text",
        "disablelimit": True,
    })
    if result and "parse" in result:
        parse_result = result["parse"]
        if "text" in parse_result:
            text_field = parse_result["text"]
            if isinstance(text_field, dict) and "*" in text_field:
                html = text_field["*"]
            elif isinstance(text_field, str):
                html = text_field
            else:
                return None
        else:
            return None
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Clean HTML entities
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#39;", "'", text)
        text = re.sub(r"&nbsp;", " ", text)
        # Remove reference markers like [1], [2]
        text = re.sub(r"\[\d+\]", "", text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()
    return None


def estimate_tokens(text):
    """Rough token estimate: ~2 chars per token for textbook text."""
    return len(text) // 2


def main():
    print("=== WikiBooks Data Acquisition ===")
    print(f"Target: ~2M tokens from {len(BOOKS)} textbooks")
    print()

    results = []
    total_tokens = 0
    total_chars = 0
    output_file = OUTPUT_DIR / "wikibooks_raw.jsonl"

    if output_file.exists():
        os.remove(output_file)

    with open(output_file, "w", encoding="utf-8") as f:
        for i, title in enumerate(BOOKS):
            print(f"  [{i+1}/{len(BOOKS)}] Fetching: {title}")

            text = get_full_book(title)
            if text and len(text) > 500:
                n_tokens = estimate_tokens(text)
                record = {
                    "source": "wikibooks",
                    "title": title,
                    "chars": len(text),
                    "tokens": n_tokens,
                    "text": text,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                results.append({"title": title, "chars": len(text), "tokens": n_tokens})
                total_tokens += n_tokens
                total_chars += len(text)
                print(f"    -> {n_tokens:,} tokens, {len(text):,} chars")
            else:
                if text is None:
                    print(f"    -> SKIPPED (not found)")
                else:
                    print(f"    -> SKIPPED (too short: {len(text)} chars)")

            time.sleep(0.3)  # Rate limit

    print(f"\n=== WikiBooks Acquisition Complete ===")
    print(f"  Books fetched: {len(results)}")
    print(f"  Total chars: {total_chars:,}")
    print(f"  Estimated tokens: {total_tokens:,}")
    print(f"  Output: {output_file}")
    print(f"  File size: {os.path.getsize(output_file):,} bytes")

    summary = {"books": len(results), "tokens": total_tokens, "chars": total_chars}
    with open(OUTPUT_DIR / "acquisition_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Summary saved to: {OUTPUT_DIR / 'acquisition_summary.json'}")
    return summary


if __name__ == "__main__":
    main()
