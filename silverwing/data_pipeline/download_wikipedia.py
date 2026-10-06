"""
PHASE 2 — Data Acquisition: Wikipedia Articles (CC BY-SA 3.0)

Uses the Wikimedia REST API which has more generous rate limits.
Fetches full article HTML and extracts plain text.
Targets ~3M tokens from ~200 articles covering all domains.

Modular: Run independently, produces raw JSONL.
"""
import json
import os
import time
import re
import html as html_lib
import urllib.parse
import urllib.request
from pathlib import Path

REST_API_BASE = "https://en.wikipedia.org/api/rest_v1/page/html"
USER_AGENT = "Silverwing-12M/1.0 (educational research; contact@example.com) Python/3.13"
OUTPUT_DIR = Path("silverwing/data_pipeline/raw/wikipedia")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 200+ high-quality Wikipedia articles across all domains
ARTICLES = [
    # === Science ===
    "Science", "Physics", "Biology", "Chemistry", "Astronomy",
    "Scientific_method", "Hypothesis", "Scientific_theory", "Scientific_law",
    "Peer_review", "Experimental_design", "Observation", "Measurement",
    "Scientific_model", "Replication_(science)",
    # === Mathematics ===
    "Mathematics", "Algebra", "Geometry", "Calculus", "Statistics",
    "Probability_theory", "Number_theory", "Linear_algebra",
    "Differential_equation", "Discrete_mathematics", "Set_theory",
    "Mathematical_logic", "Graph_theory", "Game_theory",
    "Trigonometry", "Topology", "Combinatorics", "Real_analysis",
    "Complex_analysis", "Differential_calculus", "Integral_calculus",
    # === Computer Science ===
    "Computer_science", "Algorithm", "Data_structure", "Programming_language",
    "Computer_architecture", "Operating_system", "Compiler", "Database",
    "Computer_network", "Artificial_intelligence", "Machine_learning",
    "Deep_learning", "Natural_language_processing", "Robotics",
    "Software_engineering", "Cloud_computing", "Information_theory",
    "Theory_of_computation", "Computational_complexity_theory",
    "Computer_graphics", "Human-computer_interaction", "Concurrency_(computer_science)",
    # === Engineering ===
    "Engineering", "Mechanical_engineering", "Electrical_engineering",
    "Chemical_engineering", "Materials_science", "Aerospace_engineering",
    "Biomedical_engineering", "Civil_engineering", "Industrial_engineering",
    "Control_engineering", "Systems_engineering", "Nuclear_engineering",
    # === Physics (detailed) ===
    "Classical_mechanics", "Thermodynamics", "Electromagnetism",
    "Optics", "Acoustics", "Atomic_physics", "Atomic_spectroscopy",
    "Quantum_mechanics", "Quantum_field_theory", "Relativity",
    "Special_relativity", "General_relativity", "Astrophysics",
    "Astrophysics_and_astronomy", "Plasma_(physics)", "Nuclear_physics",
    "Particle_physics", "Solid_state_physics", "Statistical_mechanics",
    # === Biology & Medicine ===
    "Evolution", "Genetics", "Ecology", "Cell_(biology)", "Molecular_biology",
    "Biochemistry", "Biotechnology", "Microbiology", "Botany", "Zoology",
    "Human_anatomy", "Physiology", "Pathology", "Pharmacology",
    "Epidemiology", "Immunology", "Neuroscience", "Oncology",
    "Cardiology", "Endocrinology", "Toxicology",
    # === Earth & Environment ===
    "Geology", "Meteorology", "Climatology", "Climate_change", "Pollution",
    "Biodiversity", "Ecology", "Conservation_biology", "Renewable_energy",
    "Solar_energy", "Wind_power", "Hydroelectric_power",
    "Plate_tectonics", "Volcano", "Earthquake", "Tsunami",
    # === Technology ===
    "Technology", "Internet", "Computer", "World_Wide_Web",
    "Semiconductor", "Transistor", "Integrated_circuit",
    "Display_device", "Touchscreen", "Voice_user_interface",
    "Bluetooth", "WiFi", "Cellular_network", "Satellite_communication",
    # === Economics & Social Sciences ===
    "Economics", "Microeconomics", "Macroeconomics", "International_economics",
    "Finance", "Banking", "Investment", "Capitalism",
    "Political_science", "Political_effects_theory", "Sociology",
    "Demography", "Anthropology", "Psychology", "Social_psychology",
    "Cognitive_science", "Cognitive_psychology",
    "Linguistics", "Historical_linguistics", "Sociolinguistics",
    "History", "World_history", "Geography",
    # === Philosophy ===
    "Philosophy", "Ethics", "Metaphysics", "Epistemology", "Logic",
    "Aesthetics", "Philosophy_of_mind", "Philosophy_of_science",
    "Political_philosophy", "Eastern_philosophy",
    # === Literature & Arts ===
    "Literature", "Poetry", "Novel", "Drama", "Film",
    "Theater", "Music", "Painting", "Sculpture", "Architecture",
    "Photography", "Dance",
    # === Space & Cosmos ===
    "Solar_System", "Mercury_(planet)", "Venus", "Earth", "Moon",
    "Mars", "Jupiter", "Saturn", "Uranus", "Neptune",
    "Galaxy", "Milky_Way", "Andromeda_galaxy", "Black_hole",
    "Neutron_star", "Supernova", "Nebula", "Exoplanet",
    "Universe", "Big_Bang", "Cosmology", "Dark_matter",
    # === Notable Concepts ===
    "Scientific_revolution", "Industrial_revolution", "Information_age",
    "Enlightenment", "Renaissance", "Age_of_Enlightenment",
    "Age_of_Discovery", "French_Revolution", "American_Revolution",
    # === Business & Society ===
    "Management", "Organization", "Leadership", "Project_management",
    "Entrepreneurship", "Marketing", "Sales",
    # === More Biology & Medicine ===
    "DNA", "RNA", "Protein", "Enzyme", "Cell_membrane",
    "Photosynthesis", "Cellular_respiration", "Glycolysis",
    "Citric_acid_cycle", "Oxidative_phosphorylation",
    "Immune_system", "Innate_immune_system", "Adaptive_immune_system",
    # === Health ===
    "Public_health", "Epidemic", "Pandemic", "Vaccination",
    # === Physics & Math ===
    "Force", "Energy", "Work_(physics)", "Power_(physics)",
    "Momentum", "Heat", "Temperature", "Entropy",
    "Wave", "Sound", "Light", "Electromagnetic_spectrum",
    "Friction", "Gravity", "Mass", "Velocity",
    # === Computing ===
    "Central_processing_unit", "Graphics_processing_unit",
    "Random-access_memory", "Hard_disk_drive", "Solid-state_drive",
    "Motherboard", "Power_supply_unit",
    "Computer_security", "Encryption", "Hash_function",
    "Neural_network", "Convolutional_neural_network",
    "Transformer_(machine_learning_model)",
    # === Engineering (more) ===
    "Nanotechnology",
    "Telecommunications", "Electrical_engineering", "Electronic_circuit",
    "Semiconductor_device", "Integrated_circuit", "Microprocessor",
    "Computer_network", "Internet_protocol_suite", "Encryption",
    "Software_engineering", "Software_testing", "Software_design",
    # === Mathematics (more) ===
    "Arithmetic", "Number", "Integer", "Rational_number", "Real_number",
    "Complex_number", "Function_(mathematics)", "Set_theory",
    "Category_theory", "Topology", "Geometry", "Algebraic_geometry",
    # === Economics & Finance ===
    "Economics", "Microeconomics", "Macroeconomics", "Game_theory",
    "Econometrics", "Finance", "Investment", "Stock_exchange",
    "Market_(economics)", "Supply_and_demand", "Inflation", "Recession",
    # === History & Geography ===
    "World_War_II", "World_War_I", "Cold_War", "French_Revolution",
    "American_Revolutionary_War", "Napoleonic_Wars", "Roman_Empire",
    "British_Empire", "History_of_the_world", "Ancient_history",
    "Medieval_history", "Modern_history",
    # === Medicine & Health ===
    "Medicine", "Public_health", "Epidemiology", "Vaccination",
    "Pharmacology", "Surgery", "Diagnostic_medical_imaging", "Nutrition",
    # === Psychology & Neuroscience ===
    "Psychology", "Cognitive_psychology", "Neuroscience", "Memory",
    "Consciousness", "Perception", "Learning",
    # === Additional Science ===
    "Earth_science", "Environmental_science", "Materials_science",
    "Nuclear_technology", "Radioactive_decay", "Nuclear_fission",
    "Solar_cell", "Wind_turbine", "Battery_(electricity)",
]


