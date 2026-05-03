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
