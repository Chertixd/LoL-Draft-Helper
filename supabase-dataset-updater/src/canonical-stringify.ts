import stringify from "safe-stable-stringify";

/**
 * Serialize a value to canonical JSON bytes — byte-identical to Python's
 * json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8").
 *
 * Critical invariant: drift here means sha256 mismatch in the __meta envelope,
 * which breaks every installed Tauri client. See the design spec for the full
 * failure-mode analysis.
 *
 * Behavioural notes vs Python:
 *  - Whole-number floats (1.0) become "1" in JS and "1.0" in Python. Our
 *    upstream data uses Math.round in lolalytics/index.ts so floats never
 *    survive the pipeline; nothing to handle.
 *  - NaN, Infinity, -Infinity throw here (Python raises in json.dumps too,
 *    unless allow_nan=True which we do not use).
 */
export function canonicalStringify(value: unknown): Uint8Array {
    rejectNonFinite(value);
    const text = stringify(value, undefined, undefined);
    if (text === undefined) {
        throw new TypeError(
            `canonicalStringify: value is not JSON-serializable: ${String(value)}`
        );
    }
    return new TextEncoder().encode(text);
}

/**
 * Walk the value graph and throw if any number is non-finite.
 * Cheaper than post-processing the JSON text and impossible to fool.
 */
function rejectNonFinite(value: unknown): void {
    if (typeof value === "number") {
        if (!Number.isFinite(value)) {
            throw new TypeError(
                `canonicalStringify: value is not JSON-serializable: ${value}`
            );
        }
        return;
    }
    if (value === null || typeof value !== "object") return;
    if (Array.isArray(value)) {
        for (const item of value) rejectNonFinite(item);
        return;
    }
    for (const v of Object.values(value as Record<string, unknown>)) {
        rejectNonFinite(v);
    }
}
