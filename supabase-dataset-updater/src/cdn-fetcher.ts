import { createHash } from "node:crypto";
import { canonicalStringify } from "./canonical-stringify";

/**
 * Fetch the previous patch's per-patch files from the live CDN.
 *
 * Returns:
 *  - Map<filename, Buffer> on success (one entry per per-patch table)
 *  - null on 404 (no previous patch yet — first run or aged out)
 *
 * Throws on:
 *  - sha256 mismatch (CDN content is corrupted; never publish on top of it)
 *  - unexpected HTTP status (non-200, non-404 — server error etc.)
 */
export async function fetchPreviousPatchFiles(
    cdnBaseUrl: string,
    previousPatch: string
): Promise<Map<string, Buffer> | null> {
    const filenames = [
        `matchups_${previousPatch}.json`,
        `synergies_${previousPatch}.json`,
    ];

    const out = new Map<string, Buffer>();
    for (const filename of filenames) {
        const url = `${cdnBaseUrl.replace(/\/$/, "")}/${filename}`;
        const resp = await fetch(url);

        if (resp.status === 404) {
            // First file 404 → previous patch doesn't exist on CDN.
            // Soft-fail: caller proceeds with current patch only.
            return null;
        }
        if (!resp.ok) {
            throw new Error(
                `cdn-fetcher: unexpected status ${resp.status} fetching ${url}`
            );
        }

        const buf = Buffer.from(await resp.arrayBuffer());
        if (!verifyEnvelopeIntegrity(buf)) {
            throw new Error(
                `cdn-fetcher: sha256 mismatch in ${filename} from ${cdnBaseUrl}`
            );
        }
        out.set(filename, buf);
    }
    return out;
}

/**
 * Re-compute sha256 over the rows in a serialized envelope and compare
 * against __meta.sha256. Returns true iff the envelope is intact.
 *
 * Used by cdn-fetcher (validate previous-patch files before reuse) and
 * by self-check (validate freshly written outputs before push).
 */
export function verifyEnvelopeIntegrity(buf: Buffer): boolean {
    let parsed: unknown;
    try {
        parsed = JSON.parse(buf.toString("utf-8"));
    } catch {
        return false;
    }
    if (
        typeof parsed !== "object" ||
        parsed === null ||
        !("__meta" in parsed) ||
        !("rows" in parsed)
    ) {
        return false;
    }
    const meta = (parsed as { __meta: { sha256?: string } }).__meta;
    const rows = (parsed as { rows: unknown[] }).rows;
    if (typeof meta.sha256 !== "string") return false;

    const computed = createHash("sha256")
        .update(canonicalStringify(rows))
        .digest("hex");
    return computed === meta.sha256;
}
