import { describe, it, expect, beforeEach, vi } from "vitest";
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
