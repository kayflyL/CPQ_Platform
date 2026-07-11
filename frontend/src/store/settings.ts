import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useSettingsStore = defineStore('settings', () => {
  const numberPrecision = ref<number>(2)

  async function loadNumberPrecision() {
    try {
      const resp = await axios.get('/api/rules/number-precision')
      numberPrecision.value = resp.data.precision
    } catch (e) {
      console.error('Failed to load number precision:', e)
    }
  }

  async function setNumberPrecision(precision: number) {
    try {
      await axios.put('/api/rules/number-precision', { precision })
      numberPrecision.value = precision
    } catch (e) {
      console.error('Failed to set number precision:', e)
      throw e
    }
  }

  function formatNumber(value: number | string | null | undefined): string {
    if (value === null || value === undefined || value === '') return ''
    if (typeof value === 'string') {
      const num = parseFloat(value)
      if (isNaN(num)) return value
      return num.toFixed(numberPrecision.value)
    }
    return value.toFixed(numberPrecision.value)
  }

  return {
    numberPrecision,
    loadNumberPrecision,
    setNumberPrecision,
    formatNumber
  }
})
