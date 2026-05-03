import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        // Tests live in ./tests/, source in ./src/
        include: ["tests/**/*.test.ts"],
        // Long timeout for golden test which reads ~850 fixtures from disk
        testTimeout: 30_000,
        // Suppress noisy console.log from production code paths during tests
        silent: false,
        reporters: ["default"],
    },
});
