"""
One-shot generator for canonical-stringify golden cases.

Run once to (re)produce tests/fixtures/canonical-cases.json. Tests load
that JSON and assert canonicalStringify produces matching bytes for each
input. The generator is committed for reproducibility; tests do NOT spawn
Python.

Usage:
    cd supabase-dataset-updater
    python tests/fixtures/_canonical_cases_generator.py

This must be re-run if you ever extend the cases list. Commit the JSON.
"""

import json
from pathlib import Path

# Each case: {"name": str, "input": Any, "expected": str (the canonical text)}
# Canonical form mirrors export_to_json.py:_canonical_rows_sha256 exactly.
CASES = [
    {"name": "rows-row", "input": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]},
    {"name": "deeply-nested", "input": {"a": {"b": {"c": {"d": [1, 2, 3]}}}}},
    {"name": "integer-keys", "input": {"10": "x", "1": "y", "2": "z"}},
    {"name": "unicode-mixed", "input": {"name": "三国杀", "id": 1}},
    {"name": "emoji", "input": {"flag": "🇩🇪", "smile": "😀"}},
    {"name": "rtl", "input": {"text": "مرحبا"}},
    {"name": "large-integer", "input": {"games": 1234567890}},
    {"name": "negative", "input": {"delta": -5.4}},
    {"name": "boolean-mixed", "input": [True, False, None, 0, ""]},
    {"name": "control-chars", "input": "tab\there\nnewline"},
    {"name": "backslash", "input": {"path": "C:\\Users\\till"}},
    {"name": "quote-inside", "input": 'he said "hi"'},
    {"name": "matchups-row-shape", "input": {
        "patch": "16.8",
        "champion_key": "61",
        "role": "support",
        "opponent_key": "157",
        "opponent_role": "middle",
        "games": 245,
        "wins": 130,
    }},
]

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))

out = [
    {"name": c["name"], "input": c["input"], "expected": canonical(c["input"])}
    for c in CASES
]

target = Path(__file__).parent / "canonical-cases.json"
target.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"wrote {len(out)} cases -> {target}")
