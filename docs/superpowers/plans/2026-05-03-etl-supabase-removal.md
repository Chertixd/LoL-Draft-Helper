# ETL Supabase Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Lolalytics → Supabase → Python exporter pipeline with a TypeScript-only direct write to GitHub Pages, producing byte-identical JSON outputs to the existing pipeline.

**Architecture:** New TS modules (`canonical-stringify`, `envelope`, `cdn-fetcher`, `writer`, `self-check`, `smoke-test`, `etl`) replace `supabase-etl.ts` + `scripts/export_to_json.py`. All Python is removed. The existing `lolalytics/` and `riot.ts` modules are preserved unchanged. A 4-layer safety stack (CI golden test, workflow self-check, post-deploy smoke test, atomic PR) protects against canonical-stringify drift breaking installed clients.

**Tech Stack:** TypeScript 5.9, Node.js LTS, vitest 2.1, safe-stable-stringify 2.5, memfs 4.15. GitHub Actions cron + peaceiris/actions-gh-pages@v4 (unchanged). No Python, no Supabase.

**Reference spec:** `docs/superpowers/specs/2026-05-03-etl-supabase-removal-design.md` (commit `b48450e`).

**Critical invariant:** `canonicalStringify(rows)` must be byte-identical to Python's `json.dumps(rows, sort_keys=True, separators=(",",":"), default=...).encode("utf-8")`. The reference implementation is in `supabase-dataset-updater/scripts/export_to_json.py:_canonical_rows_sha256` (deleted in Task 24, but remains in git history). Drift = every installed Tauri client breaks.

---

## Phase A — Setup & Tooling

### Task 1: Update package.json dependencies and scripts

**Files:**
- Modify: `supabase-dataset-updater/package.json`

- [ ] **Step 1: Replace package.json contents**

```json
{
    "name": "supabase-dataset-updater",
    "version": "2.0.0",
    "description": "Daily ETL: Lolalytics + Riot Data Dragon -> JSON files for the Counterpick CDN",
    "scripts": {
        "update": "tsx src/etl.ts",
        "self-check": "tsx src/self-check.ts public/data",
        "smoke-test": "tsx src/smoke-test.ts public/data",
        "test": "vitest run --exclude tests/golden.test.ts",
        "test:golden": "vitest run tests/golden.test.ts",
        "test:capture": "tsx scripts/capture-golden.ts",
        "typecheck": "tsc --noEmit"
    },
    "dependencies": {
        "safe-stable-stringify": "^2.5.0",
        "tsx": "^4.21.0"
    },
    "devDependencies": {
        "@types/node": "^22.19.3",
        "memfs": "^4.15.0",
        "typescript": "^5.9.3",
        "vitest": "^2.1.0"
    },
    "packageManager": "pnpm@9.2.0"
}
```

- [ ] **Step 2: Install dependencies**

Run from `supabase-dataset-updater/`:
```bash
pnpm install
```

Expected: `pnpm-lock.yaml` regenerates. `node_modules/safe-stable-stringify`, `node_modules/vitest`, `node_modules/memfs` exist. `node_modules/@supabase` is gone.

- [ ] **Step 3: Verify dependency removal**

Run:
```bash
grep -r "@supabase" src/ | head
```
Expected: only `src/supabase-etl.ts` (gets deleted in Task 25). No other matches.

- [ ] **Step 4: Commit**

```bash
git add supabase-dataset-updater/package.json supabase-dataset-updater/pnpm-lock.yaml
git commit -m "chore(etl): swap supabase deps for vitest + safe-stable-stringify"
```

### Task 2: Add vitest config and test directory structure

**Files:**
- Create: `supabase-dataset-updater/vitest.config.ts`
- Create: `supabase-dataset-updater/tests/.gitkeep`
- Create: `supabase-dataset-updater/tests/fixtures/.gitkeep`
- Modify: `supabase-dataset-updater/.gitignore` (or create if absent)

- [ ] **Step 1: Write vitest config**

Create `supabase-dataset-updater/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        // Tests live in ./tests/, source in ./src/
        include: ["tests/**/*.test.ts"],
        // Long timeout for golden test which reads ~850 fixtures from disk
        testTimeout: 30_000,
        // Suppress noisy console.log from production code paths during tests
        silent: false,
        reporters: ["default"],
    },
});
```

- [ ] **Step 2: Create directory placeholders**

```bash
mkdir -p supabase-dataset-updater/tests/fixtures
touch supabase-dataset-updater/tests/.gitkeep
touch supabase-dataset-updater/tests/fixtures/.gitkeep
```

- [ ] **Step 3: Update .gitignore for test artefacts**

