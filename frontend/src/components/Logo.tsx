/**
 * The Ardoise mark: five chalk tally marks on a school slate in a wooden frame. "Ardoise" is the
 * slate a pupil writes on, and keeping count is what the app is for. The same drawing as
 * `public/favicon.svg` and the PNG icons there; change them together.
 *
 * Decorative wherever it sits beside the name, which is the text a screen reader needs.
 */
export function Logo({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" className={`shrink-0 ${className}`}>
      <rect width="64" height="64" rx="15" fill="#b98252" />
      <rect x="6" y="6" width="52" height="52" rx="9" fill="#1f4e4a" />
      <g stroke="#f3f6f5" strokeWidth="4.4" strokeLinecap="round" fill="none">
        <path d="M21.5 20.5 L21.2 43.5" />
        <path d="M28 20 L28 44" />
        <path d="M34.5 20.5 L34.8 43.5" />
        <path d="M41 20.8 L40.7 43.4" />
        <path d="M16.5 40 L47.5 24.5" />
      </g>
    </svg>
  );
}
