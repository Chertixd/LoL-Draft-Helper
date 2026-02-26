<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
    websocketConnected: boolean;
    leagueClientConnected: boolean;
}>();

// Backend ist erreichbar wenn WebSocket verbunden ist
const backendReachable = computed(() => props.websocketConnected);

// Gesamtstatus
const overallStatus = computed(() => {
    if (!props.websocketConnected) return 'disconnected';
    if (props.leagueClientConnected) return 'ready';
    return 'waiting';
});

const statusMessage = computed(() => {
    switch (overallStatus.value) {
        case 'disconnected':
            return 'Backend nicht erreichbar. Bitte starte das Backend.';
        case 'waiting':
            return 'Warte auf League Client... Starte LoL oder gehe in Champion Select.';
        case 'ready':
            return 'Bereit! Warte auf Champion Select oder Draft läuft...';
        default:
            return '';
    }
});
</script>

<template>
    <div :class="['connection-status', overallStatus]">
        <div class="status-indicators">
            <div :class="['status-item', { connected: websocketConnected }]">
                <span class="status-indicator"></span>
                <div class="status-info">
                    <strong>Backend</strong>
                    <span class="status-text">
                        {{ websocketConnected ? 'Verbunden' : 'Offline' }}
                    </span>
                </div>
            </div>
            
            <div :class="['status-item', { connected: leagueClientConnected, waiting: websocketConnected && !leagueClientConnected }]">
                <span class="status-indicator"></span>
                <div class="status-info">
                    <strong>League Client</strong>
                    <span class="status-text">
                        {{ leagueClientConnected ? 'Verbunden' : (websocketConnected ? 'Warte...' : 'Offline') }}
                    </span>
                </div>
            </div>
        </div>
        
        <p :class="['status-message', overallStatus]">
            <span v-if="overallStatus === 'disconnected'" class="message-icon">⚠️</span>
            <span v-else-if="overallStatus === 'waiting'" class="message-icon">⏳</span>
            <span v-else class="message-icon">✅</span>
            {{ statusMessage }}
        </p>
    </div>
</template>

<style scoped>
.connection-status {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    border-left: 3px solid var(--border-color);
    transition: border-color var(--transition-fast);
}

.connection-status.ready {
    border-left-color: var(--success);
}

.connection-status.waiting {
    border-left-color: var(--warning);
}

.connection-status.disconnected {
    border-left-color: var(--error);
}

.status-indicators {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
}

.status-item {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.375rem 0.5rem;
    background: var(--bg-primary);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
    transition: border-color var(--transition-fast);
}

.status-item.connected {
    border-color: var(--success);
}

.status-item.waiting {
    border-color: var(--warning);
}

.status-indicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--error);
    transition: background-color var(--transition-fast);
}

.status-item.connected .status-indicator {
    background: var(--success);
}

.status-item.waiting .status-indicator {
    background: var(--warning);
    animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.status-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
}

.status-info strong {
    font-size: 0.75rem;
}

.status-text {
    font-size: 0.65rem;
    color: var(--text-muted);
}

.status-item.connected .status-text {
    color: var(--success);
}

.status-item.waiting .status-text {
    color: var(--warning);
}

.status-message {
    margin: 0;
    font-size: 0.7rem;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 0.375rem;
}

.status-message.ready {
    color: var(--success);
}

.status-message.waiting {
    color: var(--warning);
}

.status-message.disconnected {
    color: var(--error);
}

.message-icon {
    font-size: 0.75rem;
}
</style>
