import { describe, expect, it, vi } from 'vitest'

import { MAX_PAGE_WALK_PAGES, walkPages } from '../src/lib/pagination'

describe('walkPages', () => {
  it('returns an empty list without fetching when the first page is empty', async () => {
    const fetchPage = vi.fn().mockResolvedValue([])
    const result = await walkPages({ pageSize: 3, fetchPage })
    expect(result).toEqual([])
    expect(fetchPage).toHaveBeenCalledTimes(1)
    expect(fetchPage).toHaveBeenCalledWith(0)
  })

  it('stops after a short page without an extra fetch', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce([1, 2, 3])
      .mockResolvedValueOnce([4])
    const result = await walkPages({ pageSize: 3, fetchPage })
    expect(result).toEqual([1, 2, 3, 4])
    expect(fetchPage).toHaveBeenCalledTimes(2)
    expect(fetchPage).toHaveBeenLastCalledWith(3)
  })

  it('throws after maxPages fetches when the endpoint returns full pages forever', async () => {
    const fetchPage = vi.fn().mockResolvedValue([1, 2, 3])
    await expect(
      walkPages({ pageSize: 3, fetchPage, maxPages: 5 }),
    ).rejects.toThrow('Pagination did not terminate')
    // maxPages fetches happen before the guard trips on the next iteration.
    expect(fetchPage).toHaveBeenCalledTimes(5)
  })

  it('uses the default cap of MAX_PAGE_WALK_PAGES fetches', async () => {
    const fetchPage = vi.fn().mockResolvedValue([1])
    await expect(
      walkPages({ pageSize: 1, fetchPage }),
    ).rejects.toThrow('Pagination did not terminate')
    expect(fetchPage).toHaveBeenCalledTimes(MAX_PAGE_WALK_PAGES)
  })

  it('propagates a mid-walk fetch error and keeps earlier pages private', async () => {
    const fetchPage = vi
      .fn()
      .mockResolvedValueOnce([1, 2])
      .mockRejectedValueOnce(new Error('network gone'))
    await expect(
      walkPages({ pageSize: 2, fetchPage }),
    ).rejects.toThrow('network gone')
    expect(fetchPage).toHaveBeenCalledTimes(2)
  })

  it('rejects a page that is not an array', async () => {
    const fetchPage = vi.fn().mockResolvedValue({ items: [1] } as unknown as number[])
    await expect(
      walkPages({ pageSize: 2, fetchPage }),
    ).rejects.toThrow('Invalid response format: expected array')
  })

  it('stops immediately when cancelled and returns the accumulated rows', async () => {
    const fetchPage = vi
      .fn()
      .mockImplementation(async () => {
        // Simulate a concurrent invalidation landing while page 1 is in flight.
        cancelled = true
        return [1, 2]
      })
    let cancelled = false
    const result = await walkPages({
      pageSize: 2,
      fetchPage,
      isCancelled: () => cancelled,
    })
    expect(result).toEqual([1, 2])
    // No further fetch happens after cancellation.
    expect(fetchPage).toHaveBeenCalledTimes(1)
  })
})
