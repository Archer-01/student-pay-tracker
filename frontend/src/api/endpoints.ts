import { apiRequest } from "./client";
import type {
  DashboardSummary,
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
  StudentUpdate,
} from "./types";

export function listStudents(
  params: { status?: "active" | "inactive"; sort?: "drift_desc"; as_of?: string } = {},
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
