import i18n from '../i18n/index'

const DEFAULT_DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
}
const DEFAULT_DATETIME_OPTIONS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
}
const DEFAULT_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  hour: '2-digit',
  minute: '2-digit',
}

export const getLocale = () => i18n.language || 'es'

function format(
  value: Date | string | number,
  options: Intl.DateTimeFormatOptions,
): string {
  const date = value instanceof Date ? value : new Date(value)
  return new Intl.DateTimeFormat(getLocale(), options).format(date)
}

export const formatDate = (
  value: Date | string | number,
  options = DEFAULT_DATE_OPTIONS,
) => format(value, options)

export const formatDateTime = (
  value: Date | string | number,
  options = DEFAULT_DATETIME_OPTIONS,
) => format(value, options)

export const formatTime = (
  value: Date | string | number,
  options = DEFAULT_TIME_OPTIONS,
) => format(value, options)
