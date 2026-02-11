interface PerformanceMetrics {
  fcp?: number
  lcp?: number
  cls?: number
  fid?: number
  ttfb?: number
  memoryUsage?: {
    usedJSHeapSize: number
    totalJSHeapSize: number
    jsHeapSizeLimit: number
  }
}

interface BenchmarkResult {
  name: string
  duration: number
  timestamp: number
}

interface PerformanceEntryWithStartTime extends PerformanceEntry {
  startTime: number
}

interface LayoutShiftEntry extends PerformanceEntry {
  hadRecentInput: boolean
  value: number
}

interface FirstInputEntry extends PerformanceEntry {
  processingStart: number
  startTime: number
}

interface NavigationEntry extends PerformanceEntry {
  responseStart: number
  requestStart: number
}

interface PerformanceMemory {
  usedJSHeapSize: number
  totalJSHeapSize: number
  jsHeapSizeLimit: number
}

const perfMetrics: PerformanceMetrics = {}
const benchmarks: BenchmarkResult[] = []
const PERF_BUDGET = {
  lcp: 2500, // relax budget to reduce noisy warnings
  cls: 0.1,
  fid: 100,
  memoryLimit: 100 * 1024 * 1024,
}

const SHOULD_WARN =
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.PROD) ||
  (typeof import.meta !== 'undefined' &&
    import.meta.env &&
    import.meta.env.VITE_PERF_WARN === 'true')

const SHOULD_LOG =
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.PROD) ||
  (typeof import.meta !== 'undefined' &&
    import.meta.env &&
    import.meta.env.VITE_PERF_LOG === 'true')

let lcpWarned = false
let clsWarned = false
let fidWarned = false

export function initPerfMetrics() {
  try {
    if ('PerformanceObserver' in window) {
      const paintObserver = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'paint' && entry.name === 'first-contentful-paint') {
            perfMetrics.fcp = Math.round(entry.startTime)
            // console.log('[Perf] FCP:', perfMetrics.fcp, 'ms')
          }
        }
      })
      paintObserver.observe({ type: 'paint', buffered: true })

      const lcpObserver = new PerformanceObserver((entryList) => {
        const entries = entryList.getEntries()
        const last = entries[entries.length - 1] as PerformanceEntryWithStartTime | undefined
        if (last) {
          perfMetrics.lcp = Math.round(last.startTime)
          if (SHOULD_WARN && perfMetrics.lcp > PERF_BUDGET.lcp && !lcpWarned) {
            lcpWarned = true
            console.warn(`[Perf] LCP exceeds budget: ${perfMetrics.lcp}ms > ${PERF_BUDGET.lcp}ms`)
          }
        }
      })
      lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true })

      let clsValue = 0
      const clsObserver = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries() as LayoutShiftEntry[]) {
          if (!entry.hadRecentInput) {
            clsValue += entry.value
            perfMetrics.cls = clsValue
          }
        }
        if (clsValue > 0) {
          if (SHOULD_WARN && clsValue > PERF_BUDGET.cls && !clsWarned) {
            clsWarned = true
            console.warn(`[Perf] CLS exceeds budget: ${clsValue.toFixed(4)} > ${PERF_BUDGET.cls}`)
          }
        }
      })
      clsObserver.observe({ type: 'layout-shift', buffered: true })

      const fidObserver = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries() as FirstInputEntry[]) {
          perfMetrics.fid = Math.round(entry.processingStart - entry.startTime)
          if (SHOULD_WARN && perfMetrics.fid > PERF_BUDGET.fid && !fidWarned) {
            fidWarned = true
            console.warn(`[Perf] FID exceeds budget: ${perfMetrics.fid}ms > ${PERF_BUDGET.fid}ms`)
          }
        }
      })
      fidObserver.observe({ type: 'first-input', buffered: true })

      const navigationEntry = performance.getEntriesByType('navigation')[0] as NavigationEntry | undefined
      if (navigationEntry) {
        perfMetrics.ttfb = Math.round(navigationEntry.responseStart - navigationEntry.requestStart)
        if (SHOULD_LOG) {
          console.log('[Perf] TTFB:', perfMetrics.ttfb, 'ms')
        }
      }
    }

    const perfWithMemory = performance as Performance & { memory?: PerformanceMemory }
    if (perfWithMemory.memory) {
      monitorMemory()
      setInterval(monitorMemory, 30000)
    }
  } catch (err) {
    console.error('[Perf] Failed to initialize metrics:', err)
  }
}

