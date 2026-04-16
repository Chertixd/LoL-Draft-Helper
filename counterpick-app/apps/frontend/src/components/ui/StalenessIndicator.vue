<script setup lang="ts">
/**
 * StalenessIndicator -- small badge showing cached data age (UX-03, UX-04)
 *
 * Colors:
 *  - 'none': not rendered (parent uses v-if)
 *  - 'amber': data > 48h old
 *  - 'red': data > 7 days old
 */

defineProps<{
    severity: 'none' | 'amber' | 'red'
    lastFetchDate: string | null
}>()
</script>

<template>
    <span
        v-if="severity !== 'none'"
        :class="['staleness-indicator', `staleness-${severity}`]"
    >
        <span class="staleness-dot"></span>
        <span v-if="severity === 'amber'">Data may be outdated (&gt; 48h old)</span>
        <span v-else-if="severity === 'red'">Data is outdated (&gt; 7 days old)</span>
        <span v-if="lastFetchDate" class="staleness-date"> -- {{ lastFetchDate }}</span>
    </span>
</template>

<style scoped>
.staleness-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.7rem;
    padding: 0.2rem 0.5rem;
    border-radius: var(--radius-sm);
}

.staleness-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
}

.staleness-amber {
    color: var(--warning);
}

.staleness-amber .staleness-dot {
    background: var(--warning);
}

.staleness-red {
    color: var(--error);
    font-weight: 600;
}

.staleness-red .staleness-dot {
    background: var(--error);
}

.staleness-date {
    color: var(--text-muted);
}
</style>
