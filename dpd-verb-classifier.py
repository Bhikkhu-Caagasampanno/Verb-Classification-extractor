#!/usr/bin/env python3
"""
Extract Pāli verbs from DPD SQLite and assign rough conjugation classes.

Usage:
    python dpd-verb-classifier.py /path/to/dpd.db

Outputs:
    dpd_verb_classes.json
    dpd_verb_classes.csv
"""

import sqlite3
import json
import csv
import re
import sys
import time
from pathlib import Path


DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dpd.db")

TABLE_CANDIDATES = [
    "dpd_headwords",
    "headwords",
    "words",
    "dictionary",
]

FIELD_CANDIDATES = {
    "lemma": ["lemma_1", "lemma", "headword", "pali_1", "word"],
    "pos": ["pos", "grammar", "word_class"],
    "root": ["root_key", "root", "dhatu", "dhātu"],
    "meaning": ["meaning_1", "meaning", "definition", "english"],
}


def normalize(text):
    if text is None:
        return ""
    return str(text).strip().lower()


def get_tables(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in cur.fetchall()]


def get_columns(conn, table):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def pick_table(conn):
    tables = get_tables(conn)

    print("Available tables:")
    for table in tables:
        print(f"    {table}")
    print()

    for candidate in TABLE_CANDIDATES:
        if candidate in tables:
            print(f"Selected table from known candidates: {candidate}")
            return candidate

    print("Could not find expected table.")
    raise SystemExit(1)


def pick_field(columns, choices, required=True):
    for c in choices:
        if c in columns:
            return c

    if required:
        raise ValueError(f"Could not find any of these fields: {choices}")

    return None


def is_verb(pos_text, lemma):
    pos = normalize(pos_text)
    lemma = normalize(lemma)

    verb_markers = [
        "verb",
        "pr",
        "aor",
        "caus",
        "denom",
        "pass",
        "root",
        "dhātu",
        "dhatu",
    ]

    if any(marker in pos for marker in verb_markers):
        return True

    # Common finite/infinitive/participial endings.
    # This is intentionally loose and should be reviewed.
    possible_verb_endings = [
        "ti",
        "nti",
        "ati",
        "eti",
        "oti",
        "āti",
        "enti",
        "anti",
        "tuṃ",
        "itvā",
        "tvā",
        "māna",
        "āna",
        "ta",
        "ita",
    ]

    return any(lemma.endswith(e) for e in possible_verb_endings)


def detect_voice_or_type(pos_text, lemma):
    text = normalize(pos_text) + " " + normalize(lemma)

    if "caus" in text:
        return "causative"
    if "pass" in text:
        return "passive"
    if "denom" in text:
        return "denominative"
    if "desid" in text:
        return "desiderative"

    return "active_or_unknown"


def detect_present_stem_class(lemma):
    """
    Rough practical classification based on common present stems.

    Examples:
        bhavati  -> a_present
        karoti   -> o_present / karoti_type
        deti     -> e_present
        gacchati -> a_present, irregular root/stem
    """
    lemma = normalize(lemma)

    irregulars = {
        "hoti": "irregular_hoti",
        "atthi": "irregular_atthi",
        "karoti": "irregular_karoti",
        "deti": "irregular_deti",
        "dadāti": "irregular_dadāti",
        "gacchati": "irregular_gacchati",
        "tiṭṭhati": "irregular_tiṭṭhati",
        "jānāti": "irregular_jānāti",
        "suṇāti": "irregular_suṇāti",
        "brūti": "irregular_brūti",
    }

    if lemma in irregulars:
        return irregulars[lemma]

    if lemma.endswith("āpeti"):
        return "causative_āpe_present"
    if lemma.endswith("eti"):
        return "e_present"
    if lemma.endswith("oti"):
        return "o_present"
    if lemma.endswith("āti"):
        return "ā_present"
    if lemma.endswith("ati"):
        return "a_present"
    if lemma.endswith("nti"):
        return "plural_finite_form_needs_review"
    if lemma.endswith("ti"):
        return "ti_form_needs_review"

    if lemma.endswith("tuṃ"):
        return "infinitive_needs_root"
    if lemma.endswith("itvā") or lemma.endswith("tvā"):
        return "absolutive_needs_root"
    if lemma.endswith("māna") or lemma.endswith("āna"):
        return "present_participle_needs_review"
    if lemma.endswith("ta") or lemma.endswith("ita"):
        return "past_participle_needs_review"

    return "unknown_verb_class"


def guess_present_stem(lemma, verb_class):
    lemma = normalize(lemma)

    if verb_class.startswith("irregular_"):
        return lemma

    endings = ["ti", "nti", "tuṃ", "itvā", "tvā"]

    for ending in endings:
        if lemma.endswith(ending):
            return lemma[:-len(ending)]

    return lemma


def assign_conjugation_class(lemma, pos_text):
    voice_type = detect_voice_or_type(pos_text, lemma)
    present_class = detect_present_stem_class(lemma)

    if voice_type == "causative":
        if lemma.endswith("āpeti"):
            return "causative_āpe_present", voice_type
        if lemma.endswith("eti"):
            return "causative_e_present", voice_type
        return "causative_needs_review", voice_type

    if voice_type == "passive":
        return "passive_ya_present", voice_type

    if voice_type == "denominative":
        return "denominative_present", voice_type

    return present_class, voice_type


