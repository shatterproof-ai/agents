export function applyFilters<T>(
  items: T[],
  predicates: Array<(item: T) => boolean>,
): T[] {
  return items.filter((item) => predicates.every((p) => p(item)))
}

export function groupBy<T, K extends string>(
  items: T[],
  key: (item: T) => K,
): Record<K, T[]> {
  const result = {} as Record<K, T[]>
  for (const item of items) {
    const k = key(item)
    if (!result[k]) result[k] = []
    result[k].push(item)
  }
  return result
}
