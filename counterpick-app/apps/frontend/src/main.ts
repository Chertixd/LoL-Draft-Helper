import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { createRouter, createWebHistory } from 'vue-router';
import App from './App.vue';
import './assets/styles.css';

// Router Setup
const router = createRouter({
    history: createWebHistory(),
    routes: [
        {
            path: '/',
            redirect: '/draft'
        },
        {
            path: '/draft',
            name: 'draft-tracker',
            component: () => import('./views/DraftTrackerView.vue')
        },
        {
            path: '/lookup',
            name: 'champion-lookup',
            component: () => import('./views/ChampionLookupView.vue')
        }
    ]
});

// App erstellen
const app = createApp(App);

// Plugins
app.use(createPinia());
app.use(router);

// Mount
app.mount('#app');

