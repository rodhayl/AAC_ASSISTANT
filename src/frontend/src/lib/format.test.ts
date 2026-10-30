import { describe, it, expect } from 'vitest'
import { formatDate, formatDateTime, formatTime, formatNumber } from './format'
import '../i18n/index'
import i18n from '../i18n/index'

describe('format utilities', () => {
  it('formats date/time in es-ES', () => {
    i18n.changeLanguage('es')
    const d = new Date('2025-01-02T15:30:00Z')
    expect(formatDate(d)).toBeTypeOf('string')
    expect(formatDateTime(d)).toBeTypeOf('string')
    expect(formatTime(d)).toBeTypeOf('string')
  })
  it('formats numbers by locale', () => {
    i18n.changeLanguage('es')
    expect(formatNumber(1234.56)).toBeTypeOf('string')
  })
})
