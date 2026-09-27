import { apiRequest, downloadFile } from "./client";
import type {
  UserOut,
  LoginRequest,
  ClassCreate,
  ClassDetailOut,
  ClassLevel,
  ClassListItem,
  ClassOut,
  ClassUpdate,
  AnnualReport,
  DashboardSummary,
  DebtStatus,
  EnrollmentPeriod,
  Leavers,
  ReturnResult,
  LedgerOut,
  MonthlyReport,
  OverrideCreate,
  OverrideOut,
  PaymentCreate,
  PaymentOut,
  StudentCreate,
  StudentDetailOut,
  StudentListItem,
  StudentOut,
  OfferingCreate,
  OfferingUpdate,
  PackCreate,
  PackDetail,
  PackGrid,
  PackUpdate,
  StudentUpdate,
} from "./types";

export function listStudents(
  params: {
    status?: "active" | "inactive";
    sort?: "drift_desc";
    /** Restrict to one class. Omit for every student, assigned or not. */
    class_id?: number;
    /** Free-text search, matched against either name part. */
    q?: string;
    as_of?: string;
  } = {},
) {
  return apiRequest<StudentListItem[]>("/students", { query: params });
}

export function getStudent(id: number, as_of?: string) {
  return apiRequest<StudentDetailOut>(`/students/${id}`, { query: { as_of } });
}

export function getLedger(id: number, as_of?: string) {
  return apiRequest<LedgerOut>(`/students/${id}/ledger`, { query: { as_of } });
}

export function createStudent(body: StudentCreate) {
  return apiRequest<StudentOut>("/students", { method: "POST", body });
}

export function updateStudent(id: number, body: StudentUpdate) {
  return apiRequest<StudentOut>(`/students/${id}`, { method: "PATCH", body });
}

export function recordPayment(studentId: number, body: PaymentCreate) {
  return apiRequest<PaymentOut>(`/students/${studentId}/payments`, { method: "POST", body });
}

export function createOverride(studentId: number, body: OverrideCreate) {
  return apiRequest<OverrideOut>(`/students/${studentId}/overrides`, { method: "POST", body });
}

export function getDashboardSummary(params: { as_of?: string; limit?: number } = {}) {
  return apiRequest<DashboardSummary>("/dashboard/summary", { query: params });
}

export function getMonthlyReport(year: number, month: number) {
  return apiRequest<MonthlyReport>("/reports/monthly", { query: { year, month } });
}

/** What came in over a year, month by month. Every month is present, including empty ones. */
export function getAnnualReport(year: number) {
  return apiRequest<AnnualReport>("/reports/annual", { query: { year } });
}

// --- classes ---------------------------------------------------------------

export function listClasses(params: { level?: ClassLevel; as_of?: string } = {}) {
  return apiRequest<ClassListItem[]>("/classes", { query: params });
}

export function getClass(id: number, as_of?: string) {
  return apiRequest<ClassDetailOut>(`/classes/${id}`, { query: { as_of } });
}

export function createClass(body: ClassCreate) {
  return apiRequest<ClassOut>("/classes", { method: "POST", body });
}

export function updateClass(id: number, body: ClassUpdate) {
  return apiRequest<ClassOut>(`/classes/${id}`, { method: "PATCH", body });
}

export function deleteClass(id: number) {
  return apiRequest<void>(`/classes/${id}`, { method: "DELETE" });
}

/** The class roster as a PDF, localized server-side via the `lang` the client attaches. */
export function downloadClassRoster(id: number, filename: string, as_of?: string) {
  return downloadFile(`/classes/${id}/roster.pdf`, filename, { as_of });
}

// --- packs -----------------------------------------------------------------

export function listPacks(params: { level?: ClassLevel; active?: boolean } = {}) {
  return apiRequest<PackDetail[]>("/packs", { query: params });
}

/** The offerings x levels price matrix. A cell with a null `pack_id` is simply not offered. */
export function getPackGrid() {
  return apiRequest<PackGrid>("/packs/grid");
}

export function createPack(body: PackCreate) {
  return apiRequest<PackDetail>("/packs", { method: "POST", body });
}

/** Create a whole grid row: one pack per priced level, sharing one subject set. */
export function createOffering(body: OfferingCreate) {
  return apiRequest<PackDetail[]>("/packs/offerings", { method: "POST", body });
}

/** Rename an offering and/or set its subjects — applied to every level-variant at once. */
export function updateOffering(name: string, body: OfferingUpdate) {
  return apiRequest<PackDetail[]>(`/packs/offerings/${encodeURIComponent(name)}`, {
    method: "PATCH",
    body,
  });
}

/** Edit one grid cell (its price, or whether it is offered). */
export function updatePack(id: number, body: PackUpdate) {
  return apiRequest<PackDetail>(`/packs/${id}`, { method: "PATCH", body });
}

export function deletePack(id: number) {
  return apiRequest<void>(`/packs/${id}`, { method: "DELETE" });
}

// --- enrollment periods (leave / return) -----------------------------------

export function listPeriods(studentId: number) {
  return apiRequest<EnrollmentPeriod[]>(`/students/${studentId}/periods`);
}

/** Record a departure. Months after it stop being owed; drift already accrued is untouched. */
export function recordLeave(studentId: number, body: { leave_date: string; reason?: string }) {
  return apiRequest<EnrollmentPeriod>(`/students/${studentId}/leave`, { method: "POST", body });
}

/** Record a return. Never blocked by an outstanding balance — that call is the teacher's. */
export function recordReturn(studentId: number, body: { entry_date: string }) {
  // Never refused, even when they owe — the response carries what they left owing instead.
  return apiRequest<ReturnResult>(`/students/${studentId}/return`, { method: "POST", body });
}

// --- debts -----------------------------------------------------------------

export function listLeaversWithDebt() {
  return apiRequest<Leavers>("/debts");
}

export function getDebtStatus(studentId: number) {
  return apiRequest<DebtStatus>(`/debts/${studentId}`);
}

export function writeOffDebt(studentId: number, body: { reason: string }) {
  return apiRequest<{ id: number; amount: string; reason: string }>(
    `/debts/${studentId}/write-off`,
    { method: "POST", body },
  );
}

/** Past leavers who still owe and match this phone or name. Advisory — never a block. */
export function findSimilarLeavers(params: {
  phone?: string;
  first_name?: string;
  last_name?: string;
}) {
  return apiRequest<DebtStatus[]>("/debts/matches", { query: params });
}

// --- auth ------------------------------------------------------------------ //
// The session lives in an HttpOnly cookie, so none of these return or accept a token: the
// browser attaches it (see `credentials: "include"` in client.ts) and JS never sees it.

export function login(body: LoginRequest) {
  return apiRequest<UserOut>("/auth/login", { method: "POST", body });
}

export function logout() {
  return apiRequest<void>("/auth/logout", { method: "POST" });
}

/** Who am I? 401s when signed out — that is how the app decides to show the login page. */
export function getCurrentUser() {
  return apiRequest<UserOut>("/auth/me");
}
