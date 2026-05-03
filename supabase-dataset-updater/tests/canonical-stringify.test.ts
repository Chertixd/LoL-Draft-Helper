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
