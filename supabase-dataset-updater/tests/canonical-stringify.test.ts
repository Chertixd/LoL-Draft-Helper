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
