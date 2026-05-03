import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

interface SmokeOptions {
    retries: number; // additional attempts after the first; 3 is reasonable for prod
    sleepMs: number; // delay between attempts; 30000 in prod
}

/**
 * Verify each local .json file's __meta.sha256 matches what the live CDN
 * serves at the same filename. Retries on 404 to absorb GitHub Pages edge
 * propagation lag.
 *
 * Safety Layer 3: this runs after peaceiris/actions-gh-pages succeeds. If
 * it throws, the workflow fails — but the CDN is already in a broken state
 * by then. The point of this layer is fast detection, not prevention.
 */
export async function verifyLiveCdn(
    cdnBaseUrl: string,
    localDir: string,
    opts: SmokeOptions = { retries: 3, sleepMs: 30_000 }
): Promise<void> {
    const files = readdirSync(localDir).filter((f) => f.endsWith(".json"));
    for (const filename of files) {
        const localBuf = readFileSync(join(localDir, filename));
        const localSha = JSON.parse(localBuf.toString("utf-8")).__meta?.sha256;
        if (typeof localSha !== "string") {
            throw new Error(`smoke-test: local ${filename} has no __meta.sha256`);
        }

        const url = `${cdnBaseUrl.replace(/\/$/, "")}/${filename}`;
        const liveSha = await fetchWithRetries(url, opts);
        if (liveSha !== localSha) {
            throw new Error(
                `smoke-test: sha256 mismatch in ${filename} (live=${liveSha}, local=${localSha})`
            );
        }
    }
    console.log(
        `[smoke-test] verified ${files.length} files against ${cdnBaseUrl}`
    );
}

async function fetchWithRetries(
    url: string,
    opts: SmokeOptions
): Promise<string> {
    const totalAttempts = opts.retries + 1;
    for (let attempt = 1; attempt <= totalAttempts; attempt++) {
        const resp = await fetch(url);
        if (resp.ok) {
            const text = await resp.text();
            const sha = JSON.parse(text).__meta?.sha256;
            if (typeof sha !== "string") {
                throw new Error(`smoke-test: live ${url} has no __meta.sha256`);
            }
            return sha;
        }
        if (resp.status !== 404) {
            throw new Error(
                `smoke-test: unexpected status ${resp.status} fetching ${url}`
            );
        }
        if (attempt < totalAttempts) {
            await new Promise((r) => setTimeout(r, opts.sleepMs));
        }
    }
    throw new Error(`smoke-test: 404 after ${totalAttempts} attempts: ${url}`);
}

// CLI entry point: `tsx src/smoke-test.ts public/data`
if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith("smoke-test.ts")) {
    const localDir = process.argv[2] ?? "public/data";
    const cdn =
        process.env.CDN_BASE_URL ??
        "https://chertixd.github.io/lol-draft-helper-cdn/data";
    verifyLiveCdn(cdn, localDir).catch((err) => {
        console.error(`[smoke-test] FAIL: ${err.message}`);
        process.exit(1);
    });
}
