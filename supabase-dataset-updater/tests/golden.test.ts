/**
 * Golden test — snapshot reproducibility.
 *
 * Runs the full ETL pipeline against captured fixtures (lolalytics +
 * Riot Data Dragon) and compares every written output file byte-for-byte
 * against committed snapshots in tests/fixtures/expected-pipeline-output/.
 *
 * Because __meta.exported_at changes every run, it is stripped from both
 * sides before comparison. __meta.sha256 (over rows only) stays stable
 * and is the true integrity signal.
 *
 * To regenerate snapshots intentionally:
 *   REGENERATE_SNAPSHOT=1 pnpm test:golden
 */

import { describe, it, expect, beforeAll, beforeEach, vi } from "vitest";
import { vol } from "memfs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Hoist real-fs reads BEFORE vi.mock replaces node:fs with memfs.
// vi.importActual returns the real module even after mocking.
// ---------------------------------------------------------------------------
const realFs = await vi.importActual<typeof import("node:fs")>("node:fs");

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const FIXTURES = join(__dirname, "fixtures");
const SNAPSHOT_DIR = join(FIXTURES, "expected-pipeline-output");
const LOLALYTICS_DIR = join(FIXTURES, "lolalytics-responses");
const RIOT_DIR = join(FIXTURES, "riot-responses");
const REGENERATE = process.env.REGENERATE_SNAPSHOT === "1";

// Read all lolalytics fixture files into memory with REAL fs.
// Key format: "<ChampionId>-<lane>" or "<ChampionId>-<lane>-champion2"
const lolalyticsFixtures = new Map<string, unknown>();
for (const f of realFs.readdirSync(LOLALYTICS_DIR) as string[]) {
    if (!f.endsWith(".json")) continue;
    const key = f.replace(/\.json$/, "");
    const raw = realFs.readFileSync(join(LOLALYTICS_DIR, f), "utf-8");
    lolalyticsFixtures.set(key, JSON.parse(raw as string));
}

// Read all Riot fixture files into memory with REAL fs.
const riotFixtures = new Map<string, unknown>();
for (const f of realFs.readdirSync(RIOT_DIR) as string[]) {
    if (!f.endsWith(".json")) continue;
    const key = f.replace(/\.json$/, "");
    const raw = realFs.readFileSync(join(RIOT_DIR, f), "utf-8");
    riotFixtures.set(key, JSON.parse(raw as string));
}

// ---------------------------------------------------------------------------
// Mock node:fs with memfs so etl.ts writes to in-memory fs.
// ---------------------------------------------------------------------------
vi.mock("node:fs", async () => {
    const memfs = await import("memfs");
    return memfs.fs;
});
vi.mock("node:fs/promises", async () => {
    const memfs = await import("memfs");
    return memfs.fs.promises;
});