def fetch_article(title):
    """Fetch article HTML via REST API."""
    encoded_title = urllib.parse.quote(title)
    url = f"{REST_API_BASE}/{encoded_title}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  HTTP {e.code} for {title}: {e.reason}")
        return None
    except Exception as e:
        print(f"  Error for {title}: {e}")
        return None

def extract_text_from_html(html_bytes):
    """Extract readable plain text from Wikipedia HTML."""
    html_content = html_bytes.decode("utf-8", errors="replace")

    # Remove unwanted elements
    html_content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL)
    html_content = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL)
    html_content = re.sub(r"<table[^>]*>.*?</table>", "", html_content, flags=re.DOTALL)
    html_content = re.sub(r"<figure[^>]*>.*?</figure>", "", html_content, flags=re.DOTALL)
    html_content = re.sub(r"<sup[^>]*>.*?</sup>", "", html_content, flags=re.DOTALL)
    html_content = re.sub(r"<span[^>]*>", "", html_content)
    html_content = re.sub(r"<a[^>]*>|</a>", "", html_content)
    html_content = re.sub(r"<link[^>]*>", "", html_content)
    html_content = re.sub(r"<meta[^>]*>", "", html_content)

    # Replace closing block-level tags and <br> with paragraph breaks
    text = re.sub(r"</(?:p|div|h[1-6]|li|tr|td|th|ul|ol|blockquote|section|article|header|footer|aside|nav|pre|caption|tbody|tfoot|thead)[^>]*>",
                  "\n\n", html_content, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?[^>]*>", "\n", text, flags=re.IGNORECASE)

    # Remove all remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Clean HTML entities
    text = html_lib.unescape(text)

    # Remove reference markers [1], [2], etc.
    text = re.sub(r"\[\d+\]", "", text)

    # Normalize whitespace
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if len(line) > 3:  # Skip very short lines (navigation, etc.)
            cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def estimate_tokens(text):
    return len(text) // 2

def main():
    print("=== Wikipedia Data Acquisition (REST API) ===")
    print(f"Target: ~3M tokens from {len(ARTICLES)} articles")
    print()

    total_tokens = 0
    total_chars = 0
    total_articles = 0
    output_file = OUTPUT_DIR / "wikipedia_raw.jsonl"

    if output_file.exists():
        os.remove(output_file)

    with open(output_file, "w", encoding="utf-8") as f:
        existing_titles = set()
        for i, title in enumerate(ARTICLES):
            if title in existing_titles:
                continue  # Skip duplicates in the list
            html_bytes = fetch_article(title)
            if html_bytes:
                text = extract_text_from_html(html_bytes)
                if len(text) > 500:
                    n_tokens = estimate_tokens(text)
                    existing_titles.add(title)
                    record = {
                        "source": "wikipedia",
                        "title": title,
                        "chars": len(text),
                        "tokens": n_tokens,
                        "text": text,
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total_tokens += n_tokens
                    total_chars += len(text)
                    total_articles += 1
                    if (i + 1) % 10 == 0 or i == 0:
                        print(f"  [{i+1}/{len(ARTICLES)}] {title}: {n_tokens:,} tokens | total: {total_tokens:,}")
                else:
                    print(f"  [{i+1}/{len(ARTICLES)}] {title}: TOO SHORT ({len(text)} chars)")
            else:
                print(f"  [{i+1}/{len(ARTICLES)}] {title}: NOT FOUND")
            time.sleep(0.3)  # REST API rate limit

    print(f"\n=== Wikipedia Acquisition Complete ===")
    print(f"  Articles fetched: {total_articles}")
    print(f"  Total chars: {total_chars:,}")
    print(f"  Estimated tokens: {total_tokens:,}")
    print(f"  File size: {os.path.getsize(output_file):,} bytes")

    result = {"articles": total_articles, "tokens": total_tokens, "chars": total_chars}
    with open(OUTPUT_DIR / "acquisition_summary.json", "w") as f:
        json.dump(result, f, indent=2)
    return result

if __name__ == "__main__":
    main()
