import i18n from '../i18n/index'

export const getLocale = () => i18n.language || 'es'

export const formatDate = (d: Date | string | number, opts?: Intl.DateTimeFormatOptions) => {
  const date = d instanceof Date ? d : new Date(d)
  return new Intl.DateTimeFormat(getLocale(), opts || { year: 'numeric', month: 'long', day: 'numeric' }).format(date)
}

export const formatDateTime = (d: Date | string | number, opts?: Intl.DateTimeFormatOptions) => {
  const date = d instanceof Date ? d : new Date(d)
  return new Intl.DateTimeFormat(getLocale(), opts || { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date)
}

export const formatTime = (d: Date | string | number, opts?: Intl.DateTimeFormatOptions) => {
  const date = d instanceof Date ? d : new Date(d)
  return new Intl.DateTimeFormat(getLocale(), opts || { hour: '2-digit', minute: '2-digit' }).format(date)
}

export const formatNumber = (n: number, opts?: Intl.NumberFormatOptions) => {
  return new Intl.NumberFormat(getLocale(), opts).format(n)
}
