import i18n from "../i18n";

// Relative by default → same-origin, served through the Vite dev proxy (see vite.config.ts), which avoids
// CORS. Override with VITE_API_BASE_URL (e.g. an absolute URL) when the backend is reachable directly.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export type ValidationDetail = { loc: (string | number)[]; msg: string; type: string };

export class ApiError extends Error {
  status: number;
  detail: string | ValidationDetail[];
  /** Stable machine string on domain errors (400/404/409), e.g. "student_not_found". Undefined for 422. */
  code?: string;

  constructor(status: number, detail: string | ValidationDetail[], code?: string) {
    super(ApiError.describe(detail));
    this.status = status;
    this.detail = detail;
    this.code = code;
  }

  /**
   * Human-readable text for either `detail` shape the backend uses: an already-localized string
   * for domain errors, or a 422 array flattened to "field: message".
   *
   * Computed here and handed to `super` rather than exposed as a getter. `Error`'s constructor
   * assigns `message` as an *own* property on the instance, and an own data property shadows a
   * prototype getter — so a `get message()` on the subclass is never called, and every validation
   * error read back as the literal "Validation error".
   */
  private static describe(detail: string | ValidationDetail[]): string {
    if (typeof detail === "string") return detail;
    return detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ");
  }
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
};

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  // Second arg is the base for a relative BASE_URL (e.g. "/api/v1"); it's ignored when BASE_URL is absolute.
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  return url.toString();
}

export async function apiRequest<T>(
  path: string,
  { method = "GET", body, query }: RequestOptions = {},
): Promise<T> {
  const res = await fetch(buildUrl(path, query), {
    method,
    headers: {
      "Accept-Language": i18n.language,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new ApiError(res.status, payload?.detail ?? res.statusText, payload?.code);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/**
 * Trigger a file download (e.g. a PDF export). The API is open and sets `Content-Disposition:
 * attachment`, so a plain anchor would also work — this fetch→blob path lets us surface errors.
 * Content-type agnostic: whatever bytes the endpoint returns are saved under `filename`.
 */
export async function downloadFile(path: string, filename: string, query?: RequestOptions["query"]) {
  // `lang` drives the localized export (headers + status column) the backend renders.
  const res = await fetch(buildUrl(path, { lang: i18n.language, ...query }));

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new ApiError(res.status, payload?.detail ?? res.statusText, payload?.code);
  }

  const blob = await res.blob();
  const a = Object.assign(document.createElement("a"), {
    href: URL.createObjectURL(blob),
    download: filename,
  });
  a.click();
  URL.revokeObjectURL(a.href);
}
