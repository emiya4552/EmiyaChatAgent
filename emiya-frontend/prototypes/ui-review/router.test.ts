// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import App from './App.vue'
import router from './router'

describe('UI review navigation', () => {
  it('keeps the asset navigation visible after the chat regex entry routes to /regex-presets', async () => {
    await router.push('/regex-presets')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await nextTick()

    expect(wrapper.get('[data-testid="studio-top-nav"]').text()).toContain('正则')
    expect(wrapper.get('[data-testid="studio-top-nav"] a.active').text()).toBe('正则')
    expect(wrapper.get('.review-nav a.active').text()).toBe('创作资产')
    wrapper.unmount()
  })

  it('switches the shared prototype theme between night and day', async () => {
    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.get('.theme-root').attributes('data-theme')).toBe('night')
    await wrapper.get('.theme-toggle').trigger('click')
    expect(wrapper.get('.theme-root').attributes('data-theme')).toBe('day')
    wrapper.unmount()
  })

  it('visibly switches the home prototype to its day treatment', async () => {
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })

    await wrapper.get('.theme-toggle').trigger('click')
    expect(document.head.querySelector('#prototype-custom-theme')?.textContent).toContain(".theme-root[data-theme='day'] .workspace")
    wrapper.unmount()
  })

  it('applies account custom CSS to the shared review surface', async () => {
    await router.push('/settings')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })

    await router.push('/settings?tab=display')
    await nextTick()
    const textarea = wrapper.get('.css-theme textarea')
    await textarea.setValue('.workspace { --accent: #8da9d4; }')
    await nextTick()

    expect(document.head.querySelector('#prototype-custom-theme')?.textContent).toContain('--accent: #8da9d4')
    wrapper.unmount()
  })

  it('keeps new-chat and conversation-settings modals mutually exclusive', async () => {
    await router.push('/chat/new')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.find('.modal.create').exists()).toBe(true)
    expect(wrapper.find('.modal.config').exists()).toBe(false)

    await router.push('/chat/settings')
    await nextTick()
    expect(wrapper.find('.modal.create').exists()).toBe(false)
    expect(wrapper.find('.modal.config').exists()).toBe(true)
    wrapper.unmount()
  })
})
