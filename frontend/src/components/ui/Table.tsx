import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes } from "react";

/** Thin table primitives sharing header/cell styling so roster/ledger/report tables look uniform. */
export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
      <table className="w-full text-[0.95rem] tabular-nums">{children}</table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="border-b border-line text-left text-xs uppercase tracking-wider text-muted">
      {children}
    </thead>
  );
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-line">{children}</tbody>;
}

export function Tr({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <tr className={className}>{children}</tr>;
}

export function Th({ children, className = "", ...rest }: ThHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <th className={`px-4 py-3 font-bold ${className}`} {...rest}>
      {children}
    </th>
  );
}

export function Td({ children, className = "", ...rest }: TdHTMLAttributes<HTMLTableCellElement> & { children?: ReactNode }) {
  return (
    <td className={`px-4 py-3 ${className}`} {...rest}>
      {children}
    </td>
  );
}
