import { useEffect, useState } from 'react'

/**
 * Delays updating a value until the user stops typing.
 * Used on search inputs to avoid firing an API call on every keystroke.
 *
 * Usage:
 *   const debouncedSearch = useDebounce(searchInput, 350)
 *   useEffect(() => { fetchResults(debouncedSearch) }, [debouncedSearch])
 */
export function useDebounce<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
