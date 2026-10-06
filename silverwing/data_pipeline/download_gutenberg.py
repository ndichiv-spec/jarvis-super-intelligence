"""
PHASE 2 — Data Acquisition: Project Gutenberg Books (Public Domain)

Downloads public-domain books from Project Gutenberg.
Targets ~6M+ tokens from ~32 high-quality books across
prose, science, technology, and literature.

Modular: Run independently, produces raw text files.
"""
import json
import os
import time
import urllib.request
from pathlib import Path

GUTENBERG_BASE = "https://www.gutenberg.org/files"
OUTPUT_DIR = Path("silverwing/data_pipeline/raw/gutenberg")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BOOKS = [
    # Literature (prose quality)
    (1342, "Pride_and_Prejudice", "Pride and Prejudice by Jane Austen"),
    (84, "Frankenstein", "Frankenstein by Mary Wollstonecraft Shelley"),
    (1661, "Sherlock_Holmes", "The Complete Sherlock Holmes by Arthur Conan Doyle"),
    (11, "Alice_in_Wonderland", "Alice's Adventures in Wonderland by Lewis Carroll"),
    (7146, "Origin_of_Species", "The Origin of Species by Charles Darwin"),
    (98, "Dracula", "Dracula by Bram Stoker"),
    (1635, "Rime_of_the_Ancient_Marin", "The Rime of the Ancient Mariner"),
    (20203, "The_War_of_the_Worlds", "The War of the Worlds by H.G. Wells"),
    (36, "The_Call_of_the_Wild", "The Call of the Wild by Jack London"),
    (33221, "The_World_Set_Free", "The World Set Free by H.G. Wells"),
    (1098, "Autobiography_of_Benjamin_Franklin", "The Autobiography of Benjamin Franklin"),
    (1300, "The_Republic", "The Republic by Plato"),
    (14832, "The_Art_of_War", "The Art of War by Sun Tzu"),
    (20201, "The_Time_Machine", "The Time Machine by H.G. Wells"),
    (844, "The_Three_Musketeers", "The Three Musketeers by Alexandre Dumas"),
    (55, "Metamorphosis", "Metamorphosis by Franz Kafka"),
    (3585, "An_Essay_on_Man", "An Essay on Man by Alexander Pope"),
    (1184, "Dubliners", "Dubliners by James Joyce"),
    (25495, "The_Problems_of_Philosophy", "The Problems of Philosophy by Bertrand Russell"),
    (19408, "The_Analysis_of_Mind", "The Analysis of Mind by Bertrand Russell"),
    # Additional books for scaling
    (2701, "A_Tale_of_Two_Cities", "A Tale of Two Cities by Charles Dickens"),
    (7668, "Huckleberry_Finn", "The Adventures of Huckleberry Finn by Mark Twain"),
    (1066, "Tom_Sawyer", "The Adventures of Tom Sawyer by Mark Twain"),
    (840, "Hard_Times", "Hard Times by Charles Dickens"),
    (6177, "Paradise_Lost", "Paradise Lost by John Milton"),
    (41444, "Jekyll_and_Hyde", "The Strange Case of Dr Jekyll and Mr Hyde by R.L. Stevenson"),
    (2852, "Hound_of_the_Baskervilles", "The Hound of the Baskervilles by A.C. Doyle"),
    (2865, "Last_of_the_Mohicans", "The Last of the Mohicans by James Fenimore Cooper"),
    (11844, "The_Count_of_Monte_Cristo", "The Count of Monte Cristo by Alexandre Dumas"),
    (3748, "The_Odyssey", "The Odyssey by Homer (translated by Butler)"),
    (2400, "The_Lost_World", "The Lost World by Arthur Conan Doyle"),
    (25483, "The_Federalist_Papers", "The Federalist Papers by Alexander Hamilton, Madison, Jay"),
    # Large classic works for scaling toward ~10M tokens
    (3737, "Don_Quixote", "Don Quixote by Miguel de Cervantes"),
    (6130, "The_Iliad", "The Iliad by Homer (translated by Lang/Leaf/Buckley)"),
    (23693, "Shakespeare_Complete", "The Complete Works of William Shakespeare"),
    (2269, "Canterbury_Tales", "The Canterbury Tales by Geoffrey Chaucer"),
    (2472, "Dorian_Gray", "The Picture of Dorian Gray by Oscar Wilde"),
    (16, "The_Prince", "The Prince by Niccolo Machiavelli"),
    (1010, "Bible_Genesis", "The Holy Bible (KJV) - Genesis, Exodus, Leviticus"),
    (23189, "Keats_Poems", "The Complete Poems of John Keats"),
    (10666, "Complete_Poe", "The Complete Works of Edgar Allan Poe"),
    (2360, "Thirty_Nine_Steps", "The Thirty-Nine Steps by John Buchan"),
    (147, "Secret_Garden", "The Secret Garden by Frances Hodgson Burnett"),
    (8207, "Nature", "Nature by Ralph Waldo Emerson"),
    (514, "Peter_Rabbit", "The Tale of Peter Rabbit by Beatrix Potter"),
]


def download_book(book_id, filename, description):
    """Download a single Gutenberg book."""
    dest = OUTPUT_DIR / f"{filename}.txt"
    # Skip if already downloaded and large enough
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  [SKIP] {filename}: already exists ({dest.stat().st_size:,} bytes)")
        return None

    # Try different URL formats
    urls = [
        f"{GUTENBERG_BASE}/{book_id}/{book_id}-0.txt",
        f"{GUTENBERG_BASE}/{book_id}/{book_id}.txt",
        f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt",
    ]

    for url in urls:
        try:
            print(f"  Trying: {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Silverwing-12M/1.0"})
            resp = urllib.request.urlopen(req, timeout=60)
            content = resp.read()
            if len(content) > 1000:
                with open(dest, "wb") as f:
                    f.write(content)
                text = content.decode("utf-8", errors="replace")
                tokens_est = len(text) // 4
                print(f"  Downloaded: {len(content):,} bytes (~{tokens_est:,} tokens) -> {dest}")
                return {"id": book_id, "filename": filename, "chars": len(text), "tokens": tokens_est, "url": url}
        except Exception as e:
            print(f"  Failed: {e}")
    return None


def main():
    print("=== Project Gutenberg Data Acquisition ===")
    print(f"Target: ~6M+ tokens from {len(BOOKS)} public domain books")
    print()

    results = []
    total_tokens = 0
    total_chars = 0

    for book_id, filename, description in BOOKS:
        print(f"\n  [{description}]")
        result = download_book(book_id, filename, description)
        if result:
            results.append(result)
            total_tokens += result["tokens"]
            total_chars += result["chars"]
            print(f"  Running total: {total_tokens:,} tokens")
        time.sleep(0.5)  # Rate limit

    # Save book list
    with open(OUTPUT_DIR / "gutenberg_books.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n=== Gutenberg Acquisition Complete ===")
    print(f"  Books downloaded: {len(results)}")
    print(f"  Total chars: {total_chars:,}")
    print(f"  Estimated tokens: {total_tokens:,}")
    print(f"  Output dir: {OUTPUT_DIR}")

    return {"books": len(results), "tokens": total_tokens, "chars": total_chars}


if __name__ == "__main__":
    result = main()
    summary_path = OUTPUT_DIR / "acquisition_summary.json"
    with open(summary_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Summary saved to: {summary_path}")
