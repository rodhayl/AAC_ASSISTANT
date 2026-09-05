/**
 * Shared paginated-walk helper.
 *
 * Every roster/board loader walks a paginated endpoint until a page comes
 * back shorter than the requested page size. Without a hard cap, a backend
 * bug that keeps returning full pages would spin requests forever, so the
 * walk throws after `maxPages` fetches; callers surface the error through
 * their existing error state.
 */

export const MAX_PAGE_WALK_PAGES = 200

export interface PageWalkOptions<T> {
  /** Rows requested per page; must match the caller's `limit` param. */
  pageSize: number
  /** Fetch one page. `skip` is 0 for the first call, then the running total. */
  fetchPage: (skip: number) => Promise<T[]>
  /**
   * Optional cancellation check, consulted before every fetch. When it turns
   * true the walk stops immediately and returns what it has; callers must
   * re-check their own request/context guard before publishing, so the
   * partial result is discarded exactly like the previous inline loops.
   */
  isCancelled?: () => boolean
  /** Hard cap on fetches. 200 pages x any supported page size (max 1000) is far beyond any real roster. */
  maxPages?: number
}

/**
 * Fetch pages until one comes back shorter than `pageSize`, returning the
 * accumulated rows. Throws if a page is not an array or if the walk exceeds
 * `maxPages` fetches (a backend that never shrinks its pages).
 */
export async function walkPages<T>({
  pageSize,
  fetchPage,
  isCancelled,
  maxPages = MAX_PAGE_WALK_PAGES,
}: PageWalkOptions<T>): Promise<T[]> {
  const items: T[] = []
  let skip = 0
  let pagesFetched = 0
  while (true) {
    if (isCancelled?.()) return items
    pagesFetched += 1
    if (pagesFetched > maxPages) {
      throw new Error('Pagination did not terminate')
    }
    const page = await fetchPage(skip)
    if (!Array.isArray(page)) {
      throw new Error('Invalid response format: expected array')
    }
    items.push(...page)
    if (page.length < pageSize) return items
    skip += page.length
  }
}
