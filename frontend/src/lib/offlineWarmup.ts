import * as api from "../api/endpoints";
import { connectivity } from "./connectivity";
import { WARMUP_STORAGE_KEY } from "./offlineData";
import { schoolYearStart } from "./schoolYear";

/**
 * Every screen readable offline, not only the ones opened lately.
 *
 * While the app is online, this quietly asks for the data behind every screen: Accueil, each
 * student's page (current and former), each class, Bilan's months of the school year so far,
 * the year, École, Partis sans régler, the packs. The service worker stores each answer as it
 * passes (see `sw/service-worker.js`), so later, without a signal, any screen opens with the last
 * figures the server gave.
 *
 * It calls the same functions with the same arguments as the screens do, because the stored copy
 * is found by its exact address: a different query string would store a copy nobody reads. The
 * figures stay the server's; nothing here recomputes what is owed or how late.
 */

/** How old the stored copy may get before another round, while the app is open and online. */
export const WARM_EVERY_MS = 15 * 60 * 1000;
/** Requests in flight at once: gentle on a weak signal and on the server. */
const AT_ONCE = 3;
/** Fired on `window` after each round, so Réglages can say when the copy was made. */
export const WARMED_EVENT = "ardoise:offline-warmed";

export type Warmup = { at: string; stored: number };

export function lastWarmup(): Warmup | null {
  try {
    const raw = localStorage.getItem(WARMUP_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Warmup) : null;
  } catch {
    return null;
  }
}

/**
 * Whether to start a round now: only with the service worker in charge (production builds; it's
 * what keeps the copies), only online and with the app on screen, and only once the last round
 * is a quarter of an hour old.
 */
export function shouldWarm(now: Date, env: { hasWorker: boolean; visible: boolean }): boolean {
  if (!env.hasWorker || !env.visible || connectivity().mode !== "live") return false;
  const last = lastWarmup();
  return !last || now.getTime() - new Date(last.at).getTime() >= WARM_EVERY_MS;
}

let running: Promise<number> | null = null;

/** One round. Returns how many answers were stored; a failed request is skipped, never fatal. */
export function warmOfflineData(now = new Date()): Promise<number> {
  running ??= run(now).finally(() => {
    running = null;
  });
  return running;
}

async function run(now: Date): Promise<number> {
  let stored = 0;
  const attempt = async (load: () => Promise<unknown>): Promise<unknown> => {
    try {
      const value = await load();
      stored += 1;
      return value;
    } catch {
      return null;
    }
  };

  // The lists first: they name the students and classes whose pages come next.
  const [current, former, classes] = await Promise.all([
    attempt(() => api.listStudents({ status: "active" })),
    attempt(() => api.listStudents({ status: "inactive" })),
    attempt(() => api.listClasses()),
  ]);
  const studentIds = [...asIds(current), ...asIds(former)];
  const classIds = asIds(classes);

  const today = isoDay(now);
  const schoolYear = schoolYearStart(today);
  const tasks: (() => Promise<unknown>)[] = [
    () => api.getDashboardSummary({ limit: 100 }),
    () => api.getSchoolShare(),
    () => api.listLeaversWithDebt(),
    () => api.listPacks(),
    // Bilan › Mois shows the school year's two calendar years; Bilan › Année opens on this one.
    () => api.getAnnualReport(schoolYear),
    () => api.getAnnualReport(schoolYear + 1),
    ...monthsSoFar(schoolYear, now).map(([y, m]) => () => api.getMonthlyReport(y, m)),
    ...studentIds.flatMap((id) => [
      () => api.getStudent(id),
      () => api.getLedger(id),
      () => api.listPeriods(id),
    ]),
    ...classIds.flatMap((id) => [() => api.getClass(id), () => api.listStudents({ class_id: id })]),
  ];

  let next = 0;
  const worker = async () => {
    while (next < tasks.length) {
      const task = tasks[next++]!;
      await attempt(task);
    }
  };
  await Promise.all(Array.from({ length: AT_ONCE }, worker));

  const result: Warmup = { at: now.toISOString(), stored };
  try {
    localStorage.setItem(WARMUP_STORAGE_KEY, JSON.stringify(result));
  } catch {
    // Private browsing or storage blocked: the copies are still stored, only the time isn't.
  }
  window.dispatchEvent(new Event(WARMED_EVENT));
  return stored;
}

function asIds(rows: unknown): number[] {
  return Array.isArray(rows) ? rows.map((row: { id: number }) => row.id) : [];
}

/** September of the school year up to this month, as [year, month] pairs. */
function monthsSoFar(schoolYear: number, now: Date): [number, number][] {
  const months: [number, number][] = [];
  for (let i = 0; i < 12; i++) {
    const year = i < 4 ? schoolYear : schoolYear + 1;
    const month = ((8 + i) % 12) + 1;
    if (year > now.getFullYear() || (year === now.getFullYear() && month > now.getMonth() + 1)) break;
    months.push([year, month]);
  }
  return months;
}

function isoDay(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
