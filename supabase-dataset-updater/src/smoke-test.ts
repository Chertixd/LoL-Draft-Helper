import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

interface SmokeOptions {
    retries: number; // additional attempts after the first; 9 by default = up to 5 min
    sleepMs: number; // delay between attempts; 30_000 in prod
}

/**
 * Verify each local .json file's __meta.sha256 matches what the live CDN
 * serves at the same filename. Retries on 404 OR sha256-mismatch to absorb
 * GitHub Pages edge propagation lag (Pages edge cache TTL can be several
 * minutes — a 200 with stale content is just as transient as a 404).
 *
 * Safety Layer 3: this runs after peaceiris/actions-gh-pages succeeds. If
 * it throws, the workflow fails — but the CDN is already in a broken state
 * by then. The point of this layer is fast detection, not prevention.
 */
export async function verifyLiveCdn(
    cdnBaseUrl: string,
    localDir: string,
    opts: SmokeOptions = { retries: 9, sleepMs: 30_000 }
): Promise<void> {
    const files = readdirSync(localDir).filter((f) => f.endsWith(".json"));
    for (const filename of files) {
        const localBuf = readFileSync(join(localDir, filename));
        const localSha = JSON.parse(localBuf.toString("utf-8")).__meta?.sha256;
        if (typeof localSha !== "string") {
            throw new Error(`smoke-test: local ${filename} has no __meta.sha256`);
        }

        const url = `${cdnBaseUrl.replace(/\/$/, "")}/${filename}`;
        await fetchUntilMatchOrFail(url, localSha, opts);
    }
    console.log(
        `[smoke-test] verified ${files.length} files against ${cdnBaseUrl}`
    );
}

/**
 * Fetch the URL repeatedly until the response's __meta.sha256 matches the
 * expected value. Retries on:
 *  - 404 (edge cache propagation lag — file not visible yet)
 *  - 200 with sha mismatch (edge cache serving stale content from before push)
 *
 * Hard-fails on:
 *  - any other HTTP status (5xx, etc.)
 *  - 200 but parse error or missing __meta
 */
async function fetchUntilMatchOrFail(
    url: string,
    expectedSha: string,
    opts: SmokeOptions
): Promise<void> {
    const totalAttempts = opts.retries + 1;
    let lastReason = "no attempts made";

    for (let attempt = 1; attempt <= totalAttempts; attempt++) {
        const resp = await fetch(url);

        if (resp.status === 404) {
            lastReason = "404 (edge cache propagation lag)";
        } else if (!resp.ok) {
            throw new Error(
                `smoke-test: unexpected status ${resp.status} fetching ${url}`
            );
        } else {
            const text = await resp.text();
            const liveSha = JSON.parse(text).__meta?.sha256;
            if (typeof liveSha !== "string") {
                throw new Error(`smoke-test: live ${url} has no __meta.sha256`);
            }
            if (liveSha === expectedSha) {
                return;
            }
            lastReason = `sha256 mismatch (expected=${expectedSha.slice(0, 8)}..., live=${liveSha.slice(0, 8)}...) — edge cache lag`;
        }

        if (attempt < totalAttempts) {
            await new Promise((r) => setTimeout(r, opts.sleepMs));
        }
    }

    throw new Error(
        `smoke-test: ${lastReason} after ${totalAttempts} attempts: ${url}`
    );
}

// CLI entry point: `tsx src/smoke-test.ts public/data`
if (process.argv[1]?.endsWith("smoke-test.ts") || process.argv[1]?.endsWith("smoke-test.js")) {
    const localDir = process.argv[2] ?? "public/data";
    const cdn =
        process.env.CDN_BASE_URL ??
        "https://chertixd.github.io/lol-draft-helper-cdn/data";
    verifyLiveCdn(cdn, localDir).catch((err) => {
        console.error(`[smoke-test] FAIL: ${err.message}`);
        process.exit(1);
    });
}
