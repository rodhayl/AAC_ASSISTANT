import { describe, it, expect } from 'vitest'
import { formatDate, formatDateTime, formatTime } from '../src/lib/format'
import '../src/i18n/index'
import i18n from '../src/i18n/index'

describe('format utilities', () => {
  it('formats date/time in es-ES', () => {
    i18n.changeLanguage('es')
    const d = new Date('2025-01-02T15:30:00Z')
    expect(formatDate(d)).toBeTypeOf('string')
    expect(formatDateTime(d)).toBeTypeOf('string')
    expect(formatTime(d)).toBeTypeOf('string')
  })
})
