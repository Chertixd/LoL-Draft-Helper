import stringify from "safe-stable-stringify";

/**
 * Serialize a value to canonical JSON bytes — byte-identical to Python's
 * json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8").
 *
 * This is the SINGLE invariant that protects every installed Tauri client.
 * Drift here means sha256 mismatch in the __meta envelope, which causes
 * json_repo.py to refuse to load CDN data. See the design spec
 * (docs/superpowers/specs/2026-05-03-etl-supabase-removal-design.md) for
 * the full failure-mode analysis.
 */
export function canonicalStringify(value: unknown): Uint8Array {
    // safe-stable-stringify default: sorted keys, no whitespace, undefined keys dropped.
    // Matches Python's sort_keys=True, separators=(",",":") behaviour for
    // primitives and containers. See tests for edge cases (floats, unicode,
    // integer-keyed objects).
    const text = stringify(value, undefined, undefined);
    if (text === undefined) {
        // Python json.dumps raises on unserializable types; we mirror that.
        throw new TypeError(
            `canonicalStringify: value is not JSON-serializable: ${String(value)}`
        );
    }
    return new TextEncoder().encode(text);
}
