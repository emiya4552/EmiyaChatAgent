import { createRouter, createWebHistory } from 'vue-router'
import ImmersiveHomePrototype from '../immersive-home/ImmersiveHomePrototype.vue'
import FunctionalCoveragePrototype from '../shared/FunctionalCoveragePrototype.vue'
import ChatWorkspacePrototype from '../chat-workspace/ChatWorkspacePrototype.vue'
import AccountManagementPrototype from '../account-management/AccountManagementPrototype.vue'

const coverage = (scope: 'conversation' | 'studio' | 'insights' | 'account', initialSurface?: string) => ({
  component: FunctionalCoveragePrototype,
  props: { scope, initialSurface },
})

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: ImmersiveHomePrototype },
    { path: '/chat', component: ChatWorkspacePrototype },
    { path: '/chat/new', component: ChatWorkspacePrototype },
    { path: '/chat/settings', component: ChatWorkspacePrototype },
    { path: '/chat/card-ui', component: ChatWorkspacePrototype },
    { path: '/personas/:pathMatch(.*)*', ...coverage('studio', 'persona') },
    { path: '/worldbooks/:pathMatch(.*)*', ...coverage('studio', 'world') },
    { path: '/presets/:pathMatch(.*)*', ...coverage('studio', 'prompt') },
    { path: '/templates/:pathMatch(.*)*', ...coverage('studio', 'prompt') },
    { path: '/regex-presets/:pathMatch(.*)*', ...coverage('studio', 'regex') },
    { path: '/memories', ...coverage('insights', 'memory') },
    { path: '/mood', ...coverage('insights', 'mood') },
    { path: '/relationships', ...coverage('insights', 'bond') },
    { path: '/settings', component: AccountManagementPrototype },
    { path: '/settings/security', component: AccountManagementPrototype },
    { path: '/login', component: AccountManagementPrototype },
    { path: '/register', component: AccountManagementPrototype },
    { path: '/forgot-password', component: AccountManagementPrototype },
    { path: '/reset-password', component: AccountManagementPrototype },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
