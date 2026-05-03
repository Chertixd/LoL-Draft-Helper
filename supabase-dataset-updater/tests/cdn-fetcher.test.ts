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