// ---------------------------------------------------------------------------
// Mock the lolalytics qwik functions directly (fixtures are parsed JSON, not
// raw HTML, so we can't reconstruct the qwik/json script blob).
// ---------------------------------------------------------------------------
vi.mock("../src/lolalytics/qwik", () => ({
    getLolalyticsQwikChampion: vi.fn(),
}));
vi.mock("../src/lolalytics/qwik-champion2", () => ({
    getLolalyticsQwikChampion2: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Mock global fetch for Riot Data Dragon + CDN URLs.
// Champions fixtures are stored as processed arrays (output of getChampions()),
// so we reconstruct the raw DDragon envelope { data: { [id]: champion } }.
// Items + summoner-spells are stored as the .data record, so wrap similarly.
// Versions + runes are stored as the direct response body.
// ---------------------------------------------------------------------------
const MOCK_FETCH = vi.fn(async (url: string): Promise<Response> => {
    const urlStr = String(url);

    // CDN previous-patch files → 404 (soft-fail, pipeline proceeds without prev)
    if (urlStr.includes("chertixd.github.io")) {
        return new Response(null, { status: 404 });
    }

    // Riot Data Dragon
    if (urlStr.includes("ddragon.leagueoflegends.com")) {
        if (urlStr.includes("versions.json")) {
            return jsonResponse(riotFixtures.get("versions"));
        }
        if (urlStr.includes("/zh_CN/champion.json")) {
            return jsonResponse(reconstructChampionsEnvelope(riotFixtures.get("champions-zh") as any[]));
        }
        if (urlStr.includes("/en_US/champion.json")) {
            return jsonResponse(reconstructChampionsEnvelope(riotFixtures.get("champions-en") as any[]));
        }
        if (urlStr.includes("/en_US/item.json")) {
            return jsonResponse({ data: riotFixtures.get("items") });
        }
        if (urlStr.includes("/en_US/runesReforged.json")) {
            return jsonResponse(riotFixtures.get("runes"));
        }
        if (urlStr.includes("/en_US/summoner.json")) {
            return jsonResponse({ data: riotFixtures.get("summoner-spells") });
        }
    }

    console.warn(`[golden mock] unmatched fetch URL: ${urlStr}`);
    return new Response(null, { status: 404 });
});

/** Reconstruct raw DDragon champion.json envelope from processed array. */
function reconstructChampionsEnvelope(arr: Array<{ id: string; key: string; name: string }>) {
    const data: Record<string, { id: string; key: string; name: string }> = {};
    for (const c of arr) {
        data[c.id] = c;
    }
    return { data };
}

function jsonResponse(body: unknown): Response {
    return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
    });
}

// ---------------------------------------------------------------------------
// Helper: strip exported_at from a parsed envelope (it changes per run).
// ---------------------------------------------------------------------------
function stripExportedAt(obj: Record<string, unknown>): Record<string, unknown> {
    if (obj.__meta && typeof obj.__meta === "object") {
        const meta = { ...(obj.__meta as Record<string, unknown>) };
        delete meta.exported_at;
        return { ...obj, __meta: meta };
    }
    return obj;
}

// ---------------------------------------------------------------------------
// Main test
// ---------------------------------------------------------------------------
describe("golden — pipeline snapshot reproducibility", () => {
    beforeAll(async () => {
        // Wire up lolalytics mock implementations (after vi.mock declarations
        // have taken effect, so we can import the mocked module).
        const { getLolalyticsQwikChampion } = await import("../src/lolalytics/qwik");
        const { getLolalyticsQwikChampion2 } = await import(
            "../src/lolalytics/qwik-champion2"
        );

        (getLolalyticsQwikChampion as ReturnType<typeof vi.fn>).mockImplementation(
            (_version: string, championId: string, role: string) => {
                // etl.ts passes champion.id (original casing); qwik.ts lowercases internally.
                // Fixture key uses original casing from capture-golden.ts (it passes champion.id directly).
                // We need to find the right fixture. Try exact match first, then case-insensitive.
                const keyExact = `${championId}-${role}`;
                if (lolalyticsFixtures.has(keyExact)) {
                    return Promise.resolve(lolalyticsFixtures.get(keyExact));
                }
                // Try with capitalised first letter (fixture files use original champion.id casing)
                const capitalised = championId.charAt(0).toUpperCase() + championId.slice(1).toLowerCase();
                const keyCapitalised = `${capitalised}-${role}`;
                if (lolalyticsFixtures.has(keyCapitalised)) {
                    return Promise.resolve(lolalyticsFixtures.get(keyCapitalised));
                }
                // Search case-insensitively
                const keyLower = `${championId.toLowerCase()}-${role}`;
                for (const [k, v] of lolalyticsFixtures) {
                    if (k.toLowerCase() === keyLower) {
                        return Promise.resolve(v);
                    }
                }
                return Promise.reject(new Error(`No lolalytics fixture for ${championId} ${role}`));
            }
        );

        (getLolalyticsQwikChampion2 as ReturnType<typeof vi.fn>).mockImplementation(
            (_version: string, championId: string, role: string) => {
                const keyExact = `${championId}-${role}-champion2`;
                if (lolalyticsFixtures.has(keyExact)) {
                    return Promise.resolve(lolalyticsFixtures.get(keyExact));
                }
                const capitalised = championId.charAt(0).toUpperCase() + championId.slice(1).toLowerCase();
                const keyCapitalised = `${capitalised}-${role}-champion2`;
                if (lolalyticsFixtures.has(keyCapitalised)) {
                    return Promise.resolve(lolalyticsFixtures.get(keyCapitalised));
                }
                const keyLower = `${championId.toLowerCase()}-${role}-champion2`;
                for (const [k, v] of lolalyticsFixtures) {
                    if (k.toLowerCase() === keyLower) {
                        return Promise.resolve(v);
                    }
                }
                return Promise.reject(new Error(`No lolalytics fixture (champion2) for ${championId} ${role}`));
            }
        );
    });

    beforeEach(() => {
        vol.reset();
        vi.stubGlobal("fetch", MOCK_FETCH);

        // Set env vars for the ETL run
        process.env.TEST_CHAMPIONS = "Aatrox,Garen,Jinx,Lux,Nautilus,Yasuo";
        process.env.ETL_OUT_DIR = "/out";
        process.env.CDN_BASE_URL = "https://chertixd.github.io/lol-draft-helper-cdn/data";
    });

    it("produces byte-identical output to committed snapshot (modulo exported_at)", async () => {
        // Run the pipeline
        const { main } = await import("../src/etl");
        await main();

        // Collect all files written to /out
        const written = vol.toJSON() as Record<string, string | Buffer | null>;
        const outputFiles = Object.entries(written)
            .filter(([p]) => p.startsWith("/out/") && !p.endsWith("/"))
            .map(([p, content]) => ({
                filename: p.replace("/out/", ""),
                content: typeof content === "string" ? content : (content as Buffer).toString("utf-8"),
            }));

        expect(outputFiles.length).toBeGreaterThan(0);

        if (REGENERATE) {
            // Write snapshot files with REAL fs
            realFs.mkdirSync(SNAPSHOT_DIR, { recursive: true });
            for (const { filename, content } of outputFiles) {
                realFs.writeFileSync(join(SNAPSHOT_DIR, filename), content);
                console.log(`[golden] snapshot written: ${filename}`);
            }
            console.log(
                `[golden] regenerated ${outputFiles.length} snapshot files in ${SNAPSHOT_DIR}`
            );
            return; // Skip comparison in regen mode
        }

        // Compare each output against snapshot
        for (const { filename, content } of outputFiles) {
            const snapshotPath = join(SNAPSHOT_DIR, filename);
            expect(
                realFs.existsSync(snapshotPath),
                `Snapshot missing for ${filename} — run REGENERATE_SNAPSHOT=1 pnpm test:golden`
            ).toBe(true);

            const snapshotRaw = realFs.readFileSync(snapshotPath, "utf-8") as string;

            // Strip exported_at from both sides before comparison
            let actual: Record<string, unknown>;
            let expected: Record<string, unknown>;
            try {
                actual = stripExportedAt(JSON.parse(content));
                expected = stripExportedAt(JSON.parse(snapshotRaw));
            } catch {
                // Non-JSON file — compare raw bytes
                expect(content, `Mismatch in ${filename}`).toBe(snapshotRaw);
                continue;
            }

            expect(actual, `Mismatch in ${filename}`).toEqual(expected);
        }

        // Also ensure no extra/missing files vs snapshot
        const snapshotFiles = realFs.readdirSync(SNAPSHOT_DIR) as string[];
        const outputFilenames = new Set(outputFiles.map((f) => f.filename));
        for (const sf of snapshotFiles) {
            expect(
                outputFilenames.has(sf),
                `Snapshot file ${sf} was not produced by the pipeline`
            ).toBe(true);
        }
        expect(outputFiles.length, "Output file count mismatch vs snapshot").toBe(
            snapshotFiles.length
        );
    });
});
