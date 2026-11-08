// Brand v1 (13-Brand.pdf, logos in design/brand): the Plimsoll Q mark and the SonarIQ wordmark. Same geometry as
// sonariq-logo-on-black/-on-white.svg, without the background square; colours come from --brand-ink / --brand-blue so
// dark surfaces get the on-black colours and light surfaces the on-white ones.
export function Mark({ size = 20, title }: { size?: number; title?: string }) {
  return (
    <svg viewBox="1 6.5 59 53" width={size * 59 / 53} height={size} fill="none" role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true} className="sq-mark">
      <circle cx="29" cy="29" r="19" stroke="var(--brand-ink)" strokeWidth="6" />
      <path stroke="var(--brand-ink)" strokeLinecap="round" strokeWidth="5" d="M4 29h50" />
      <path stroke="var(--brand-blue)" strokeLinecap="round" strokeWidth="6" d="m40 40 16 16" />
    </svg>
  );
}

export function Lockup({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`sq-lockup ${className}`} style={{ fontSize: size * 0.9 }}>
      <Mark size={size} /><span>Sonar<b>IQ</b></span>
    </span>
  );
}
