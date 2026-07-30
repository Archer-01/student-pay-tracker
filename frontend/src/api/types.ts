import type { components } from "./schema";

export type StudentOut = components["schemas"]["StudentOut"];
/** List rows carry `cumulative_drift` on top of the base StudentOut fields. */
export type StudentListItem = components["schemas"]["StudentListItemOut"];
export type StudentDetailOut = components["schemas"]["StudentDetailOut"];
export type StudentCreate = components["schemas"]["StudentCreate"];
export type StudentUpdate = components["schemas"]["StudentUpdate"];
export type LedgerOut = components["schemas"]["LedgerOut"];
export type LedgerEntry = components["schemas"]["LedgerEntryOut"];
export type PaymentCreate = components["schemas"]["PaymentCreate"];
export type PaymentOut = components["schemas"]["PaymentOut"];
export type OverrideCreate = components["schemas"]["OverrideCreate"];
export type OverrideOut = components["schemas"]["OverrideOut"];
export type DashboardSummary = components["schemas"]["DashboardSummaryOut"];
export type MonthlyReport = components["schemas"]["MonthlyReportOut"];
