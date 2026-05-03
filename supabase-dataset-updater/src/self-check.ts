import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { verifyEnvelopeIntegrity } from "./cdn-fetcher";

/**
 * Verify every .json file in `dir` carries a valid __meta envelope whose
 * sha256 matches its rows. Throws on first mismatch with the offending path.
 *
 * Safety Layer 2: this runs in CI between writer and peaceiris/actions-gh-pages.
 * If it throws, the workflow exits 1 and no publish happens — yesterday's CDN
 * content stays valid until the next cron.
 */
export async function verifyAllOutputs(dir: string): Promise<void> {
    const entries = readdirSync(dir).filter((f) => f.endsWith(".json"));
    if (entries.length === 0) {
        throw new Error(`self-check: no .json files in ${dir}`);
    }
    for (const file of entries) {
        const path = join(dir, file);
        const buf = readFileSync(path);
        if (!verifyEnvelopeIntegrity(buf)) {
            throw new Error(
                `self-check: sha256 mismatch or malformed envelope in ${path}`
            );
        }
    }
    console.log(`[self-check] verified ${entries.length} files in ${dir}`);
}

// CLI entry point: `tsx src/self-check.ts public/data`
if (process.argv[1]?.endsWith("self-check.ts") || process.argv[1]?.endsWith("self-check.js")) {
    const dir = process.argv[2] ?? "public/data";
    verifyAllOutputs(dir).catch((err) => {
        console.error(`[self-check] FAIL: ${err.message}`);
        process.exit(1);
    });
}
