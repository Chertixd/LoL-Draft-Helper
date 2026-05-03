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
