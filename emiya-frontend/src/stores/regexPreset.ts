import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchRegexPresets, fetchRegexPresetDetail, createRegexPreset,
  updateRegexPreset, deleteRegexPreset, importRegexPreset,
} from '../api/regexPreset'
import type { RegexPresetInfo } from '../types'

// ADR-0015：activeScripts / loadActiveScripts 已删除——前端不再做渲染层正则。
// reply 正则现在由后端 message_pipeline 统一处理，DB 里的 message.content 即最终版本。
export const useRegexStore = defineStore('regexPreset', () => {
  const list = ref<RegexPresetInfo[]>([])
  const loading = ref(false)

  async function loadList() {
    loading.value = true
    try {
      list.value = await fetchRegexPresets()
    } finally {
      loading.value = false
    }
  }

  return {
    list, loading,
    loadList,
    fetchRegexPresetDetail, createRegexPreset, updateRegexPreset,
    deleteRegexPreset, importRegexPreset,
  }
})
