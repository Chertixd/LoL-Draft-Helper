import stringify from "safe-stable-stringify";

/**
 * Serialize a value to canonical JSON bytes — byte-identical to Python's
 * json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
 * with default ensure_ascii=True.
 *
 * Critical invariant: drift here means sha256 mismatch in the __meta envelope,
 * which breaks every installed Tauri client. See the design spec for the full
 * failure-mode analysis.
 *
 * Behavioural notes vs Python:
 *  - Whole-number floats (1.0) become "1" in JS and "1.0" in Python. Our
 *    upstream data uses Math.round in lolalytics/index.ts so floats never
 *    survive the pipeline; nothing to handle.
 *  - NaN, Infinity, -Infinity throw here (Python raises in json.dumps too).
 *  - Non-ASCII characters are escaped as \uXXXX (Python default
 *    ensure_ascii=True). Surrogate pairs emit both halves.
 */
export function canonicalStringify(value: unknown): Uint8Array {
    rejectNonFinite(value);
    const text = stringify(value, undefined, undefined);
    if (text === undefined) {
        throw new TypeError(
            `canonicalStringify: value is not JSON-serializable: ${String(value)}`
        );
    }
    return new TextEncoder().encode(escapeNonAscii(text));
}

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

/**
 * Escape every character with code point >= 0x80 to \uXXXX form.
 * Matches Python's json.dumps default ensure_ascii=True behaviour.
 *
 * For surrogate pairs (code points >= 0x10000), JavaScript stores both halves
 * in the string already (UTF-16 representation), and we emit both as \uXXXX.
 * Python does the same — it iterates UTF-16 code units, not code points.
 */
function escapeNonAscii(text: string): string {
    let out = "";
    for (let i = 0; i < text.length; i++) {
        const cu = text.charCodeAt(i);
        if (cu < 0x80) {
            out += text[i];
        } else {
            out += "\\u" + cu.toString(16).padStart(4, "0");
        }
    }
    return out;
}
