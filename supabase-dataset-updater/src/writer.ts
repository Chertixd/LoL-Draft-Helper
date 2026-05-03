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
