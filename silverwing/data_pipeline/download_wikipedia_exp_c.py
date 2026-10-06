"""Download Wikipedia articles for Experiment C (50M token dataset).

Uses the Wikipedia REST API (https://en.wikipedia.org/api/rest_v1/) to fetch
article content. This avoids the MediaWiki API's HTTP 429 rate limiting.

USAGE:
    python download_wikipedia_exp_c.py --target_tokens 18000000 --output silverwing/data_pipeline/raw/wikipedia_exp_c.jsonl
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path


def fetch_wikipedia_article(title: str, session=None) -> str | None:
    """Fetch a single Wikipedia article's plain text via REST API."""
    url = f"https://en.wikipedia.org/api/rest_v1/page/html/{urllib.parse.quote(title)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Silverwing-Experiment-C/1.0 (educational LLM training; contact: research@poolside.ai)"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  HTTP {e.code} for '{title}'")
        return None
    except Exception as e:
        print(f"  Error fetching '{title}': {e}")
        return None

    # Extract text from HTML (basic tag stripping)
    import re
    # Remove script and style blocks
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove reference markers
    text = re.sub(r'\[\d+\]', '', text)
    return text


def get_wikipedia_titles_list(n: int) -> list[str]:
    """Get a list of Wikipedia article titles from the REST API's page lists."""
    # Using the REST API to get most-viewed pages
    url = "https://en.wikipedia.org/api/rest_v1/data/wikitext/en.viki"
    # Fallback: use a curated list of common Wikipedia titles
    curated_titles = [
        "United States", "United Kingdom", "France", "Germany", "Japan",
        "China", "India", "Brazil", "Russia", "Canada",
        "World War II", "World War I", "Cold War", "French Revolution",
        "Industrial Revolution", "Renaissance", "Ancient Rome", "Greek civilization",
        "Napoleonic Wars", "American Civil War", "Scientific Revolution",
        "Physics", "Chemistry", "Biology", "Mathematics", "Astronomy",
        "Evolution", "Darwin", "Newton", "Einstein", "Tesla",
        "Shakespeare", "William Shakespeare", "Homer", "Dante", "Cervantes",
        "Leonardo da Vinci", "Michelangelo", "Beethoven", "Mozart",
        "Computer", "Internet", "Artificial intelligence", "Machine learning",
        "Democracy", "Capitalism", "Socialism", "Communism", "Philosophy",
        "Psychology", "Sociology", "Economics", "Anthropology", "History",
    ]
    # Get more titles via the REST API's 'page/summary' endpoint for popular pages
    more_titles = []
    for title in curated_titles:
        more_titles.append(title)
        if len(more_titles) >= n:
            break

    # If we need more, fetch from Wikipedia's REST API page lists
    if len(more_titles) < n:
        # Use the REST API to get a list of article titles
        for batch_start in range(0, n - len(more_titles), 500):
            url = f"https://en.wikipedia.org/w/api.php?action=query&list=allpages&aplimit=500&apfrom={batch_start}&format=json"
            # This might get rate limited, so use a simple approach
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Silverwing-Experiment-C/1.0"
                })
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                for page in data.get("query", {}).get("allpages", []):
                    more_titles.append(page["title"])
                    if len(more_titles) >= n:
                        break
            except Exception as e:
                print(f"Failed to fetch title batch at {batch_start}: {e}")
                if len(more_titles) > len(curated_titles):
                    break
            time.sleep(1)

    return more_titles[:n]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_tokens", type=int, default=18_000_000,
                        help="Target number of tokens to collect")
    parser.add_argument("--output", type=str,
                        default="silverwing/data_pipeline/raw/wikipedia_exp_c.jsonl")
    parser.add_argument("--max_articles", type=int, default=2500,
                        help="Maximum number of articles to fetch")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between API requests (seconds)")
    args = parser.parse_args()

    print(f"Experiment C Wikipedia Download")
    print(f"  Target: ~{args.target_tokens:,} tokens ({args.max_articles} articles)")
    print(f"  Output: {args.output}")
    print(f"  Delay: {args.delay}s between requests")
    print()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get article titles
    print("[1/3] Fetching article titles...")
    titles = get_wikipedia_titles_list(args.max_articles)
    print(f"  Got {len(titles)} article titles")

    # Fetch articles
    print(f"\n[2/3] Fetching articles (target ~{args.target_tokens:,} tokens)...")
    total_chars = 0
    articles_saved = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for i, title in enumerate(titles):
            text = fetch_wikipedia_article(title)
            if text:
                record = {"title": title, "text": text, "chars": len(text)}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_chars += len(text)
                articles_saved += 1

                if (i + 1) % 50 == 0:
                    approx_tokens = total_chars // 4
                    pct = min(100.0, total_chars / (args.target_tokens * 4) * 100)
                    print(f"  [{i+1}/{len(titles)}] {articles_saved} articles | "
                          f"~{approx_tokens:,} tokens ({pct:.1f}% of target) | "
                          f"last: {title}")

                if total_chars >= args.target_tokens * 4:
                    print(f"  Target reached! Stopping at {articles_saved} articles.")
                    break
            else:
                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(titles)}] Skipped: {title}")

            time.sleep(args.delay)

    approx_tokens = total_chars // 4
    print(f"\n[3/3] Done!")
    print(f"  Articles saved: {articles_saved}")
    print(f"  Total chars: {total_chars:,}")
    print(f"  Approx tokens: {approx_tokens:,}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    import urllib.parse
    main()
