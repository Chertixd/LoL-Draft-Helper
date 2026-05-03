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