Append to `supabase-dataset-updater/.gitignore` (create file if it doesn't exist):
```
# Test outputs
public/data/
tmp/

# Vitest cache
.vitest/
```

- [ ] **Step 4: Verify test runner boots**

Run from `supabase-dataset-updater/`:
```bash
pnpm test
```
Expected: vitest exits 0 with "No test files found" (no tests yet, that's fine).

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/vitest.config.ts supabase-dataset-updater/tests/ supabase-dataset-updater/.gitignore
git commit -m "chore(etl): add vitest config and tests/ scaffold"
```

---

## Phase B — Pure Function Modules (TDD)

### Task 3: canonical-stringify — empty values and primitives

**Files:**
- Create: `supabase-dataset-updater/src/canonical-stringify.ts`
- Create: `supabase-dataset-updater/tests/canonical-stringify.test.ts`

This module must produce byte-identical output to Python's:
```python
json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

- [ ] **Step 1: Write failing test**

Create `supabase-dataset-updater/tests/canonical-stringify.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { canonicalStringify } from "../src/canonical-stringify";

const enc = (s: string) => new TextEncoder().encode(s);
const eq = (actual: Uint8Array, expected: string) =>
    expect(Buffer.from(actual).toString("utf-8")).toBe(expected);

describe("canonicalStringify — primitives", () => {
    it("serializes null", () => eq(canonicalStringify(null), "null"));
    it("serializes true", () => eq(canonicalStringify(true), "true"));
    it("serializes false", () => eq(canonicalStringify(false), "false"));
    it("serializes integer", () => eq(canonicalStringify(42), "42"));
    it("serializes negative integer", () => eq(canonicalStringify(-17), "-17"));
    it("serializes string", () => eq(canonicalStringify("hello"), '"hello"'));
    it("serializes empty string", () => eq(canonicalStringify(""), '""'));
    it("serializes empty array", () => eq(canonicalStringify([]), "[]"));
    it("serializes empty object", () => eq(canonicalStringify({}), "{}"));
});
```

- [ ] **Step 2: Run test, verify it fails**

```bash
pnpm test canonical-stringify
```
Expected: FAIL — "Cannot find module '../src/canonical-stringify'".

- [ ] **Step 3: Write minimal implementation**

Create `supabase-dataset-updater/src/canonical-stringify.ts`:
```typescript
import stringify from "safe-stable-stringify";

/**
 * Serialize a value to canonical JSON bytes — byte-identical to Python's
 * json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8").
 *
 * This is the SINGLE invariant that protects every installed Tauri client.
 * Drift here means sha256 mismatch in the __meta envelope, which causes
 * json_repo.py to refuse to load CDN data. See the design spec
 * (docs/superpowers/specs/2026-05-03-etl-supabase-removal-design.md) for
 * the full failure-mode analysis.
 */
export function canonicalStringify(value: unknown): Uint8Array {
    // safe-stable-stringify default: sorted keys, no whitespace, undefined keys dropped.
    // Matches Python's sort_keys=True, separators=(",",":") behaviour for
    // primitives and containers. See tests for edge cases (floats, unicode,
    // integer-keyed objects).
    const text = stringify(value, undefined, undefined);
    if (text === undefined) {
        // Python json.dumps raises on unserializable types; we mirror that.
        throw new TypeError(
            `canonicalStringify: value is not JSON-serializable: ${String(value)}`
        );
    }
    return new TextEncoder().encode(text);
}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pnpm test canonical-stringify
```
Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/canonical-stringify.ts supabase-dataset-updater/tests/canonical-stringify.test.ts
git commit -m "feat(etl): canonical-stringify — primitives and empty containers"
```

### Task 4: canonical-stringify — sorted keys and nested structures

**Files:**
- Modify: `supabase-dataset-updater/tests/canonical-stringify.test.ts`

- [ ] **Step 1: Append failing tests**

Add to the existing `tests/canonical-stringify.test.ts`:
```typescript
describe("canonicalStringify — sorting & nesting", () => {
    it("sorts object keys lexicographically (string sort, NOT numeric)", () => {
        // Python's sort_keys=True does string-sort: "1" < "10" < "2"
        eq(
            canonicalStringify({ "10": "b", "1": "a", "2": "c" }),
            '{"1":"a","10":"b","2":"c"}'
        );
    });

    it("sorts mixed-content keys", () =>
        eq(
            canonicalStringify({ z: 1, a: 2, m: 3 }),
            '{"a":2,"m":3,"z":1}'
        ));

    it("uses no whitespace between key/value or between elements", () =>
        eq(
            canonicalStringify({ b: 1, a: [1, 2, 3] }),
            '{"a":[1,2,3],"b":1}'
        ));

    it("recursively sorts nested objects", () =>
        eq(
            canonicalStringify({ outer: { z: 1, a: 2 }, prefix: 0 }),
            '{"outer":{"a":2,"z":1},"prefix":0}'
        ));

    it("preserves array order (arrays are not sorted)", () =>
        eq(canonicalStringify([3, 1, 2]), "[3,1,2]"));

    it("handles array of objects", () =>
        eq(
            canonicalStringify([
                { b: 1, a: 2 },
                { d: 3, c: 4 },
            ]),
            '[{"a":2,"b":1},{"c":4,"d":3}]'
        ));
});
```

- [ ] **Step 2: Run tests, verify they pass**

```bash
pnpm test canonical-stringify
```
Expected: 15 tests pass (9 from Task 3 + 6 new). `safe-stable-stringify` already does lexicographic key sort, no impl change needed.

- [ ] **Step 3: Commit**

```bash
git add supabase-dataset-updater/tests/canonical-stringify.test.ts
git commit -m "test(etl): canonical-stringify — sorted keys and nesting"
```

### Task 5: canonical-stringify — Python-compatible numeric edge cases

**Files:**
- Modify: `supabase-dataset-updater/tests/canonical-stringify.test.ts`
- Modify: `supabase-dataset-updater/src/canonical-stringify.ts`

This task addresses the **highest-risk** part of the migration. Python and JS handle numbers differently. Test the edge cases that actually appear in our data.

- [ ] **Step 1: Append failing tests**

Add to `tests/canonical-stringify.test.ts`:
```typescript
describe("canonicalStringify — numeric edge cases", () => {
    it("emits integer for whole-number float", () => {
        // Python json.dumps(1.0) = "1.0"; JSON.stringify(1.0) = "1"
        // safe-stable-stringify follows JS — value is just the number 1.
        // Our row data only ever has integers (Math.round in lolalytics/index.ts),
        // so we never hit float-1.0 in production. Document the known difference.
        eq(canonicalStringify(1), "1");
    });

    it("preserves IEEE-754 float representation", () =>
        // 0.1 + 0.2 produces the same float-bits in both Python and JS;
        // so the canonical text is identical: "0.30000000000000004".
        eq(canonicalStringify(0.1 + 0.2), "0.30000000000000004"));

    it("handles negative zero as zero", () => eq(canonicalStringify(-0), "0"));

    it("rejects NaN", () =>
        expect(() => canonicalStringify(NaN)).toThrow(/not JSON-serializable/i));

    it("rejects Infinity", () =>
        expect(() => canonicalStringify(Infinity)).toThrow(/not JSON-serializable/i));

    it("rejects -Infinity", () =>
        expect(() => canonicalStringify(-Infinity)).toThrow(/not JSON-serializable/i));
});
```

- [ ] **Step 2: Run tests, verify NaN/Infinity ones fail**

```bash
pnpm test canonical-stringify
```
Expected: NaN/Infinity tests FAIL. `safe-stable-stringify` emits `null` for these by default; we need stricter behaviour to match Python's `json.dumps` which raises.

- [ ] **Step 3: Update implementation to reject non-finite numbers**

Replace `supabase-dataset-updater/src/canonical-stringify.ts` with:
```typescript
import stringify from "safe-stable-stringify";

/**
 * Serialize a value to canonical JSON bytes — byte-identical to Python's
 * json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8").
 *
 * Critical invariant: drift here means sha256 mismatch in the __meta envelope,
 * which breaks every installed Tauri client. See the design spec for the full
 * failure-mode analysis.
 *
 * Behavioural notes vs Python:
 *  - Whole-number floats (1.0) become "1" in JS and "1.0" in Python. Our
 *    upstream data uses Math.round in lolalytics/index.ts so floats never
 *    survive the pipeline; nothing to handle.
 *  - NaN, Infinity, -Infinity throw here (Python raises in json.dumps too,
 *    unless allow_nan=True which we do not use).
 */
export function canonicalStringify(value: unknown): Uint8Array {
    rejectNonFinite(value);
    const text = stringify(value, undefined, undefined);
    if (text === undefined) {
        throw new TypeError(
            `canonicalStringify: value is not JSON-serializable: ${String(value)}`
        );
    }
    return new TextEncoder().encode(text);
}

/**
 * Walk the value graph and throw if any number is non-finite.
 * Cheaper than post-processing the JSON text and impossible to fool.
 */
function rejectNonFinite(value: unknown): void {
    if (typeof value === "number") {
        if (!Number.isFinite(value)) {
            throw new TypeError(
                `canonicalStringify: value is not JSON-serializable: ${value}`
            );
        }
        return;
    }
    if (value === null || typeof value !== "object") return;
    if (Array.isArray(value)) {
        for (const item of value) rejectNonFinite(item);
        return;
    }
    for (const v of Object.values(value as Record<string, unknown>)) {
        rejectNonFinite(v);
    }
}
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
pnpm test canonical-stringify
```
Expected: 21 tests pass.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/canonical-stringify.ts supabase-dataset-updater/tests/canonical-stringify.test.ts
git commit -m "feat(etl): canonical-stringify — reject NaN/Infinity to match Python json.dumps"
```

### Task 6: canonical-stringify — Unicode round-trip

**Files:**
- Modify: `supabase-dataset-updater/tests/canonical-stringify.test.ts`

Lolalytics responses can contain unicode (champion names in zh_CN, special characters). Verify our output handles them as Python would.

- [ ] **Step 1: Append failing tests**

Add to `tests/canonical-stringify.test.ts`:
```typescript
describe("canonicalStringify — unicode", () => {
    it("emits multi-byte UTF-8 directly (no \\uXXXX escapes)", () => {
        // Python's default json.dumps with ensure_ascii=False emits raw UTF-8;
        // export_to_json.py does NOT pass ensure_ascii=False, but it does NOT
        // pass ensure_ascii=True either. Default is True, meaning it WOULD
        // escape. CRITICAL: confirm what export_to_json.py actually does.
        //
        // From export_to_json.py line 112-117 — no ensure_ascii kwarg, so
        // the Python default (ensure_ascii=True) applies: non-ASCII becomes
        // \uXXXX escapes. We must match that.
        //
        // safe-stable-stringify default uses JSON.stringify which does NOT
        // escape non-ASCII characters. We need to post-process or override.
        //
        // Test the expectation: Python emits "\\u4e09" for "三", not "三".
        eq(canonicalStringify({ name: "三" }), '{"name":"\\u4e09"}');
    });

    it("escapes emoji (multi-codepoint surrogate pairs)", () => {
        // "😀" is U+1F600, surrogate pair "😀" in UTF-16.
        // Python emits both halves as \uXXXX.
        eq(canonicalStringify("😀"), '"\\ud83d\\ude00"');
    });

    it("preserves ASCII control characters as escaped", () => {
        // \n is "\n" (escape sequence), tab is "\t", etc.
        eq(canonicalStringify("\n\t"), '"\\n\\t"');
    });

    it("escapes embedded quotes", () =>
        eq(canonicalStringify('a"b'), '"a\\"b"'));

    it("escapes backslashes", () =>
        eq(canonicalStringify("a\\b"), '"a\\\\b"'));
});
```

- [ ] **Step 2: Run tests, verify unicode tests fail**

```bash
pnpm test canonical-stringify
```
Expected: unicode tests FAIL. `safe-stable-stringify` emits raw UTF-8; Python's default escapes to `\uXXXX`.

- [ ] **Step 3: Update implementation to escape non-ASCII**

Replace `supabase-dataset-updater/src/canonical-stringify.ts` with:
```typescript
import stringify from "safe-stable-stringify";

/**
 * Serialize a value to canonical JSON bytes — byte-identical to Python's
 * json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
 * with default ensure_ascii=True.
 *
 * Critical invariant: drift here means sha256 mismatch in the __meta envelope,
 * which breaks every installed Tauri client. See the design spec for the full
 * failure-mode analysis.
 *
 * Behavioural notes vs Python:
 *  - Whole-number floats (1.0) become "1" in JS and "1.0" in Python. Our
 *    upstream data uses Math.round in lolalytics/index.ts so floats never
 *    survive the pipeline; nothing to handle.
 *  - NaN, Infinity, -Infinity throw here (Python raises in json.dumps too).
 *  - Non-ASCII characters are escaped as \uXXXX (Python default
 *    ensure_ascii=True). Surrogate pairs emit both halves.
 */
export function canonicalStringify(value: unknown): Uint8Array {
    rejectNonFinite(value);
    const text = stringify(value, undefined, undefined);
    if (text === undefined) {
        throw new TypeError(
            `canonicalStringify: value is not JSON-serializable: ${String(value)}`
        );
    }
    return new TextEncoder().encode(escapeNonAscii(text));
}

function rejectNonFinite(value: unknown): void {
    if (typeof value === "number") {
        if (!Number.isFinite(value)) {
            throw new TypeError(
                `canonicalStringify: value is not JSON-serializable: ${value}`
            );
        }
        return;
    }
    if (value === null || typeof value !== "object") return;
    if (Array.isArray(value)) {
        for (const item of value) rejectNonFinite(item);
        return;
    }
    for (const v of Object.values(value as Record<string, unknown>)) {
        rejectNonFinite(v);
    }
}

/**
 * Escape every character with code point >= 0x80 to \uXXXX form.
 * Matches Python's json.dumps default ensure_ascii=True behaviour.
 *
 * For surrogate pairs (code points >= 0x10000), JavaScript stores both halves
 * in the string already (UTF-16 representation), and we emit both as \uXXXX.
 * Python does the same — it iterates UTF-16 code units, not code points.
 */
function escapeNonAscii(text: string): string {
    let out = "";
    for (let i = 0; i < text.length; i++) {
        const cu = text.charCodeAt(i);
        if (cu < 0x80) {
            out += text[i];
        } else {
            out += "\\u" + cu.toString(16).padStart(4, "0");
        }
    }
    return out;
}
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
pnpm test canonical-stringify
```
Expected: 26 tests pass.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/canonical-stringify.ts supabase-dataset-updater/tests/canonical-stringify.test.ts
git commit -m "feat(etl): canonical-stringify — escape non-ASCII to match Python ensure_ascii"
```

### Task 7: canonical-stringify — Python-generated golden cases

**Files:**
- Create: `supabase-dataset-updater/tests/fixtures/_canonical_cases_generator.py`
- Create: `supabase-dataset-updater/tests/fixtures/canonical-cases.json`
- Modify: `supabase-dataset-updater/tests/canonical-stringify.test.ts`

This task generates a frozen reference using actual Python and asserts our TS implementation matches it byte-for-byte across many cases. The Python script is committed as documentation but is **not** invoked during tests — its output `canonical-cases.json` is the test input.

- [ ] **Step 1: Write the Python generator**

Create `supabase-dataset-updater/tests/fixtures/_canonical_cases_generator.py`:
```python
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
```

- [ ] **Step 2: Run the generator (one-shot)**

```bash
cd supabase-dataset-updater
python tests/fixtures/_canonical_cases_generator.py
```
Expected: prints `wrote 13 cases -> tests/fixtures/canonical-cases.json`. The JSON file is created.

If Python is not available on the executor's machine, the generator can be run anywhere with Python ≥ 3.6 and the result file committed manually.

- [ ] **Step 3: Append golden test to canonical-stringify.test.ts**

Add to `tests/canonical-stringify.test.ts`:
```typescript
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("canonicalStringify — Python golden cases", () => {
    const casesPath = resolve(__dirname, "fixtures/canonical-cases.json");
    const cases = JSON.parse(readFileSync(casesPath, "utf-8")) as Array<{
        name: string;
        input: unknown;
        expected: string;
    }>;

    for (const c of cases) {
        it(`matches Python output for: ${c.name}`, () => {
            const actual = Buffer.from(canonicalStringify(c.input)).toString("utf-8");
            // ensure_ascii=True is implicit — non-ASCII inputs in fixtures
            // come back from Python as \uXXXX escapes already.
            expect(actual).toBe(c.expected);
        });
    }
});
```

- [ ] **Step 4: Run tests, verify all pass**

```bash
pnpm test canonical-stringify
```
Expected: 26 + 13 = 39 tests pass. If any fail, the failure message shows the input name and exact byte difference — investigate before continuing.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/tests/fixtures/_canonical_cases_generator.py
git add supabase-dataset-updater/tests/fixtures/canonical-cases.json
git add supabase-dataset-updater/tests/canonical-stringify.test.ts
git commit -m "test(etl): canonical-stringify — Python golden cases (13 cases)"
```

### Task 8: envelope — wrap and serialize

**Files:**
- Create: `supabase-dataset-updater/src/envelope.ts`
- Create: `supabase-dataset-updater/tests/envelope.test.ts`

The envelope wraps row data with `__meta` (sha256, exported_at, row_count, schema_version, source_table, optional source_patch). It is the on-disk file shape.

- [ ] **Step 1: Write failing tests**

Create `supabase-dataset-updater/tests/envelope.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { wrapWithEnvelope, serializeEnvelope, SCHEMA_VERSION } from "../src/envelope";

const FROZEN_DATE = new Date("2026-05-03T12:00:00.000Z");

describe("wrapWithEnvelope", () => {
    it("includes all required __meta fields", () => {
        const env = wrapWithEnvelope("matchups", [{ a: 1 }], FROZEN_DATE);
        expect(env.__meta.source_table).toBe("matchups");
        expect(env.__meta.row_count).toBe(1);
        expect(env.__meta.schema_version).toBe(SCHEMA_VERSION);
        expect(env.__meta.exported_at).toBe("2026-05-03T12:00:00.000Z".replace(".000Z", "Z").replace("T12:00:00Z", "T12:00:00+00:00Z"));
        // Actually mirror Python: '...Z' replaces '+00:00' suffix.
        // We expect exported_at to end with "Z".
        expect(env.__meta.exported_at.endsWith("Z")).toBe(true);
        expect(env.__meta.sha256).toMatch(/^[0-9a-f]{64}$/);
        expect(env.rows).toEqual([{ a: 1 }]);
    });

    it("preserves source_patch when provided", () => {
        const env = wrapWithEnvelope("matchups", [], FROZEN_DATE, "16.8");
        expect(env.__meta.source_patch).toBe("16.8");
    });

    it("omits source_patch when absent", () => {
        const env = wrapWithEnvelope("champions", [], FROZEN_DATE);
        expect("source_patch" in env.__meta).toBe(false);
    });

    it("computes sha256 over canonical rows only (not __meta)", () => {
        // Two envelopes with same rows and different exported_at must have same sha256.
        const a = wrapWithEnvelope("matchups", [{ x: 1 }], new Date("2020-01-01Z"));
        const b = wrapWithEnvelope("matchups", [{ x: 1 }], new Date("2030-01-01Z"));
        expect(a.__meta.sha256).toBe(b.__meta.sha256);
        expect(a.__meta.exported_at).not.toBe(b.__meta.exported_at);
    });

    it("sha256 differs when rows differ", () => {
        const a = wrapWithEnvelope("x", [{ a: 1 }], FROZEN_DATE);
        const b = wrapWithEnvelope("x", [{ a: 2 }], FROZEN_DATE);
        expect(a.__meta.sha256).not.toBe(b.__meta.sha256);
    });
});

describe("serializeEnvelope", () => {
    it("produces JSON bytes with __meta and rows", () => {
        const env = wrapWithEnvelope("x", [{ a: 1 }], FROZEN_DATE);
        const bytes = serializeEnvelope(env);
        const parsed = JSON.parse(Buffer.from(bytes).toString("utf-8"));
        expect(parsed.__meta.source_table).toBe("x");
        expect(parsed.rows).toEqual([{ a: 1 }]);
    });

    it("uses no whitespace (separators)", () => {
        const env = wrapWithEnvelope("x", [{ a: 1 }], FROZEN_DATE);
        const text = Buffer.from(serializeEnvelope(env)).toString("utf-8");
        expect(text).not.toMatch(/: /); // no ": " (with space)
        expect(text).not.toMatch(/, /); // no ", " (with space)
    });
});
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pnpm test envelope
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write implementation**

Create `supabase-dataset-updater/src/envelope.ts`:
```typescript
import { createHash } from "node:crypto";
import { canonicalStringify } from "./canonical-stringify";

export const SCHEMA_VERSION = 1;

export interface EnvelopeMeta {
    exported_at: string; // ISO-8601 with "Z" suffix
    sha256: string; // 64-char lowercase hex over canonical rows only
    row_count: number;
    schema_version: number;
    source_table: string;
    source_patch?: string; // only set for per-patch tables
}

export interface EnvelopedTable {
    __meta: EnvelopeMeta;
    rows: unknown[];
}

/**
 * Wrap a list of rows with the canonical __meta envelope.
 *
 * Mirrors export_to_json.py:export_table / export_table_per_patch exactly:
 *  - exported_at: now in UTC, ISO-8601, "Z" suffix (replaces "+00:00")
 *  - sha256: lowercase hex over canonicalStringify(rows) only
 *  - row_count, schema_version, source_table, optional source_patch
 *
 * The sha256 deliberately excludes __meta itself so the same rows produce
 * the same hash regardless of timestamp — this lets the client verify
 * integrity without re-deriving exported_at.
 */
export function wrapWithEnvelope(
    table: string,
    rows: unknown[],
    exportedAt: Date,
    sourcePatch?: string
): EnvelopedTable {
    const sha256 = createHash("sha256")
        .update(canonicalStringify(rows))
        .digest("hex");

    const meta: EnvelopeMeta = {
        exported_at: exportedAt.toISOString().replace(/\.\d{3}Z$/, "Z"),
        sha256,
        row_count: rows.length,
        schema_version: SCHEMA_VERSION,
        source_table: table,
    };

    if (sourcePatch !== undefined) {
        meta.source_patch = sourcePatch;
    }

    return { __meta: meta, rows };
}

/**
 * Serialize an enveloped table to UTF-8 JSON bytes ready to write to disk.
 *
 * Uses canonicalStringify to keep the on-disk form deterministic — important
 * for self-check.ts which re-reads the file and recomputes sha256.
 *
 * Note: the on-disk format is canonical JSON over the WHOLE envelope (__meta
 * + rows), but the embedded sha256 is over rows only. self-check.ts knows to
 * re-stringify only `rows`.
 */
export function serializeEnvelope(env: EnvelopedTable): Uint8Array {
    return canonicalStringify(env);
}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pnpm test envelope
```
Expected: 7 tests pass.

If the `exported_at` test fails because of the `.000Z` → `Z` regex: the spec uses `.replace("+00:00", "Z")` in Python, but Node's `toISOString()` produces `.000Z` directly (no `+00:00`). The `.replace(/\.\d{3}Z$/, "Z")` strips the `.000` to match Python's output exactly.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/envelope.ts supabase-dataset-updater/tests/envelope.test.ts
git commit -m "feat(etl): envelope — wrap rows with __meta and serialize to canonical bytes"
```

---

## Phase C — IO Modules (mock-first)

### Task 9: cdn-fetcher — fetch and verify previous-patch files

**Files:**
- Create: `supabase-dataset-updater/src/cdn-fetcher.ts`
- Create: `supabase-dataset-updater/tests/cdn-fetcher.test.ts`

Fetches the previous patch's `matchups_<patch>.json` and `synergies_<patch>.json` from the live CDN and verifies their integrity. Soft-fail on 404 (expected for first runs and aged-out patches), hard-fail on sha256 mismatch (data corruption).

- [ ] **Step 1: Write failing tests**

Create `supabase-dataset-updater/tests/cdn-fetcher.test.ts`:
```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
    fetchPreviousPatchFiles,
    verifyEnvelopeIntegrity,
} from "../src/cdn-fetcher";
import { wrapWithEnvelope, serializeEnvelope } from "../src/envelope";

const CDN = "https://chertixd.github.io/lol-draft-helper-cdn/data";

const validBuffer = (table: string, rows: unknown[]) =>
    Buffer.from(serializeEnvelope(wrapWithEnvelope(table, rows, new Date(), "16.7")));

describe("verifyEnvelopeIntegrity", () => {
    it("returns true for a freshly written envelope", () => {
        const buf = validBuffer("matchups", [{ a: 1 }]);
        expect(verifyEnvelopeIntegrity(buf)).toBe(true);
    });

    it("returns false when rows are tampered with", () => {
        const env = wrapWithEnvelope("matchups", [{ a: 1 }], new Date(), "16.7");
        env.rows = [{ a: 2 }]; // tamper
        const buf = Buffer.from(serializeEnvelope(env));
        expect(verifyEnvelopeIntegrity(buf)).toBe(false);
    });

    it("returns false when the buffer is not JSON", () => {
        expect(verifyEnvelopeIntegrity(Buffer.from("not json"))).toBe(false);
    });

    it("returns false when __meta is missing", () => {
        expect(verifyEnvelopeIntegrity(Buffer.from('{"rows":[]}'))).toBe(false);
    });
});

describe("fetchPreviousPatchFiles", () => {
    let fetchMock: ReturnType<typeof vi.fn>;
    beforeEach(() => {
        fetchMock = vi.fn();
        // @ts-expect-error overriding global
        globalThis.fetch = fetchMock;
    });
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("returns a Map of file → Buffer on success", async () => {
        const matchupsBuf = validBuffer("matchups", [{ x: 1 }]);
        const synergiesBuf = validBuffer("synergies", [{ y: 2 }]);
        fetchMock.mockImplementation(async (url: string) => {
            if (url.endsWith("matchups_16.7.json")) {
                return new Response(matchupsBuf, { status: 200 });
            }
            if (url.endsWith("synergies_16.7.json")) {
                return new Response(synergiesBuf, { status: 200 });
            }
            return new Response("", { status: 404 });
        });

        const result = await fetchPreviousPatchFiles(CDN, "16.7");
        expect(result).not.toBeNull();
        expect(result!.size).toBe(2);
        expect(result!.get("matchups_16.7.json")).toBeInstanceOf(Buffer);
        expect(result!.get("synergies_16.7.json")).toBeInstanceOf(Buffer);
    });

    it("returns null on 404 (soft-fail for first run / aged-out patch)", async () => {
        fetchMock.mockResolvedValue(new Response("", { status: 404 }));
        const result = await fetchPreviousPatchFiles(CDN, "99.99");
        expect(result).toBeNull();
    });

    it("throws on sha256 mismatch (hard-fail for corruption)", async () => {
        const env = wrapWithEnvelope("matchups", [{ x: 1 }], new Date(), "16.7");
        env.rows = [{ x: 2 }]; // tamper
        const buf = Buffer.from(serializeEnvelope(env));
        fetchMock.mockResolvedValue(new Response(buf, { status: 200 }));

        await expect(fetchPreviousPatchFiles(CDN, "16.7")).rejects.toThrow(
            /sha256 mismatch/i
        );
    });

    it("throws on non-200, non-404 (hard-fail for unexpected status)", async () => {
        fetchMock.mockResolvedValue(new Response("", { status: 500 }));
        await expect(fetchPreviousPatchFiles(CDN, "16.7")).rejects.toThrow(
            /unexpected status 500/i
        );
    });
});
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pnpm test cdn-fetcher
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write implementation**

Create `supabase-dataset-updater/src/cdn-fetcher.ts`:
```typescript
import { createHash } from "node:crypto";
import { canonicalStringify } from "./canonical-stringify";

/**
 * Fetch the previous patch's per-patch files from the live CDN.
 *
 * Returns:
 *  - Map<filename, Buffer> on success (one entry per per-patch table)
 *  - null on 404 (no previous patch yet — first run or aged out)
 *
 * Throws on:
 *  - sha256 mismatch (CDN content is corrupted; never publish on top of it)
 *  - unexpected HTTP status (non-200, non-404 — server error etc.)
 */
export async function fetchPreviousPatchFiles(
    cdnBaseUrl: string,
    previousPatch: string
): Promise<Map<string, Buffer> | null> {
    const filenames = [
        `matchups_${previousPatch}.json`,
        `synergies_${previousPatch}.json`,
    ];

    const out = new Map<string, Buffer>();
    for (const filename of filenames) {
        const url = `${cdnBaseUrl.replace(/\/$/, "")}/${filename}`;
        const resp = await fetch(url);

        if (resp.status === 404) {
            // First file 404 → previous patch doesn't exist on CDN.
            // Soft-fail: caller proceeds with current patch only.
            return null;
        }
        if (!resp.ok) {
            throw new Error(
                `cdn-fetcher: unexpected status ${resp.status} fetching ${url}`
            );
        }

        const buf = Buffer.from(await resp.arrayBuffer());
        if (!verifyEnvelopeIntegrity(buf)) {
            throw new Error(
                `cdn-fetcher: sha256 mismatch in ${filename} from ${cdnBaseUrl}`
            );
        }
        out.set(filename, buf);
    }
    return out;
}

/**
 * Re-compute sha256 over the rows in a serialized envelope and compare
 * against __meta.sha256. Returns true iff the envelope is intact.
 *
 * Used by cdn-fetcher (validate previous-patch files before reuse) and
 * by self-check (validate freshly written outputs before push).
 */
export function verifyEnvelopeIntegrity(buf: Buffer): boolean {
    let parsed: unknown;
    try {
        parsed = JSON.parse(buf.toString("utf-8"));
    } catch {
        return false;
    }
    if (
        typeof parsed !== "object" ||
        parsed === null ||
        !("__meta" in parsed) ||
        !("rows" in parsed)
    ) {
        return false;
    }
    const meta = (parsed as { __meta: { sha256?: string } }).__meta;
    const rows = (parsed as { rows: unknown[] }).rows;
    if (typeof meta.sha256 !== "string") return false;

    const computed = createHash("sha256")
        .update(canonicalStringify(rows))
        .digest("hex");
    return computed === meta.sha256;
}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pnpm test cdn-fetcher
```
Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/cdn-fetcher.ts supabase-dataset-updater/tests/cdn-fetcher.test.ts
git commit -m "feat(etl): cdn-fetcher — fetch and verify previous-patch files (soft-fail 404, hard-fail mismatch)"
```

### Task 10: writer — write 8 enveloped tables to disk

**Files:**
- Create: `supabase-dataset-updater/src/writer.ts`
- Create: `supabase-dataset-updater/tests/writer.test.ts`

The writer takes pre-built rows (one entry per logical table) plus pre-fetched previous-patch buffers, and writes the final 8-or-10 files to a target directory.

- [ ] **Step 1: Write failing test**

Create `supabase-dataset-updater/tests/writer.test.ts`:
```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { vol } from "memfs";
import { writeOutputs, TableInputs } from "../src/writer";
import { verifyEnvelopeIntegrity } from "../src/cdn-fetcher";
import { wrapWithEnvelope, serializeEnvelope } from "../src/envelope";

// memfs swaps node:fs with an in-memory FS for the duration of these tests.
vi.mock("node:fs", async () => {
    const memfs = await import("memfs");
    return memfs.fs;
});
vi.mock("node:fs/promises", async () => {
    const memfs = await import("memfs");
    return memfs.fs.promises;
});

import { vi } from "vitest";

const FROZEN = new Date("2026-05-03T12:00:00Z");

const minimalInputs: TableInputs = {
    champions: [{ key: "266", name: "Aatrox" }],
    patches: [{ patch: "16.8" }, { patch: "16.7" }],
    items: [{ patch: "16.8", item_id: 1001, name: "Boots", gold: 300 }],
    runes: [{ patch: "16.8", rune_id: 8005, data: { id: 8005 } }],
    summoner_spells: [{ patch: "16.8", spell_key: "4", name: "Flash" }],
    champion_stats: [
        {
            patch: "16.8",
            champion_key: "266",
            role: "top",
            games: 100,
            wins: 50,
            damage_profile: {},
            stats_by_time: [],
        },
    ],
    matchups_current: [
        {
            patch: "16.8",
            champion_key: "266",
            role: "top",
            opponent_key: "157",
            opponent_role: "top",
            games: 50,
            wins: 25,
        },
    ],
    synergies_current: [
        {
            patch: "16.8",
            champion_key: "266",
            role: "top",
            mate_key: "157",
            mate_role: "middle",
            games: 50,
            wins: 30,
        },
    ],
};

describe("writeOutputs", () => {
    beforeEach(() => {
        vol.reset();
        vol.fromJSON({ "/out/.keep": "" });
    });

    it("writes 6 global tables + 2 current-patch shards (no previous)", async () => {
        await writeOutputs("/out", minimalInputs, "16.8", null, FROZEN);

        const files = Object.keys(vol.toJSON()).map((p) =>
            p.replace("/out/", "")
        );
        expect(files.sort()).toEqual(
            [
                ".keep",
                "champion_stats.json",
                "champions.json",
                "items.json",
                "matchups_16.8.json",
                "patches.json",
                "runes.json",
                "summoner_spells.json",
                "synergies_16.8.json",
            ].sort()
        );
    });

    it("writes 6 global + 2 current + 2 previous when previousFiles is provided", async () => {
        const prevMatchups = Buffer.from(
            serializeEnvelope(
                wrapWithEnvelope("matchups", [], FROZEN, "16.7")
            )
        );
        const prevSynergies = Buffer.from(
            serializeEnvelope(
                wrapWithEnvelope("synergies", [], FROZEN, "16.7")
            )
        );

        await writeOutputs(
            "/out",
            minimalInputs,
            "16.8",
            {
                patch: "16.7",
                files: new Map([
                    ["matchups_16.7.json", prevMatchups],
                    ["synergies_16.7.json", prevSynergies],
                ]),
            },
            FROZEN
        );

        const files = Object.keys(vol.toJSON()).map((p) =>
            p.replace("/out/", "")
        );
        expect(files).toContain("matchups_16.7.json");
        expect(files).toContain("synergies_16.7.json");
        expect(files).toContain("matchups_16.8.json");
        expect(files).toContain("synergies_16.8.json");
    });

    it("each written file has a valid envelope (sha256 verifies)", async () => {
        await writeOutputs("/out", minimalInputs, "16.8", null, FROZEN);
        for (const name of [
            "champions.json",
            "patches.json",
            "matchups_16.8.json",
            "synergies_16.8.json",
        ]) {
            const buf = Buffer.from(vol.readFileSync(`/out/${name}`) as Buffer);
            expect(verifyEnvelopeIntegrity(buf)).toBe(true);
        }
    });
});
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pnpm test writer
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write implementation**

Create `supabase-dataset-updater/src/writer.ts`:
```typescript
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { wrapWithEnvelope, serializeEnvelope } from "./envelope";

/**
 * Pre-built rows for every logical output table.
 *
 * Per-patch tables (matchups, synergies) appear here only for the CURRENT
 * patch — the previous patch's content is read straight from a CDN buffer
 * and re-emitted verbatim, so we don't re-shape it.
 */
export interface TableInputs {
    champions: unknown[];
    patches: unknown[];
    items: unknown[];
    runes: unknown[];
    summoner_spells: unknown[];
    champion_stats: unknown[];
    matchups_current: unknown[];
    synergies_current: unknown[];
}

/**
 * Pre-fetched previous-patch buffers. When null, the previous patch is
 * omitted from the output (first run or aged-out).
 */
export interface PreviousPatchBundle {
    patch: string;
    files: Map<string, Buffer>; // matchups_<patch>.json, synergies_<patch>.json
}

/**
 * Write all enveloped output files to outDir.
 *
 * Globals: champions, patches, items, runes, summoner_spells, champion_stats.
 * Current-patch shards: matchups_<current>.json, synergies_<current>.json.
 * Previous-patch shards (if provided): copied verbatim from the CDN buffer
 * (already enveloped — re-serialising would change __meta.exported_at).
 */
export async function writeOutputs(
    outDir: string,
    tables: TableInputs,
    currentPatch: string,
    previousFiles: PreviousPatchBundle | null,
    exportedAt: Date
): Promise<void> {
    mkdirSync(outDir, { recursive: true });

    // 6 global tables
    const globals: Array<[string, unknown[]]> = [
        ["champion_stats", tables.champion_stats],
        ["champions", tables.champions],
        ["items", tables.items],
        ["patches", tables.patches],
        ["runes", tables.runes],
        ["summoner_spells", tables.summoner_spells],
    ];

    for (const [table, rows] of globals) {
        const env = wrapWithEnvelope(table, rows, exportedAt);
        writeFileSync(join(outDir, `${table}.json`), serializeEnvelope(env));
    }

    // Current-patch shards
    const currentMatchups = wrapWithEnvelope(
        "matchups",
        tables.matchups_current,
        exportedAt,
        currentPatch
    );
    writeFileSync(
        join(outDir, `matchups_${currentPatch}.json`),
        serializeEnvelope(currentMatchups)
    );
    const currentSynergies = wrapWithEnvelope(
        "synergies",
        tables.synergies_current,
        exportedAt,
        currentPatch
    );
    writeFileSync(
        join(outDir, `synergies_${currentPatch}.json`),
        serializeEnvelope(currentSynergies)
    );

    // Previous-patch shards (verbatim copy from CDN buffer; do not re-envelope)
    if (previousFiles !== null) {
        for (const [filename, buf] of previousFiles.files) {
            writeFileSync(join(outDir, filename), buf);
        }
    }
}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pnpm test writer
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/writer.ts supabase-dataset-updater/tests/writer.test.ts
git commit -m "feat(etl): writer — write 8/10 enveloped tables (globals + current + optional previous)"
```

### Task 11: self-check — verify all written files (Safety Layer 2)

**Files:**
- Create: `supabase-dataset-updater/src/self-check.ts`
- Create: `supabase-dataset-updater/tests/self-check.test.ts`

CLI script run between writer and gh-pages publish. Reads every JSON file in the directory, recomputes sha256 over the canonical rows, asserts match against `__meta.sha256`. Mismatch → exit 1 → no publish.

- [ ] **Step 1: Write failing tests**

Create `supabase-dataset-updater/tests/self-check.test.ts`:
```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { vol } from "memfs";
import { verifyAllOutputs } from "../src/self-check";
import { wrapWithEnvelope, serializeEnvelope } from "../src/envelope";

vi.mock("node:fs", async () => (await import("memfs")).fs);
vi.mock("node:fs/promises", async () => (await import("memfs")).fs.promises);

const FROZEN = new Date("2026-05-03T12:00:00Z");

describe("verifyAllOutputs", () => {
    beforeEach(() => {
        vol.reset();
    });

    it("passes when all files are intact", async () => {
        const env1 = serializeEnvelope(
            wrapWithEnvelope("champions", [{ key: "266" }], FROZEN)
        );
        const env2 = serializeEnvelope(
            wrapWithEnvelope("matchups", [], FROZEN, "16.8")
        );
        vol.fromJSON({
            "/out/champions.json": Buffer.from(env1).toString("utf-8"),
            "/out/matchups_16.8.json": Buffer.from(env2).toString("utf-8"),
        });

        await expect(verifyAllOutputs("/out")).resolves.not.toThrow();
    });

    it("throws when any file's sha256 does not match its rows", async () => {
        const env = wrapWithEnvelope("champions", [{ key: "266" }], FROZEN);
        env.rows = [{ key: "157" }]; // tamper
        vol.fromJSON({
            "/out/champions.json": Buffer.from(serializeEnvelope(env)).toString("utf-8"),
        });

        await expect(verifyAllOutputs("/out")).rejects.toThrow(/sha256 mismatch/i);
    });

    it("throws when a file is not valid JSON", async () => {
        vol.fromJSON({ "/out/champions.json": "not json" });
        await expect(verifyAllOutputs("/out")).rejects.toThrow();
    });

    it("throws when no .json files are present", async () => {
        vol.fromJSON({ "/out/.keep": "" });
        await expect(verifyAllOutputs("/out")).rejects.toThrow(/no \.json files/i);
    });
});
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pnpm test self-check
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write implementation**

Create `supabase-dataset-updater/src/self-check.ts`:
```typescript
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { verifyEnvelopeIntegrity } from "./cdn-fetcher";

/**
 * Verify every .json file in `dir` carries a valid __meta envelope whose
 * sha256 matches its rows. Throws on first mismatch with the offending path.
 *
 * Safety Layer 2: this runs in CI between writer and peaceiris/actions-gh-pages.
 * If it throws, the workflow exits 1 and no publish happens — yesterday's CDN
 * content stays valid until the next cron.
 */
export async function verifyAllOutputs(dir: string): Promise<void> {
    const entries = readdirSync(dir).filter((f) => f.endsWith(".json"));
    if (entries.length === 0) {
        throw new Error(`self-check: no .json files in ${dir}`);
    }
    for (const file of entries) {
        const path = join(dir, file);
        const buf = readFileSync(path);
        if (!verifyEnvelopeIntegrity(buf)) {
            throw new Error(
                `self-check: sha256 mismatch or malformed envelope in ${path}`
            );
        }
    }
    console.log(`[self-check] verified ${entries.length} files in ${dir}`);
}

// CLI entry point: `tsx src/self-check.ts public/data`
if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("self-check.ts")) {
    const dir = process.argv[2] ?? "public/data";
    verifyAllOutputs(dir).catch((err) => {
        console.error(`[self-check] FAIL: ${err.message}`);
        process.exit(1);
    });
}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pnpm test self-check
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/self-check.ts supabase-dataset-updater/tests/self-check.test.ts
git commit -m "feat(etl): self-check — verify all output files before publish (Safety Layer 2)"
```

### Task 12: smoke-test — verify live CDN content matches local (Safety Layer 3)

**Files:**
- Create: `supabase-dataset-updater/src/smoke-test.ts`
- Create: `supabase-dataset-updater/tests/smoke-test.test.ts`

CLI script run after gh-pages publish. Reads each local file's `__meta.sha256`, fetches the corresponding URL from the live CDN, asserts the live `__meta.sha256` matches local. Catches push-mechanic failures.

- [ ] **Step 1: Write failing tests**

Create `supabase-dataset-updater/tests/smoke-test.test.ts`:
```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { vol } from "memfs";
import { verifyLiveCdn } from "../src/smoke-test";
import { wrapWithEnvelope, serializeEnvelope } from "../src/envelope";

vi.mock("node:fs", async () => (await import("memfs")).fs);

const FROZEN = new Date("2026-05-03T12:00:00Z");
const CDN = "https://chertixd.github.io/lol-draft-helper-cdn/data";

describe("verifyLiveCdn", () => {
    let fetchMock: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        vol.reset();
        fetchMock = vi.fn();
        // @ts-expect-error overriding global
        globalThis.fetch = fetchMock;
    });

    it("passes when live CDN content matches local", async () => {
        const env = serializeEnvelope(
            wrapWithEnvelope("champions", [{ key: "266" }], FROZEN)
        );
        const buf = Buffer.from(env);
        vol.fromJSON({ "/out/champions.json": buf.toString("utf-8") });

        fetchMock.mockResolvedValue(new Response(buf, { status: 200 }));

        await expect(
            verifyLiveCdn(CDN, "/out", { retries: 0, sleepMs: 0 })
        ).resolves.not.toThrow();
    });

    it("throws when live sha256 differs from local", async () => {
        const local = serializeEnvelope(
            wrapWithEnvelope("champions", [{ key: "266" }], FROZEN)
        );
        const remote = serializeEnvelope(
            wrapWithEnvelope("champions", [{ key: "157" }], FROZEN)
        );
        vol.fromJSON({
            "/out/champions.json": Buffer.from(local).toString("utf-8"),
        });

        fetchMock.mockResolvedValue(new Response(Buffer.from(remote), { status: 200 }));

        await expect(
            verifyLiveCdn(CDN, "/out", { retries: 0, sleepMs: 0 })
        ).rejects.toThrow(/sha256 mismatch/i);
    });

    it("retries on transient 404 (edge cache propagation)", async () => {
        const env = serializeEnvelope(
            wrapWithEnvelope("champions", [], FROZEN)
        );
        const buf = Buffer.from(env);
        vol.fromJSON({ "/out/champions.json": buf.toString("utf-8") });

        fetchMock
            .mockResolvedValueOnce(new Response("", { status: 404 }))
            .mockResolvedValueOnce(new Response("", { status: 404 }))
            .mockResolvedValueOnce(new Response(buf, { status: 200 }));

        await expect(
            verifyLiveCdn(CDN, "/out", { retries: 3, sleepMs: 0 })
        ).resolves.not.toThrow();

        expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it("throws after exhausting retries on 404", async () => {
        const buf = Buffer.from(
            serializeEnvelope(wrapWithEnvelope("champions", [], FROZEN))
        );
        vol.fromJSON({ "/out/champions.json": buf.toString("utf-8") });

        fetchMock.mockResolvedValue(new Response("", { status: 404 }));

        await expect(
            verifyLiveCdn(CDN, "/out", { retries: 2, sleepMs: 0 })
        ).rejects.toThrow(/404/);
    });
});
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pnpm test smoke-test
```
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write implementation**

Create `supabase-dataset-updater/src/smoke-test.ts`:
```typescript
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

interface SmokeOptions {
    retries: number; // additional attempts after the first; 3 is reasonable for prod
    sleepMs: number; // delay between attempts; 30000 in prod
}

/**
 * Verify each local .json file's __meta.sha256 matches what the live CDN
 * serves at the same filename. Retries on 404 to absorb GitHub Pages edge
 * propagation lag.
 *
 * Safety Layer 3: this runs after peaceiris/actions-gh-pages succeeds. If
 * it throws, the workflow fails — but the CDN is already in a broken state
 * by then. The point of this layer is fast detection, not prevention.
 */
export async function verifyLiveCdn(
    cdnBaseUrl: string,
    localDir: string,
    opts: SmokeOptions = { retries: 3, sleepMs: 30_000 }
): Promise<void> {
    const files = readdirSync(localDir).filter((f) => f.endsWith(".json"));
    for (const filename of files) {
        const localBuf = readFileSync(join(localDir, filename));
        const localSha = JSON.parse(localBuf.toString("utf-8")).__meta?.sha256;
        if (typeof localSha !== "string") {
            throw new Error(`smoke-test: local ${filename} has no __meta.sha256`);
        }

        const url = `${cdnBaseUrl.replace(/\/$/, "")}/${filename}`;
        const liveSha = await fetchWithRetries(url, opts);
        if (liveSha !== localSha) {
            throw new Error(
                `smoke-test: sha256 mismatch in ${filename} (live=${liveSha}, local=${localSha})`
            );
        }
    }
    console.log(
        `[smoke-test] verified ${files.length} files against ${cdnBaseUrl}`
    );
}

async function fetchWithRetries(
    url: string,
    opts: SmokeOptions
): Promise<string> {
    const totalAttempts = opts.retries + 1;
    for (let attempt = 1; attempt <= totalAttempts; attempt++) {
        const resp = await fetch(url);
        if (resp.ok) {
            const text = await resp.text();
            const sha = JSON.parse(text).__meta?.sha256;
            if (typeof sha !== "string") {
                throw new Error(`smoke-test: live ${url} has no __meta.sha256`);
            }
            return sha;
        }
        if (resp.status !== 404) {
            throw new Error(
                `smoke-test: unexpected status ${resp.status} fetching ${url}`
            );
        }
        if (attempt < totalAttempts) {
            await new Promise((r) => setTimeout(r, opts.sleepMs));
        }
    }
    throw new Error(`smoke-test: 404 after ${totalAttempts} attempts: ${url}`);
}

// CLI entry point: `tsx src/smoke-test.ts public/data`
if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("smoke-test.ts")) {
    const localDir = process.argv[2] ?? "public/data";
    const cdn =
        process.env.CDN_BASE_URL ??
        "https://chertixd.github.io/lol-draft-helper-cdn/data";
    verifyLiveCdn(cdn, localDir).catch((err) => {
        console.error(`[smoke-test] FAIL: ${err.message}`);
        process.exit(1);
    });
}
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
pnpm test smoke-test
```
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add supabase-dataset-updater/src/smoke-test.ts supabase-dataset-updater/tests/smoke-test.test.ts
git commit -m "feat(etl): smoke-test — verify live CDN matches local (Safety Layer 3)"
```

---

## Phase D — Orchestrator

### Task 13: Row-shape types module

**Files:**
- Create: `supabase-dataset-updater/src/models/Rows.ts`

The row shapes were inline types in `supabase-etl.ts`. Extract into a dedicated module so `etl.ts` and `writer.ts` import from one source of truth.

- [ ] **Step 1: Create the file**

Create `supabase-dataset-updater/src/models/Rows.ts`:
```typescript
/**
 * Row shapes for the 8 logical tables produced by the ETL.
 *
 * Field names and types match what the Tauri client (json_repo.py) expects.
 * Any change here REQUIRES coordination with json_repo.py — the shapes are
 * coupled by the canonical sha256 hash.
 *
 * Source-of-truth field origins:
 *  - patch / champion_key / role / opponent_key / etc. — Lolalytics responses
 *  - games / wins — derived from Lolalytics with Math.round (integer values)
 */

export interface ChampionRow {
    key: string;
    name: string;
    i18n: { zh_CN: { name: string | undefined } };
}

export interface PatchRow {
    patch: string;
}

export interface ItemRow {
    patch: string;
    item_id: number;
    name: string;
    gold: number;
}

export interface RuneRow {
    patch: string;
    rune_id: number;
    data: {
        id: number;
        key: string;
        name: string;
        icon: string;
        pathId: number;
    };
}

export interface SummonerSpellRow {
    patch: string;
    spell_key: string;
    name: string;
}

export interface ChampionStatsRow {
    patch: string;
    champion_key: string;
    role: string;
    games: number;
    wins: number;
    damage_profile: unknown;
    stats_by_time: unknown;
}

export interface MatchupRow {
    patch: string;
    champion_key: string;
    role: string;
    opponent_key: string;
    opponent_role: string;
    games: number;
    wins: number;
}

export interface SynergyRow {
    patch: string;
    champion_key: string;
    role: string;
    mate_key: string;
    mate_role: string;
    games: number;
    wins: number;
}
```

- [ ] **Step 2: Verify typecheck**

```bash
cd supabase-dataset-updater
pnpm typecheck
```
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add supabase-dataset-updater/src/models/Rows.ts
git commit -m "refactor(etl): extract row-shape types to models/Rows.ts"
```

### Task 14: etl.ts — pure orchestrator (no business logic)

**Files:**
- Create: `supabase-dataset-updater/src/etl.ts`

The orchestrator wires existing modules together. No business logic — it's a recipe, readable top-to-bottom.

- [ ] **Step 1: Write etl.ts**

Create `supabase-dataset-updater/src/etl.ts`:
```typescript
import {
    getChampions,
    getItems,
    getRunes,
    getSummonerSpells,
    getVersions,
    RiotChampion,
} from "./riot";
import { getChampionDataFromLolalytics } from "./lolalytics";
import { displayNameByRole, Role } from "./models/Role";
import {
    ChampionRow,
    PatchRow,
    ItemRow,
    RuneRow,
    SummonerSpellRow,
    ChampionStatsRow,
    MatchupRow,
    SynergyRow,
} from "./models/Rows";
import { fetchPreviousPatchFiles } from "./cdn-fetcher";
import { writeOutputs, TableInputs, PreviousPatchBundle } from "./writer";

const CDN_BASE_URL =
    process.env.CDN_BASE_URL ??
    "https://chertixd.github.io/lol-draft-helper-cdn/data";

const OUT_DIR = process.env.ETL_OUT_DIR ?? "public/data";

function normalizePatch(version: string): string {
    return version.split(".").slice(0, 2).join(".");
}

function roleToName(role: Role): string {
    return displayNameByRole[role].toLowerCase();
}

async function main(): Promise<void> {
    // Step 1: Patch detection
    const versions = await getVersions();
    const currentVersion = versions[0];
    const previousVersion = versions[1];
    const currentPatch = normalizePatch(currentVersion);
    const previousPatch = previousVersion ? normalizePatch(previousVersion) : null;
    console.log(`[etl] current=${currentPatch}, previous=${previousPatch ?? "(none)"}`);

    // Step 2: Previous-patch restore from live CDN (soft-fail on 404)
    let previousFiles: PreviousPatchBundle | null = null;
    if (previousPatch) {
        const fetched = await fetchPreviousPatchFiles(CDN_BASE_URL, previousPatch);
        if (fetched !== null) {
            previousFiles = { patch: previousPatch, files: fetched };
            console.log(`[etl] restored previous patch ${previousPatch} from CDN`);
        } else {
            console.log(`[etl] previous patch ${previousPatch} not on CDN — skipping`);
        }
    }

    // Step 3 + 4: scrape Riot Data Dragon + Lolalytics
    const [champions, championsZh, runes, items, summonerSpells] = await Promise.all([
        getChampions(currentVersion),
        getChampions(currentVersion, "zh_CN"),
        getRunes(currentVersion),
        getItems(currentVersion),
        getSummonerSpells(currentVersion),
    ]);
    const championByKey = Object.fromEntries(championsZh.map((c) => [c.key, c])) as Record<
        string,
        RiotChampion
    >;

    const championRows: ChampionRow[] = champions.map((c) => ({
        key: c.key,
        name: c.name,
        i18n: { zh_CN: { name: championByKey[c.key]?.name } },
    }));

    const itemRows: ItemRow[] = Object.entries(items).map(([id, item]) => ({
        patch: currentPatch,
        item_id: parseInt(id, 10),
        name: item.name,
        gold: item.gold.total,
    }));

    const runeRows: RuneRow[] = runes.flatMap((path) =>
        path.slots.flatMap((slot) =>
            slot.runes.map((rune) => ({
                patch: currentPatch,
                rune_id: rune.id,
                data: {
                    id: rune.id,
                    key: rune.key,
                    name: rune.name,
                    icon: rune.icon,
                    pathId: path.id,
                },
            }))
        )
    );

    const summonerSpellRows: SummonerSpellRow[] = Object.values(summonerSpells).map((spell) => ({
        patch: currentPatch,
        spell_key: spell.key,
        name: spell.name,
    }));

    // Patches list reflects retention rule (current + optional previous).
    const patchRows: PatchRow[] = previousFiles
        ? [{ patch: currentPatch }, { patch: previousFiles.patch }]
        : [{ patch: currentPatch }];

    // Per-champion Lolalytics scrape (cartesian-fix preserved in lolalytics/index.ts)
    const championStatsRows: ChampionStatsRow[] = [];
    const matchupRows: MatchupRow[] = [];
    const synergyRows: SynergyRow[] = [];

    const testChampionKeys =
        process.env.TEST_CHAMPIONS?.split(",")
            .map((c) => c.trim())
            .filter(Boolean) ?? [];
    const sampleKeys =
        testChampionKeys.length > 0 ? testChampionKeys : champions.map((c) => c.key);

    for (const championKey of sampleKeys) {
        const champion = champions.find(
            (c) =>
                c.key === championKey ||
                c.id.toLowerCase() === championKey.toLowerCase() ||
                c.name.toLowerCase() === championKey.toLowerCase()
        );
        if (!champion) {
            console.log(`[etl] champion "${championKey}" not found, skipping`);
            continue;
        }
        console.log(`[etl] processing ${champion.name} (key=${champion.key})`);
        const championData = await getChampionDataFromLolalytics(currentVersion, champion);
        if (!championData) {
            console.log(`[etl] no usable data for ${champion.name}`);
            continue;
        }

        for (const [roleKey, roleStats] of Object.entries(championData.statsByRole)) {
            const role = Number(roleKey) as Role;
            const roleName = roleToName(role);

            championStatsRows.push({
                patch: currentPatch,
                champion_key: championData.key,
                role: roleName,
                games: Math.round(roleStats.games),
                wins: Math.round(roleStats.wins),
                damage_profile: roleStats.damageProfile,
                stats_by_time: roleStats.statsByTime,
            });

            for (const [opponentRoleKey, opponents] of Object.entries(roleStats.matchup)) {
                const opponentRoleName = roleToName(Number(opponentRoleKey) as Role);
                for (const [opponentKey, mu] of Object.entries(opponents)) {
                    matchupRows.push({
                        patch: currentPatch,
                        champion_key: championData.key,
                        role: roleName,
                        opponent_key: opponentKey,
                        opponent_role: opponentRoleName,
                        games: Math.round(mu.games),
                        wins: Math.round(mu.wins),
                    });
                }
            }

            for (const [mateRoleKey, mates] of Object.entries(roleStats.synergy)) {
                const mateRoleName = roleToName(Number(mateRoleKey) as Role);
                for (const [mateKey, syn] of Object.entries(mates)) {
                    synergyRows.push({
                        patch: currentPatch,
                        champion_key: championData.key,
                        role: roleName,
                        mate_key: mateKey,
                        mate_role: mateRoleName,
                        games: Math.round(syn.games),
                        wins: Math.round(syn.wins),
                    });
                }
            }
        }
    }

    // Step 5: canonical write
    const tables: TableInputs = {
        champions: championRows,
        patches: patchRows,
        items: itemRows,
        runes: runeRows,
        summoner_spells: summonerSpellRows,
        champion_stats: championStatsRows,
        matchups_current: matchupRows,
        synergies_current: synergyRows,
    };
    await writeOutputs(OUT_DIR, tables, currentPatch, previousFiles, new Date());
    console.log(`[etl] wrote outputs to ${OUT_DIR}`);
}

// Exported for the golden test to call deterministically. Direct CLI invocation
// guards on import.meta.url so import-side-effects don't auto-run main during tests.
export { main };

if (
    import.meta.url === `file://${process.argv[1]}` ||
    process.argv[1]?.endsWith("etl.ts") ||
    process.argv[1]?.endsWith("etl.js")
) {
    main().catch((err) => {
        console.error("[etl] FATAL:", err);
        process.exit(1);
    });
}
```

- [ ] **Step 2: Verify typecheck**

```bash
cd supabase-dataset-updater
pnpm typecheck
```
Expected: 0 errors. If `displayNameByRole` types don't line up, look at `src/models/Role.ts` and adjust the import.

- [ ] **Step 3: Commit**

```bash
git add supabase-dataset-updater/src/etl.ts
git commit -m "feat(etl): orchestrator — wires lolalytics + riot + cdn-fetcher + writer"
```

---

## Phase E — Capture & Golden Test

### Task 15: capture-golden.ts — fixture recorder

**Files:**
- Create: `supabase-dataset-updater/scripts/capture-golden.ts`

A one-shot script the operator runs ONCE before merging the migration PR. It hits live Lolalytics + Riot Data Dragon + the live CDN, captures all responses to `tests/fixtures/`, and writes the expected outputs.

- [ ] **Step 1: Write the script**

Create `supabase-dataset-updater/scripts/capture-golden.ts`:
```typescript
/**
 * One-shot fixture capture for the golden test.
 *
 * Run ONCE before the migration cutover:
 *     pnpm test:capture
 *
 * Captures:
 *   - tests/fixtures/lolalytics-responses/<champion-id>-<lane>.json
 *     and <champion-id>-<lane>-champion2.json (raw API responses for
 *     every champion × lane).
 *   - tests/fixtures/riot-responses/{versions,champions-en,champions-zh,
 *     items,runes,summoner-spells}.json (raw Data Dragon).
 *   - tests/fixtures/expected-output/*.json (today's CDN content for
 *     all 8 logical tables, including matchups_<current>, synergies_<current>,
 *     and any previous-patch shards present).
 *
 * The captured fixtures are committed and become the immutable golden
 * reference. The golden test (tests/golden.test.ts) mocks fetch with these
 * fixtures and asserts the new pipeline produces byte-identical output.
 *
 * After capture: do NOT re-run unless the entire migration baseline is
 * intentionally being reset.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { getVersions, getChampions, getItems, getRunes, getSummonerSpells } from "../src/riot";
import { getLolalyticsQwikChampion } from "../src/lolalytics/qwik";
import { getLolalyticsQwikChampion2 } from "../src/lolalytics/qwik-champion2";
import { LOLALYTICS_ROLES } from "../src/lolalytics/roles";

const CDN_BASE_URL =
    process.env.CDN_BASE_URL ?? "https://chertixd.github.io/lol-draft-helper-cdn/data";
const FIXTURES_ROOT = join(__dirname, "..", "tests", "fixtures");

function ensureDir(p: string) {
    mkdirSync(p, { recursive: true });
}

async function captureRiotResponses(version: string): Promise<void> {
    const dir = join(FIXTURES_ROOT, "riot-responses");
    ensureDir(dir);

    const versions = await getVersions();
    writeFileSync(join(dir, "versions.json"), JSON.stringify(versions));

    const championsEn = await getChampions(version);
    writeFileSync(join(dir, "champions-en.json"), JSON.stringify(championsEn));

    const championsZh = await getChampions(version, "zh_CN");
    writeFileSync(join(dir, "champions-zh.json"), JSON.stringify(championsZh));

    const items = await getItems(version);
    writeFileSync(join(dir, "items.json"), JSON.stringify(items));

    const runes = await getRunes(version);
    writeFileSync(join(dir, "runes.json"), JSON.stringify(runes));

    const spells = await getSummonerSpells(version);
    writeFileSync(join(dir, "summoner-spells.json"), JSON.stringify(spells));

    console.log(`[capture] riot responses -> ${dir}`);
}

async function captureLolalyticsResponses(
    version: string,
    championIds: string[]
): Promise<void> {
    const dir = join(FIXTURES_ROOT, "lolalytics-responses");
    ensureDir(dir);

    let captured = 0;
    for (const championId of championIds) {
        for (const lane of LOLALYTICS_ROLES) {
            try {
                const data1 = await getLolalyticsQwikChampion(version, championId, lane);
                writeFileSync(
                    join(dir, `${championId}-${lane}.json`),
                    JSON.stringify(data1)
                );
                const data2 = await getLolalyticsQwikChampion2(version, championId, lane);
                writeFileSync(
                    join(dir, `${championId}-${lane}-champion2.json`),
                    JSON.stringify(data2)
                );
                captured += 2;
            } catch (err) {
                console.log(`[capture] skip ${championId} ${lane}: ${err}`);
            }
        }
    }
    console.log(`[capture] lolalytics responses (${captured} files) -> ${dir}`);
}

async function captureCdnExpectedOutput(): Promise<void> {
    const dir = join(FIXTURES_ROOT, "expected-output");
    ensureDir(dir);

    const filesToFetch = [
        "champions.json",
        "patches.json",
        "items.json",
        "runes.json",
        "summoner_spells.json",
        "champion_stats.json",
    ];

    // Also fetch the per-patch shards: read patches.json first, derive shard names.
    const patchesResp = await fetch(`${CDN_BASE_URL}/patches.json`);
    if (!patchesResp.ok) {
        throw new Error(`capture: cannot read CDN patches.json (${patchesResp.status})`);
    }
    const patchesEnvelope = await patchesResp.json();
    const patches: string[] = (patchesEnvelope.rows as { patch: string }[]).map(
        (r) => r.patch
    );
    for (const patch of patches) {
        filesToFetch.push(`matchups_${patch}.json`);
        filesToFetch.push(`synergies_${patch}.json`);
    }

    for (const filename of filesToFetch) {
        const resp = await fetch(`${CDN_BASE_URL}/${filename}`);
        if (!resp.ok) {
            throw new Error(`capture: ${filename} -> ${resp.status}`);
        }
        const buf = Buffer.from(await resp.arrayBuffer());
        writeFileSync(join(dir, filename), buf);
    }
    console.log(`[capture] CDN expected output (${filesToFetch.length} files) -> ${dir}`);
}

async function main(): Promise<void> {
    const [currentVersion] = await getVersions();
    console.log(`[capture] using version ${currentVersion}`);

    await captureRiotResponses(currentVersion);

    const championsEn = await getChampions(currentVersion);
    const championIds = championsEn.map((c) => c.id);
    await captureLolalyticsResponses(currentVersion, championIds);

    await captureCdnExpectedOutput();

    console.log("[capture] DONE — review tests/fixtures/ before committing");
}

main().catch((err) => {
    console.error("[capture] FATAL:", err);
    process.exit(1);
});
```

- [ ] **Step 2: Verify typecheck (do not run yet — runs against live APIs)**

```bash
cd supabase-dataset-updater
pnpm typecheck
```
Expected: 0 errors.

- [ ] **Step 3: Commit script (without running it yet)**

```bash
git add supabase-dataset-updater/scripts/capture-golden.ts
git commit -m "feat(etl): capture-golden script for one-shot fixture recording"
```

### Task 16: Run capture against live APIs and commit fixtures

**Files:**
- Created by run: `supabase-dataset-updater/tests/fixtures/lolalytics-responses/*.json` (~850 files)
- Created by run: `supabase-dataset-updater/tests/fixtures/riot-responses/*.json` (6 files)
- Created by run: `supabase-dataset-updater/tests/fixtures/expected-output/*.json` (8-10 files)

**This task hits LIVE APIs. Run it ONCE, ideally on a day when Lolalytics is stable. The captured fixtures become the immutable golden reference for the entire migration.**

- [ ] **Step 1: Run the capture script**

```bash
cd supabase-dataset-updater
pnpm test:capture
```
Expected: ~5-15 minutes runtime. Logs `[capture] riot responses -> ...`, `[capture] lolalytics responses (N files) -> ...`, `[capture] CDN expected output -> ...`, `[capture] DONE`.

If Lolalytics rate-limits, the script logs `[capture] skip <champion> <lane>` and continues. As long as MOST champions are captured, the golden test will work — pivotal champions (Aatrox, Garen, Jinx, Nautilus, Yasuo, Lux) MUST succeed.

- [ ] **Step 2: Verify fixtures look reasonable**

```bash
ls supabase-dataset-updater/tests/fixtures/lolalytics-responses/ | wc -l
ls supabase-dataset-updater/tests/fixtures/riot-responses/
ls supabase-dataset-updater/tests/fixtures/expected-output/
```
Expected: ~850 files in lolalytics-responses, 6 in riot-responses, 8-10 in expected-output.

- [ ] **Step 3: Spot-check a fixture**

```bash
head -c 200 supabase-dataset-updater/tests/fixtures/expected-output/champions.json
```
Expected: starts with `{"__meta":{"exported_at":"...","sha256":"...",...`.

- [ ] **Step 4: Commit fixtures**

```bash
git add supabase-dataset-updater/tests/fixtures/
git commit -m "test(etl): capture frozen golden fixtures (lolalytics + riot + CDN expected)"
```

### Task 17: golden.test.ts — full-pipeline byte-equality

**Files:**
- Create: `supabase-dataset-updater/tests/golden.test.ts`

Mocks `fetch` to return the captured fixtures, runs the new ETL pipeline, asserts every output file is byte-identical to `tests/fixtures/expected-output/`.

- [ ] **Step 1: Write the golden test**

Create `supabase-dataset-updater/tests/golden.test.ts`:
```typescript
import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";
import { vol } from "memfs";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

vi.mock("node:fs", async () => (await import("memfs")).fs);
vi.mock("node:fs/promises", async () => (await import("memfs")).fs.promises);

const FIXTURES = join(__dirname, "fixtures");
const REAL_FS = require("node:fs"); // bypass memfs mock for fixture reads

describe("golden test — pipeline produces byte-identical output to expected-output/", () => {
    const expectedDir = join(FIXTURES, "expected-output");
    let expected: Map<string, Buffer>;

    beforeAll(() => {
        expected = new Map();
        for (const f of REAL_FS.readdirSync(expectedDir)) {
            expected.set(f, REAL_FS.readFileSync(join(expectedDir, f)));
        }
    });

    beforeEach(() => {
        vol.reset();
        installFetchMock();
        // Ensure ETL writes into memfs at /out
        process.env.ETL_OUT_DIR = "/out";
        process.env.CDN_BASE_URL = "https://chertixd.github.io/lol-draft-helper-cdn/data";
    });

    it("produces byte-identical 8+ files", async () => {
        // Import etl.ts and call main() directly. main() is exported precisely
        // so the golden test can await it deterministically — no flaky setImmediate.
        const etl = await import("../src/etl");
        await etl.main();

        const produced = new Map<string, Buffer>();
        for (const file of vol.readdirSync("/out") as string[]) {
            produced.set(file, Buffer.from(vol.readFileSync(`/out/${file}`) as Buffer));
        }

        // Each expected file must be present and byte-identical
        for (const [name, expectedBuf] of expected) {
            const actualBuf = produced.get(name);
            if (!actualBuf) {
                throw new Error(`golden test: missing output ${name}`);
            }
            // exported_at differs every run → strip both __meta.exported_at fields
            // before comparing. sha256 stays stable because it's over rows only.
            expect(stripExportedAt(actualBuf)).toBe(stripExportedAt(expectedBuf));
        }
    });
});

function stripExportedAt(buf: Buffer): string {
    return buf.toString("utf-8").replace(/"exported_at":"[^"]+"/, '"exported_at":"<stripped>"');
}

function installFetchMock(): void {
    const lolalyticsDir = join(FIXTURES, "lolalytics-responses");
    const riotDir = join(FIXTURES, "riot-responses");
    const expectedDir = join(FIXTURES, "expected-output");

    const fetchMock = vi.fn(async (url: string) => {
        // Riot Data Dragon: ddragon.leagueoflegends.com/...
        if (url.includes("/api/versions.json")) {
            return new Response(REAL_FS.readFileSync(join(riotDir, "versions.json")));
        }
        if (url.includes("/champion.json")) {
            const isZh = url.includes("zh_CN");
            return new Response(
                REAL_FS.readFileSync(
                    join(riotDir, isZh ? "champions-zh.json" : "champions-en.json")
                )
            );
        }
        if (url.includes("/item.json")) {
            return new Response(REAL_FS.readFileSync(join(riotDir, "items.json")));
        }
        if (url.includes("/runesReforged.json")) {
            return new Response(REAL_FS.readFileSync(join(riotDir, "runes.json")));
        }
        if (url.includes("/summoner.json")) {
            return new Response(REAL_FS.readFileSync(join(riotDir, "summoner-spells.json")));
        }

        // Lolalytics: https://a1.lolalytics.com/mega/?...&c=<id>&lane=<role>...
        const lolaMatch = /[?&]c=([^&]+)&[^?]*lane=([^&]+)/.exec(url);
        if (lolaMatch) {
            const [, championId, lane] = lolaMatch;
            const isChampion2 = url.includes("ep=build-team");
            const filename = isChampion2
                ? `${championId}-${lane}-champion2.json`
                : `${championId}-${lane}.json`;
            const path = join(lolalyticsDir, filename);
            try {
                return new Response(REAL_FS.readFileSync(path));
            } catch {
                return new Response("", { status: 404 });
            }
        }

        // CDN previous-patch fetch
        if (url.startsWith("https://chertixd.github.io/")) {
            const filename = url.split("/").pop()!;
            const path = join(expectedDir, filename);
            try {
                return new Response(REAL_FS.readFileSync(path));
            } catch {
                return new Response("", { status: 404 });
            }
        }

        return new Response("", { status: 404 });
    });

    // @ts-expect-error overriding global
    globalThis.fetch = fetchMock;
}
```

- [ ] **Step 2: Run the golden test**

```bash
pnpm test:golden
```
Expected: 1 test passes (~10-30s runtime).

If it fails: the failure message highlights which file differs. Common causes:
- Lolalytics URL pattern differs from the regex (inspect `qwik.ts`/`qwik-champion2.ts` for exact URL shape and adjust the matcher).
- `exported_at` stripping doesn't catch all sites (extend the regex).
- Row ordering: the writer doesn't sort rows; if the ETL processes champions in a different order than Supabase did, the `rows` array will differ. Mitigation: ETL currently iterates `champions.map((c) => c.key)` — order matches Riot's response, which matched what the old supabase-etl.ts did (same `champions.map`). If still mismatched, add a stable sort in `writer.ts` before serialising.

- [ ] **Step 3: Commit**

```bash
git add supabase-dataset-updater/tests/golden.test.ts
git commit -m "test(etl): golden test — full pipeline byte-equality vs frozen CDN snapshot"
```

---

## Phase F — CI & Workflow Wiring

### Task 18: Add etl-test.yml CI gate

**Files:**
- Create: `.github/workflows/etl-test.yml`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/etl-test.yml`:
```yaml
name: ETL Tests
on:
    pull_request:
        paths:
            - "supabase-dataset-updater/**"
            - ".github/workflows/etl-test.yml"

jobs:
    test:
        runs-on: ubuntu-latest
        steps:
            - uses: actions/checkout@v4

            - name: Install pnpm
              run: npm install -g pnpm

            - uses: actions/setup-node@v4
              with:
                  node-version: lts/*
                  cache: pnpm
                  cache-dependency-path: supabase-dataset-updater/pnpm-lock.yaml

            - name: Install dependencies
              working-directory: supabase-dataset-updater
              run: pnpm install --frozen-lockfile

            - name: Typecheck
              working-directory: supabase-dataset-updater
              run: pnpm typecheck

            - name: Fast tests
              working-directory: supabase-dataset-updater
              run: pnpm test

            - name: Golden test (byte-equality vs frozen snapshot)
              working-directory: supabase-dataset-updater
              run: pnpm test:golden
```

- [ ] **Step 2: Verify YAML syntax**

```bash
cat .github/workflows/etl-test.yml | head -20
```
Expected: file looks like above.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/etl-test.yml
git commit -m "ci: ETL test workflow — typecheck + tests + golden gate on PRs"
```

### Task 19: Modify update-dataset.yml — replace Python steps

**Files:**
- Modify: `.github/workflows/update-dataset.yml`

- [ ] **Step 1: Replace contents**

Overwrite `.github/workflows/update-dataset.yml`:
```yaml
name: "Update Dataset"
on:
    schedule:
        - cron: "0 12 * * *"
    workflow_dispatch:

permissions:
    contents: write

jobs:
    update:
        runs-on: ubuntu-latest
        steps:
            - name: Checkout repository
              uses: actions/checkout@v4

            - name: Install PNPM
              run: npm install -g pnpm

            - name: Sync node version and setup cache
              uses: actions/setup-node@v4
              with:
                  node-version: "lts/*"
                  cache: "pnpm"
                  cache-dependency-path: supabase-dataset-updater/pnpm-lock.yaml

            - name: Install dependencies
              working-directory: supabase-dataset-updater
              run: pnpm install

            - name: Run ETL
              working-directory: supabase-dataset-updater
              run: pnpm update
              env:
                  CDN_BASE_URL: https://chertixd.github.io/lol-draft-helper-cdn/data

            - name: Self-check outputs (Layer 2)
              working-directory: supabase-dataset-updater
              run: pnpm self-check

            - name: Publish to gh-pages branch
              uses: peaceiris/actions-gh-pages@v4
              with:
                  personal_token: ${{ secrets.CDN_DEPLOY_TOKEN }}
                  external_repository: Chertixd/lol-draft-helper-cdn
                  publish_dir: ./supabase-dataset-updater/public
                  publish_branch: gh-pages
                  force_orphan: true
                  user_name: "github-actions[bot]"
                  user_email: "github-actions[bot]@users.noreply.github.com"
                  commit_message: "data: refresh ${{ github.run_id }}"

            - name: Smoke-test live CDN (Layer 3)
              working-directory: supabase-dataset-updater
              run: pnpm smoke-test
              env:
                  CDN_BASE_URL: https://chertixd.github.io/lol-draft-helper-cdn/data
```

- [ ] **Step 2: Verify the diff**

```bash
git diff .github/workflows/update-dataset.yml | head -80
```
Expected: shows removal of "Setup Python", "Install Python deps", "Export Supabase tables to JSON" steps, removal of `SUPABASE_*` env vars, addition of "Self-check outputs" and "Smoke-test live CDN" steps.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update-dataset.yml
git commit -m "ci: update-dataset workflow — drop Python + Supabase, add safety gates"
```

---

## Phase G — Cleanup

### Task 20: Delete obsolete Python files

**Files:**
- Delete: `supabase-dataset-updater/scripts/__init__.py`
- Delete: `supabase-dataset-updater/scripts/export_to_json.py`
- Delete: `supabase-dataset-updater/scripts/test_export_to_json.py`
- Delete: `supabase-dataset-updater/requirements-dev.txt`

- [ ] **Step 1: Verify nothing else references them**

```bash
grep -r "export_to_json" .github/ supabase-dataset-updater/src/ 2>/dev/null
grep -r "requirements-dev" .github/ supabase-dataset-updater/ 2>/dev/null | grep -v node_modules
```
Expected: no matches outside the workflow file (which we've already updated).

- [ ] **Step 2: Delete files**

```bash
rm supabase-dataset-updater/scripts/__init__.py
rm supabase-dataset-updater/scripts/export_to_json.py
rm supabase-dataset-updater/scripts/test_export_to_json.py
rm supabase-dataset-updater/requirements-dev.txt
```

Note: `supabase-dataset-updater/scripts/` directory is NOT empty — `capture-golden.ts` lives there. Don't delete the dir.

- [ ] **Step 3: Commit**

```bash
git add -A supabase-dataset-updater/scripts/ supabase-dataset-updater/requirements-dev.txt
git commit -m "chore(etl): remove obsolete Python exporter and dev requirements"
```

### Task 21: Delete supabase-etl.ts

**Files:**
- Delete: `supabase-dataset-updater/src/supabase-etl.ts`

- [ ] **Step 1: Verify nothing imports it**

```bash
grep -r "supabase-etl" supabase-dataset-updater/ 2>/dev/null | grep -v node_modules
```
Expected: no matches (we replaced its `pnpm update` script entry with `etl.ts` in Task 1).

- [ ] **Step 2: Delete**

```bash
rm supabase-dataset-updater/src/supabase-etl.ts
```

- [ ] **Step 3: Verify typecheck still clean**

```bash
cd supabase-dataset-updater
pnpm typecheck
```
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add -A supabase-dataset-updater/src/supabase-etl.ts
git commit -m "chore(etl): remove supabase-etl.ts (replaced by etl.ts)"
```

---

## Phase H — Final Verification

### Task 22: Local end-to-end smoke (manual operator step)

**Files:** none modified

This task is a manual sanity-check before the PR gets merged. It runs the new pipeline against live APIs and verifies the output matches what the production pipeline would produce.

- [ ] **Step 1: Run ETL locally**

```bash
cd supabase-dataset-updater
pnpm update
```
Expected: ~5-10 minutes runtime. Logs `[etl] current=16.X, previous=16.Y`, `[etl] processing <champion>...`, `[etl] wrote outputs to public/data`.

- [ ] **Step 2: Run self-check**

```bash
pnpm self-check
```
Expected: `[self-check] verified N files in public/data`.

- [ ] **Step 3: List output**

```bash
ls supabase-dataset-updater/public/data/
```
Expected: 8-10 files: champions.json, patches.json, items.json, runes.json, summoner_spells.json, champion_stats.json, matchups_<current>.json, synergies_<current>.json, optionally matchups_<previous>.json + synergies_<previous>.json.

- [ ] **Step 4: Verify Tauri app reads local snapshot**

In one terminal:
```bash
cd supabase-dataset-updater
python -m http.server 8000 --directory ./public/data
```

In another:
```bash
cd counterpick-app
CDN_BASE_URL=http://localhost:8000 pnpm tauri dev
```

Expected: app starts, no `sha256 mismatch` errors, Champion Lookup view loads data, draft recommendations render.

- [ ] **Step 5: No commit needed (smoke test only)**

The output of `pnpm update` lives in `public/data/` which is gitignored.

### Task 23: Self-review the full diff

**Files:** none modified

- [ ] **Step 1: Review the cumulative diff**

```bash
git log --oneline | head -25
git diff <commit-before-task-1>..HEAD --stat
```

Expected commits (chronological):
1. chore(etl): swap supabase deps for vitest + safe-stable-stringify
2. chore(etl): add vitest config and tests/ scaffold
3. feat(etl): canonical-stringify — primitives and empty containers
4. test(etl): canonical-stringify — sorted keys and nesting
5. feat(etl): canonical-stringify — reject NaN/Infinity to match Python
6. feat(etl): canonical-stringify — escape non-ASCII to match Python ensure_ascii
7. test(etl): canonical-stringify — Python golden cases (13 cases)
8. feat(etl): envelope — wrap rows with __meta and serialize to canonical bytes
9. feat(etl): cdn-fetcher — fetch and verify previous-patch files
10. feat(etl): writer — write 8/10 enveloped tables
11. feat(etl): self-check — verify all output files before publish
12. feat(etl): smoke-test — verify live CDN matches local
13. refactor(etl): extract row-shape types to models/Rows.ts
14. feat(etl): orchestrator — wires lolalytics + riot + cdn-fetcher + writer
15. feat(etl): capture-golden script
16. test(etl): capture frozen golden fixtures
17. test(etl): golden test — full pipeline byte-equality
18. ci: ETL test workflow
19. ci: update-dataset workflow — drop Python + Supabase, add safety gates
20. chore(etl): remove obsolete Python exporter and dev requirements
21. chore(etl): remove supabase-etl.ts

Net stat: 0 files Python, +N TypeScript files, ~+1500 LOC TS, ~-500 LOC Python.

- [ ] **Step 2: Run the full test suite one more time**

```bash
cd supabase-dataset-updater
pnpm typecheck
pnpm test
pnpm test:golden
```
Expected: all green.

- [ ] **Step 3: Squash for the PR (optional — depends on team workflow)**

If the team prefers squash-merge: just open the PR — GitHub squashes on merge.

If the team prefers a single linear commit: do an interactive rebase to combine all 21 commits into one. Otherwise, leave as-is and rely on squash-merge.

### Task 24: Open the PR

**Files:** none modified

- [ ] **Step 1: Push branch**

```bash
git push -u origin <branch-name>
```

- [ ] **Step 2: Open PR with detailed body**

Use `gh pr create` with a body that:
- Links to `docs/superpowers/specs/2026-05-03-etl-supabase-removal-design.md`
- Lists the 4-layer safety stack
- Lists the rollback plan (`git revert <merge-commit>`)
- Notes that Supabase secrets remain in repo settings as cold backup for 2-3 weeks
- Points reviewers to the golden test as the primary verification
- Reminds: this PR is meant to be merged ATOMICALLY — squash-merge preferred

- [ ] **Step 3: Wait for CI green**

The new `etl-test.yml` workflow should run automatically. All other CI workflows must pass too. Do not merge if any are red.

- [ ] **Step 4: Merge after approval**

Use squash-merge to keep `main` history linear. After merge: monitor the next nightly cron (12:00 UTC) for green status.

---

## Self-Review Checklist (orchestrator note)

After implementing all tasks, before declaring done, the executor should verify:

- [ ] Every spec section has a corresponding task (Phase A-G covers Section 1 pipeline, Section 2 code structure, Section 3 safety, Section 4 workflow).
- [ ] No `TODO`, `TBD`, `implement later` text in source files.
- [ ] All function signatures referenced in later tasks are defined in earlier tasks (`canonicalStringify`, `wrapWithEnvelope`, `serializeEnvelope`, `verifyEnvelopeIntegrity`, `verifyAllOutputs`, `verifyLiveCdn`, `fetchPreviousPatchFiles`, `writeOutputs` — all spelled identically).
- [ ] Cartesian-product fix from `lolalytics/index.ts` is preserved (Task 14 imports `getChampionDataFromLolalytics` unchanged).
- [ ] `hasAnyUsableRole` gate is preserved (lives inside the imported function — not duplicated).
- [ ] No business logic in `etl.ts` — only orchestration (Task 14).
- [ ] Cold backup retention plan is documented (in PR body, Task 24).
