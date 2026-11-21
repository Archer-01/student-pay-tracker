import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as endpoints from "../api/endpoints";
import { reportOffline, resetConnectivity } from "./connectivity";
import { lastWarmup, shouldWarm, warmOfflineData, WARM_EVERY_MS } from "./offlineWarmup";

const NOW = new Date("2026-11-21T10:00:00");
const student = (id: number) => ({ id });

beforeEach(() => {
  vi.spyOn(endpoints, "getDashboardSummary").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "listStudents").mockImplementation(async (params = {}) =>
    (params.status === "inactive" ? [student(9)] : params.class_id ? [] : [student(1), student(2)]) as never,
  );
  vi.spyOn(endpoints, "listClasses").mockResolvedValue([{ id: 5 }] as never);
  vi.spyOn(endpoints, "getClass").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "getStudent").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "getLedger").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "listPeriods").mockResolvedValue([] as never);
  vi.spyOn(endpoints, "getMonthlyReport").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "getAnnualReport").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "getSchoolShare").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "listLeaversWithDebt").mockResolvedValue({} as never);
  vi.spyOn(endpoints, "listPacks").mockResolvedValue([] as never);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  resetConnectivity();
});

describe("warmOfflineData", () => {
  it("asks for every screen's data exactly as the screens do, so their stored copies match", async () => {
    await warmOfflineData(NOW);
    // Accueil, Élèves (current and former), Réglages lists.
    expect(endpoints.getDashboardSummary).toHaveBeenCalledWith({ limit: 100 });
    expect(endpoints.listStudents).toHaveBeenCalledWith({ status: "active" });
    expect(endpoints.listStudents).toHaveBeenCalledWith({ status: "inactive" });
    expect(endpoints.listClasses).toHaveBeenCalledWith();
    expect(endpoints.listPacks).toHaveBeenCalledWith();
    // Every student's page, current and former.
    for (const id of [1, 2, 9]) {
      expect(endpoints.getStudent).toHaveBeenCalledWith(id);
      expect(endpoints.getLedger).toHaveBeenCalledWith(id);
      expect(endpoints.listPeriods).toHaveBeenCalledWith(id);
    }
    // Every class page.
    expect(endpoints.getClass).toHaveBeenCalledWith(5);
    expect(endpoints.listStudents).toHaveBeenCalledWith({ class_id: 5 });
    // Bilan: each month of the school year so far, both calendar years, École, Partis.
    const months = vi.mocked(endpoints.getMonthlyReport).mock.calls;
    expect(months).toEqual([[2026, 9], [2026, 10], [2026, 11]]);
    expect(endpoints.getAnnualReport).toHaveBeenCalledWith(2026);
    expect(endpoints.getAnnualReport).toHaveBeenCalledWith(2027);
    expect(endpoints.getSchoolShare).toHaveBeenCalled();
    expect(endpoints.listLeaversWithDebt).toHaveBeenCalled();
  });

  it("keeps going when one request fails, and says how many screens it stored", async () => {
    vi.mocked(endpoints.getLedger).mockRejectedValueOnce(new Error("network"));
    const stored = await warmOfflineData(NOW);
    expect(endpoints.getStudent).toHaveBeenCalledWith(2);
    expect(stored).toBeGreaterThan(0);
    expect(lastWarmup()).toEqual({ at: NOW.toISOString(), stored });
  });
});

describe("shouldWarm", () => {
  const withWorker = { hasWorker: true, visible: true };

  it("waits for the app's offline helper, which only production builds have", () => {
    expect(shouldWarm(NOW, { ...withWorker, hasWorker: false })).toBe(false);
    expect(shouldWarm(NOW, withWorker)).toBe(true);
  });

  it("doesn't run while offline or with the app in the background", () => {
    expect(shouldWarm(NOW, { ...withWorker, visible: false })).toBe(false);
    reportOffline();
    expect(shouldWarm(NOW, withWorker)).toBe(false);
  });

  it("runs again only once the stored copy is a quarter of an hour old", async () => {
    await warmOfflineData(NOW);
    const soon = new Date(NOW.getTime() + WARM_EVERY_MS - 1000);
    const later = new Date(NOW.getTime() + WARM_EVERY_MS + 1000);
    expect(shouldWarm(soon, withWorker)).toBe(false);
    expect(shouldWarm(later, withWorker)).toBe(true);
  });
});
