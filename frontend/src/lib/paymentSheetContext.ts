import { createContext, useContext } from "react";

export type PaymentSheetValue = {
  /** Open the payment sheet, for one student or (without an id) starting from a student picker. */
  open: (studentId?: number) => void;
  /**
   * Bumped after every recorded payment. Screens that show money put it in their `useApi` deps so
   * they refresh by themselves, wherever the sheet was opened from.
   */
  version: number;
};

export const PaymentSheetContext = createContext<PaymentSheetValue | null>(null);

/**
 * Just the refresh counter, without requiring the provider: lets a screen that shows money stay
 * current while still rendering on its own (in tests, say) where there is no sheet.
 */
export function usePaymentsVersion(): number {
  return useContext(PaymentSheetContext)?.version ?? 0;
}

export function usePaymentSheet(): PaymentSheetValue {
  const ctx = useContext(PaymentSheetContext);
  if (!ctx) throw new Error("usePaymentSheet must be used within a PaymentSheetProvider");
  return ctx;
}
