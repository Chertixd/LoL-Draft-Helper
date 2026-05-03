import { describe, it, expect } from "vitest";
import { wrapWithEnvelope, serializeEnvelope, SCHEMA_VERSION } from "../src/envelope";

const FROZEN_DATE = new Date("2026-05-03T12:00:00.000Z");

describe("wrapWithEnvelope", () => {
    it("includes all required __meta fields", () => {
        const env = wrapWithEnvelope("matchups", [{ a: 1 }], FROZEN_DATE);
        expect(env.__meta.source_table).toBe("matchups");
        expect(env.__meta.row_count).toBe(1);
        expect(env.__meta.schema_version).toBe(SCHEMA_VERSION);
        // exported_at must end with "Z" (UTC marker), no millisecond fractions
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