def main():
    overall_start = time.time()

    print("=" * 70)
    print("DPD VERB EXTRACTOR")
    print("=" * 70)
    print()

    print("Opening database:")
    print(f"    {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("Connection successful.")
    print()

    table = pick_table(conn)

    print("Using table:")
    print(f"    {table}")
    print()

    columns = get_columns(conn, table)

    print("Available columns:")
    for column in columns:
        print(f"    {column}")
    print()

    lemma_field = pick_field(columns, FIELD_CANDIDATES["lemma"])
    pos_field = pick_field(columns, FIELD_CANDIDATES["pos"], required=False)
    root_field = pick_field(columns, FIELD_CANDIDATES["root"], required=False)
    meaning_field = pick_field(columns, FIELD_CANDIDATES["meaning"], required=False)

    print("Detected fields:")
    print(f"    Lemma field  : {lemma_field}")
    print(f"    POS field    : {pos_field}")
    print(f"    Root field   : {root_field}")
    print(f"    Meaning field: {meaning_field}")
    print()

    print("Loading database rows...")

    load_start = time.time()
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    load_time = time.time() - load_start

    print(f"Loaded {len(rows):,} rows.")
    print(f"Took {load_time:.2f} seconds.")
    print()

    output = []

    verb_count = 0
    skip_count = 0
    blank_lemma_count = 0
    unknown_class_count = 0

    class_counts = {}
    voice_counts = {}

    print("Beginning extraction...")
    print("First ten extracted entries will be shown below.")
    print()

    extract_start = time.time()

    for index, row in enumerate(rows, start=1):
        if index % 1000 == 0:
            percent = index / len(rows) * 100 if rows else 100
            print(
                f"[{index:,}/{len(rows):,}] "
                f"{percent:5.1f}% complete   "
                f"Verbs found: {verb_count:,}   "
                f"Skipped: {skip_count:,}",
                end="\r",
                flush=True,
            )

        lemma = normalize(row[lemma_field])

        if not lemma:
            blank_lemma_count += 1
            skip_count += 1
            continue

        pos_text = row[pos_field] if pos_field else ""

        if not is_verb(pos_text, lemma):
            skip_count += 1
            continue

        root = normalize(row[root_field]) if root_field else ""
        meaning = normalize(row[meaning_field]) if meaning_field else ""

        conjugation_class, voice_type = assign_conjugation_class(lemma, pos_text)
        present_stem = guess_present_stem(lemma, conjugation_class)

        if conjugation_class == "unknown_verb_class" or "needs_review" in conjugation_class:
            unknown_class_count += 1

        entry = {
            "lemma": lemma,
            "pos": "verb",
            "root": root,
            "present_stem": present_stem,
            "voice_type": voice_type,
            "conjugation_class": conjugation_class,
            "meaning": meaning,
        }

        output.append(entry)

        verb_count += 1

        class_counts.setdefault(conjugation_class, 0)
        class_counts[conjugation_class] += 1

        voice_counts.setdefault(voice_type, 0)
        voice_counts[voice_type] += 1

        if verb_count <= 10:
            print(
                f"Example {verb_count}: "
                f"{lemma:25} "
                f"root={root or 'unknown':15} "
                f"stem={present_stem:20} "
                f"type={voice_type:20} "
                f"class={conjugation_class}"
            )

    extract_time = time.time() - extract_start

    print()
    print()
    print("Extraction complete.")
    print(f"Extraction took {extract_time:.2f} seconds.")
    print(f"{verb_count:,} verb entries found.")
    print()

    print("Sorting output...")
    output = sorted(output, key=lambda x: x["lemma"])

    json_path = "dpd_verb_classes.json"
    csv_path = "dpd_verb_classes.csv"

    print(f"Writing JSON: {json_path}")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Writing CSV: {csv_path}")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "lemma",
                "pos",
                "root",
                "present_stem",
                "voice_type",
                "conjugation_class",
                "meaning",
            ],
        )
        writer.writeheader()
        writer.writerows(output)

    elapsed = time.time() - overall_start

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Rows processed          : {len(rows):,}")
    print(f"Verbs extracted         : {verb_count:,}")
    print(f"Skipped                 : {skip_count:,}")
    print(f"Blank lemmas            : {blank_lemma_count:,}")
    print(f"Unknown/review classes  : {unknown_class_count:,}")
    print(f"Total time              : {elapsed:.2f} seconds")
    print()

    print("Conjugation classes:")
    print("-" * 70)

    for cls in sorted(class_counts):
        print(f"{cls:40} {class_counts[cls]:8,}")

    print()
    print("Voice/type counts:")
    print("-" * 70)

    for voice in sorted(voice_counts):
        print(f"{voice:40} {voice_counts[voice]:8,}")

    print()
    print("Files written:")
    print(f"    JSON -> {json_path}")
    print(f"    CSV  -> {csv_path}")
    print()
    print("Done.")


if __name__ == "__main__":
    main()