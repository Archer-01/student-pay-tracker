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
/** Moroccan school levels, in school order — shared by classes and (later) pack pricing. */
export type ClassLevel = components["schemas"]["ClassLevel"];
export type ClassOut = components["schemas"]["ClassOut"];
export type ClassBrief = components["schemas"]["ClassBriefOut"];
export type ClassListItem = components["schemas"]["ClassListItemOut"];
export type ClassDetailOut = components["schemas"]["ClassDetailOut"];
export type ClassCreate = components["schemas"]["ClassCreate"];

export type ClassUpdate = components["schemas"]["ClassUpdate"];
export type MonthlyReport = components["schemas"]["MonthlyReportOut"];
export type PackDetail = components["schemas"]["PackDetailOut"];
export type PackGrid = components["schemas"]["PackGridOut"];
export type PackGridRow = components["schemas"]["GridRowOut"];
export type PackGridCell = components["schemas"]["GridCellOut"];
export type PackCreate = components["schemas"]["PackCreate"];
export type PackUpdate = components["schemas"]["PackUpdate"];
export type OfferingCreate = components["schemas"]["OfferingCreate"];
export type OfferingUpdate = components["schemas"]["OfferingUpdate"];
export type PackBrief = components["schemas"]["PackBriefOut"];
export type AnnualReport = components["schemas"]["AnnualReportOut"];
export type EnrollmentPeriod = components["schemas"]["PeriodOut"];
export type DebtStatus = components["schemas"]["DebtStatusOut"];
export type Leavers = components["schemas"]["LeaversOut"];
export type ReturnResult = components["schemas"]["ReturnResultOut"];
