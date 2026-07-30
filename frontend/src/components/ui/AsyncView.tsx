import type { ReactNode } from "react";
import type { AsyncState } from "../../lib/useApi";
import { LoadingState } from "./LoadingState";
import { ErrorState } from "./ErrorState";
import { EmptyState } from "./EmptyState";

type Props<T> = {
  state: AsyncState<T>;
  /** Called on the success branch to render the data. */
  children: (data: T) => ReactNode;
  /** Optional retry passed to ErrorState (typically `useApi`'s `reload`). */
  onRetry?: () => void;
  /** When provided, decides whether success data should render EmptyState instead. */
  isEmpty?: (data: T) => boolean;
  /** Custom empty message forwarded to EmptyState. */
  emptyMessage?: string;
};

/**
 * Composes the async-state primitives over the `useApi` discriminated union so read screens
 * don't hand-roll loading/error/empty branches. Usage:
 *   <AsyncView state={state} onRetry={state.reload} isEmpty={(d) => d.length === 0}>
 *     {(data) => <Table … />}
 *   </AsyncView>
 */
export function AsyncView<T>({ state, children, onRetry, isEmpty, emptyMessage }: Props<T>) {
  if (state.status === "loading") return <LoadingState />;
  if (state.status === "error") return <ErrorState message={state.error} onRetry={onRetry} />;
  if (isEmpty?.(state.data)) return <EmptyState message={emptyMessage} />;
  return <>{children(state.data)}</>;
}
