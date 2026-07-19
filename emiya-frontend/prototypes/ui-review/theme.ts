import { ref, type InjectionKey, type Ref } from 'vue'

export type PrototypeTheme = 'night' | 'day'

export type PrototypeThemeContext = {
  theme: Ref<PrototypeTheme>
  customCss: Ref<string>
  toggleTheme: () => void
}

export const prototypeThemeKey: InjectionKey<PrototypeThemeContext> = Symbol('prototype-theme')

export function createPrototypeTheme(): PrototypeThemeContext {
  const theme = ref<PrototypeTheme>('night')
  const customCss = ref('')
  return {
    theme,
    customCss,
    toggleTheme: () => { theme.value = theme.value === 'night' ? 'day' : 'night' },
  }
}