function monitorMemory() {
  const perfWithMemory = performance as Performance & { memory?: PerformanceMemory }
  const memory = perfWithMemory.memory
  if (memory) {
    perfMetrics.memoryUsage = {
      usedJSHeapSize: memory.usedJSHeapSize,
      totalJSHeapSize: memory.totalJSHeapSize,
      jsHeapSizeLimit: memory.jsHeapSizeLimit,
    }
    const usedMB = (memory.usedJSHeapSize / 1024 / 1024).toFixed(2)
    const totalMB = (memory.totalJSHeapSize / 1024 / 1024).toFixed(2)
    if (SHOULD_LOG) {
      console.log(`[Perf] Memory: ${usedMB}MB / ${totalMB}MB`)
    }
    if (SHOULD_WARN && memory.usedJSHeapSize > PERF_BUDGET.memoryLimit) {
      console.warn(`[Perf] Memory usage high: ${usedMB}MB`)
    }
  }
}

export function benchmark(name: string, fn: () => void) {
  const start = performance.now()
  fn()
  const duration = performance.now() - start
  const result: BenchmarkResult = { name, duration, timestamp: Date.now() }
  benchmarks.push(result)
  if (SHOULD_LOG) {
    console.log(`[Benchmark] ${name}: ${duration.toFixed(2)}ms`)
  }
  return duration
}

export async function benchmarkAsync(name: string, fn: () => Promise<void>) {
  const start = performance.now()
  await fn()
  const duration = performance.now() - start
  const result: BenchmarkResult = { name, duration, timestamp: Date.now() }
  benchmarks.push(result)
  if (SHOULD_LOG) {
    console.log(`[Benchmark] ${name}: ${duration.toFixed(2)}ms`)
  }
  return duration
}

export function getMetrics(): PerformanceMetrics {
  return { ...perfMetrics }
}

export function getBenchmarks(): BenchmarkResult[] {
  return [...benchmarks]
}

export function generatePerfReport(): string {
  const metrics = getMetrics()
  const bench = getBenchmarks()

  let report = '=== Performance Report ===\n\n'
  report += 'Core Web Vitals:\n'
  report += `  FCP: ${metrics.fcp ?? 'N/A'}ms\n`
  report += `  LCP: ${metrics.lcp ?? 'N/A'}ms ${metrics.lcp && metrics.lcp > PERF_BUDGET.lcp ? '⚠️ EXCEEDS BUDGET' : '✓'}\n`
  report += `  CLS: ${metrics.cls?.toFixed(4) ?? 'N/A'} ${metrics.cls && metrics.cls > PERF_BUDGET.cls ? '⚠️ EXCEEDS BUDGET' : '✓'}\n`
  report += `  FID: ${metrics.fid ?? 'N/A'}ms ${metrics.fid && metrics.fid > PERF_BUDGET.fid ? '⚠️ EXCEEDS BUDGET' : '✓'}\n`
  report += `  TTFB: ${metrics.ttfb ?? 'N/A'}ms\n\n`

  if (metrics.memoryUsage) {
    const usedMB = (metrics.memoryUsage.usedJSHeapSize / 1024 / 1024).toFixed(2)
    const totalMB = (metrics.memoryUsage.totalJSHeapSize / 1024 / 1024).toFixed(2)
    const limitMB = (metrics.memoryUsage.jsHeapSizeLimit / 1024 / 1024).toFixed(2)
    report += `Memory Usage:\n`
    report += `  Used: ${usedMB}MB / ${totalMB}MB (Limit: ${limitMB}MB)\n\n`
  }

  if (bench.length > 0) {
    report += 'Benchmarks:\n'
    bench.forEach(b => {
      report += `  ${b.name}: ${b.duration.toFixed(2)}ms\n`
    })
  }

  return report
}

if (import.meta.env.DEV && typeof window !== 'undefined') {
  const w = window as Window & { __perfMetrics?: typeof getMetrics; __perfReport?: typeof generatePerfReport; __perfBenchmarks?: typeof getBenchmarks }
  w.__perfMetrics = getMetrics
  w.__perfReport = generatePerfReport
  w.__perfBenchmarks = getBenchmarks
}
