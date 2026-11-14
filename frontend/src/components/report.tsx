import type { ReactNode } from "react";
import { ChevronLeftIcon, ChevronRightIcon } from "./icons";

/**
 * A headline figure: a label over a big number. `alarming` turns the number red. Stacked from the
 * top, so figures side by side line up whether or not each has a hint underneath.
 */
export function Figure({
  label,
  value,
  hint,
  alarming = false,
}: {
  label: string;
  value: string;
  hint?: string;
  alarming?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-line bg-surface p-4">
      <span className="text-sm text-muted">{label}</span>
      <span
        className={`font-display text-2xl font-extrabold tabular-nums tracking-tight sm:text-3xl ${
          alarming ? "text-bad" : "text-ink"
        }`}
      >
        {value}
      </span>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}

/** ‹ label ›: step through months or years with two thumb-sized arrows instead of dropdowns. */
export function Stepper({
  label,
  previousLabel,
  nextLabel,
  onPrevious,
  onNext,
  canGoNext,
}: {
  label: ReactNode;
  previousLabel: string;
  nextLabel: string;
  onPrevious: () => void;
  onNext: () => void;
  canGoNext: boolean;
}) {
  const arrow =
    "flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-brand disabled:opacity-40";
  return (
    <div className="flex items-center justify-between gap-3">
      <button type="button" aria-label={previousLabel} onClick={onPrevious} className={arrow}>
        <ChevronLeftIcon className="h-6 w-6" />
      </button>
      <span className="text-center font-display text-xl font-extrabold tracking-tight">{label}</span>
      <button type="button" aria-label={nextLabel} onClick={onNext} disabled={!canGoNext} className={arrow}>
        <ChevronRightIcon className="h-6 w-6" />
      </button>
    </div>
  );
}

export type Bar = {
  key: string;
  /** Under the bar: a letter or a short month. */
  label: string;
  /** What the bar says to a screen reader and in its tooltip: the month and the amount. */
  title: string;
  /** Height only. Never used for arithmetic on money. */
  value: number;
  selected?: boolean;
};

/**
 * Bars on one scale, the tallest reaching the top. Drawn with plain elements rather than a chart
 * library: a dozen bars don't need one. With `onSelect` each bar is a button, so tapping a month
 * opens it.
 */
export function BarChart({ bars, onSelect }: { bars: Bar[]; onSelect?: (key: string) => void }) {
  const peak = Math.max(...bars.map((b) => b.value), 0);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-32 items-end gap-1 sm:gap-1.5">
        {bars.map((bar) => {
          const height = peak > 0 ? Math.max((bar.value / peak) * 100, bar.value > 0 ? 4 : 2) : 2;
          const fill = (
            <span
              className={`block w-full rounded-t-md ${bar.selected ? "bg-brand" : bar.value > 0 ? "bg-brand-mid" : "bg-line"}`}
              style={{ height: `${height}%` }}
            />
          );
          return onSelect ? (
            <button
              key={bar.key}
              type="button"
              title={bar.title}
              aria-label={bar.title}
              aria-pressed={bar.selected ?? false}
              onClick={() => onSelect(bar.key)}
              className="flex h-full flex-1 items-end rounded-t-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
            >
              {fill}
            </button>
          ) : (
            <span key={bar.key} title={bar.title} className="flex h-full flex-1 items-end">
              {fill}
            </span>
          );
        })}
      </div>
      {/* Twelve "Sept"s and "Janv"s only fit a phone at 11px and a tighter gap; `min-w-0` keeps
          each label to its bar's width, so a long one spills into the gap rather than shifting
          the columns out from under the bars. */}
      <div
        aria-hidden="true"
        className="flex gap-1 whitespace-nowrap text-center text-[11px] text-muted sm:gap-1.5 sm:text-xs sm:font-bold"
      >
        {bars.map((bar) => (
          <span key={bar.key} className={`min-w-0 flex-1 ${bar.selected ? "font-bold text-brand" : ""}`}>
            {bar.label}
          </span>
        ))}
      </div>
    </div>
  );
}
