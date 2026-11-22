import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as endpoints from "./endpoints";
// The generated file as text, through Vite: the `paths` interface lists every route and method.
import schema from "./schema.d.ts?raw";

/**
 * Every endpoint function against the backend's own list of routes, read from the generated
 * `schema.d.ts`: the method and the path it sends must be one the server serves. The types alone
 * don't catch a typo in a template string, and a wrong path only shows up at runtime, as a 404
 * on one screen. The queries the offline copy depends on are pinned too: a stored answer is found
 * by its exact address (see `lib/offlineWarmup.ts`).
 */

type Call = { method: string; url: URL; body: unknown };

/** "/api/v1/students/{student_id}" → its methods, from the generated `paths` interface. */
function backendRoutes(): { pattern: RegExp; template: string; methods: Set<string> }[] {
  const pathsBlock = schema.slice(schema.indexOf("export interface paths"), schema.indexOf("export type webhooks"));
  return pathsBlock.split(/\n {4}"(?=\/api\/)/).slice(1).map((block) => {
    const template = block.slice(0, block.indexOf('"'));
    const methods = new Set([...block.matchAll(/^ {8}(get|put|post|delete|patch): operations/gm)].map((m) => m[1].toUpperCase()));
    const pattern = new RegExp(`^${template.replace(/\{[^}]+\}/g, "[^/]+")}$`);
    return { pattern, template, methods };
  });
}

let calls: Call[] = [];

beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init: RequestInit = {}) => {
      calls.push({
        method: init.method ?? "GET",
        url: new URL(input),
        body: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
      });
      return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
  // downloadFile hands the blob to a synthetic link, which jsdom can't follow.
  Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

/** One call per exported function, with plausible arguments. */
const everyEndpoint: Record<keyof typeof endpoints, () => Promise<unknown>> = {
  listStudents: () => endpoints.listStudents({ status: "active", class_id: 3, q: "sa" }),
  getStudent: () => endpoints.getStudent(1, "2026-11-01"),
  getLedger: () => endpoints.getLedger(1),
  createStudent: () => endpoints.createStudent({} as never),
  updateStudent: () => endpoints.updateStudent(1, {} as never),
  recordPayment: () => endpoints.recordPayment(1, {} as never),
  updatePayment: () => endpoints.updatePayment(1, 4, { amount: "300.00" }),
  deletePayment: () => endpoints.deletePayment(1, 4),
  createOverride: () => endpoints.createOverride(1, {} as never),
  getDashboardSummary: () => endpoints.getDashboardSummary({ limit: 100 }),
  getMonthlyReport: () => endpoints.getMonthlyReport(2026, 11),
  getSchoolShare: () => endpoints.getSchoolShare(),
  markShareHandedOver: () => endpoints.markShareHandedOver(2026, 10, "2026-11-03"),
  unmarkShareHandedOver: () => endpoints.unmarkShareHandedOver(2026, 10),
  handOverAllShare: () => endpoints.handOverAllShare("2026-11-20"),
  getAnnualReport: () => endpoints.getAnnualReport(2026),
  downloadMonthlyReportPdf: () => endpoints.downloadMonthlyReportPdf(2026, 11, "mois.pdf"),
  downloadAnnualReportPdf: () => endpoints.downloadAnnualReportPdf(2026, "annee.pdf"),
  downloadLedgerPdf: () => endpoints.downloadLedgerPdf(1, "eleve.pdf"),
  listClasses: () => endpoints.listClasses(),
  getClass: () => endpoints.getClass(2),
  createClass: () => endpoints.createClass({} as never),
  updateClass: () => endpoints.updateClass(2, {} as never),
  deleteClass: () => endpoints.deleteClass(2),
  downloadClassRoster: () => endpoints.downloadClassRoster(2, "classe.pdf"),
  listPacks: () => endpoints.listPacks(),
  createPack: () => endpoints.createPack({} as never),
  updatePack: () => endpoints.updatePack(5, {} as never),
  deletePack: () => endpoints.deletePack(5),
  listPeriods: () => endpoints.listPeriods(1),
  recordLeave: () => endpoints.recordLeave(1, { leave_date: "2026-11-01" }),
  recordReturn: () => endpoints.recordReturn(1, { entry_date: "2026-11-02" }),
  listLeaversWithDebt: () => endpoints.listLeaversWithDebt(),
  writeOffDebt: () => endpoints.writeOffDebt(1, { reason: "parti" }),
  findSimilarLeavers: () => endpoints.findSimilarLeavers({ phone: "0612345678" }),
  login: () => endpoints.login({ username: "aymen", password: "pw" }),
  logout: () => endpoints.logout(),
  getCurrentUser: () => endpoints.getCurrentUser(),
};

describe("endpoints", () => {
  const routes = backendRoutes();

  it("found the backend's routes in schema.d.ts", () => {
    expect(routes.length).toBeGreaterThan(20);
  });

  it.each(Object.entries(everyEndpoint))("%s asks for a route the backend serves", async (_name, call) => {
    await call();
    expect(calls).toHaveLength(1);
    const { method, url } = calls[0];
    const route = routes.find((r) => r.pattern.test(url.pathname));
    expect(route, `${method} ${url.pathname} is not a backend route`).toBeDefined();
    expect([...route!.methods]).toContain(method);
  });

  it("sends the queries the screens and the offline copy rely on", async () => {
    await endpoints.listStudents({ status: "inactive" });
    await endpoints.getDashboardSummary({ limit: 100 });
    await endpoints.getMonthlyReport(2026, 9);
    await endpoints.getStudent(1);
    const [students, dashboard, monthly, student] = calls.map((c) => c.url);
    expect(students.search).toBe("?status=inactive");
    expect(dashboard.search).toBe("?limit=100");
    expect(monthly.search).toBe("?year=2026&month=9");
    // An omitted as_of leaves no trace, or "today" would be stored under a second address.
    expect(student.search).toBe("");
  });

  it("sends a payment correction's fields, and a handover's date, as the body", async () => {
    await endpoints.updatePayment(1, 4, { amount: "199.50" });
    await endpoints.markShareHandedOver(2026, 10, "2026-11-03");
    expect(calls[0].body).toEqual({ amount: "199.50" });
    expect(calls[1].body).toEqual({ handed_on: "2026-11-03" });
  });
});
