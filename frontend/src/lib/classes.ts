import type { ClassBrief, ClassLevel } from "../api/types";

/**
 * School order, not alphabetical — "1BAC" sorts before "2AC" as a string, which is wrong.
 * Mirrors the backend's `ClassLevel` declaration order; the API already returns classes sorted,
 * so this exists for the level *filter* and for any client-side grouping.
 */
export const CLASS_LEVELS: ClassLevel[] = ["1AC", "2AC", "3AC", "TC", "1BAC", "2BAC"];

/** "2BAC — Groupe A". The level is not part of the name, so it's composed for display. */
export function classLabel(schoolClass: Pick<ClassBrief, "level" | "name">): string {
  return `${schoolClass.level} — ${schoolClass.name}`;
}
