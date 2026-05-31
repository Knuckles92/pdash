/**
 * Small immutable helpers for lists of `{ id }` records held in client state.
 * Used by the settings clients and the approvals/activity views.
 */

/** Build a `Map` keyed by each item's `id` (last write wins on duplicates). */
export function indexById<T extends { id: string }>(items: T[]): Map<string, T> {
  return new Map(items.map((item) => [item.id, item]));
}

/**
 * Return a new list with `item` inserted, or replacing the existing entry that
 * shares its `id`. Order is preserved; a new item is appended.
 */
export function upsertById<T extends { id: string }>(list: T[], item: T): T[] {
  const index = list.findIndex((existing) => existing.id === item.id);
  if (index === -1) return [...list, item];
  const next = list.slice();
  next[index] = item;
  return next;
}
