import { createHash } from "node:crypto";
import { canonicalStringify } from "./canonical-stringify";

export const SCHEMA_VERSION = 1;

export interface EnvelopeMeta {
    exported_at: string; // ISO-8601 with "Z" suffix
    sha256: string; // 64-char lowercase hex over canonical rows only
    row_count: number;
    schema_version: number;
    source_table: string;
    source_patch?: string; // only set for per-patch tables
}

export interface EnvelopedTable {
    __meta: EnvelopeMeta;
    rows: unknown[];
}

/**
 * Wrap a list of rows with the canonical __meta envelope.
 *
 * Mirrors export_to_json.py:export_table / export_table_per_patch exactly:
 *  - exported_at: now in UTC, ISO-8601, "Z" suffix (replaces "+00:00")
 *  - sha256: lowercase hex over canonicalStringify(rows) only
 *  - row_count, schema_version, source_table, optional source_patch
 *
 * The sha256 deliberately excludes __meta itself so the same rows produce
 * the same hash regardless of timestamp — this lets the client verify
 * integrity without re-deriving exported_at.
 */
export function wrapWithEnvelope(
    table: string,
    rows: unknown[],
    exportedAt: Date,
    sourcePatch?: string
): EnvelopedTable {
    const sha256 = createHash("sha256")
        .update(canonicalStringify(rows))
        .digest("hex");

    const meta: EnvelopeMeta = {
        exported_at: exportedAt.toISOString().replace(/\.\d{3}Z$/, "Z"),
        sha256,
        row_count: rows.length,
        schema_version: SCHEMA_VERSION,
        source_table: table,
    };

    if (sourcePatch !== undefined) {
        meta.source_patch = sourcePatch;
    }

    return { __meta: meta, rows };
}

/**
 * Serialize an enveloped table to UTF-8 JSON bytes ready to write to disk.
 *
 * Uses canonicalStringify to keep the on-disk form deterministic — important
 * for self-check.ts which re-reads the file and recomputes sha256.
 *
 * Note: the on-disk format is canonical JSON over the WHOLE envelope (__meta
 * + rows), but the embedded sha256 is over rows only. self-check.ts knows to
 * re-stringify only `rows`.
 */
export function serializeEnvelope(env: EnvelopedTable): Uint8Array {
    return canonicalStringify(env);
}
