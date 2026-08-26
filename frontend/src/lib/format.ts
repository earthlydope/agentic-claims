export const eur = (v: number | null | undefined, dp = 2) =>
  new Intl.NumberFormat('de-AT', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  }).format(Number(v ?? 0))

export const num = (v: number | null | undefined, dp = 0) =>
  new Intl.NumberFormat('en-GB', {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  }).format(Number(v ?? 0))

export const pct = (v: number | null | undefined, dp = 1) =>
  `${(Number(v ?? 0) * 100).toFixed(dp)}%`

export const ms = (v: number | null | undefined) => {
  const value = Number(v ?? 0)
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`
}

export const shortHash = (h: string | null | undefined, n = 10) =>
  h ? `${h.slice(0, n)}…` : '—'

export const when = (iso: string | null | undefined) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

export const ago = (iso: string | null | undefined) => {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`
  return `${Math.floor(diff / 86400)} d ago`
}

export const titleise = (s: string | null | undefined) =>
  (s ?? '').replace(/[_.]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const PRODUCT_LABEL: Record<string, string> = {
  Vollkasko: 'Comprehensive',
  Teilkasko: 'Partial cover',
  Haftpflicht: 'Liability only',
}
