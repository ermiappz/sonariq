// Home: blueprint-style general arrangement line art, the pitch in two lines, one Login button (demo workspace, no auth).
const FAIL = "#ff8a50", WARN = "#e69f00", PASS = "#3cc49a", LINE = "#5d6a80", INK = "#9fb3cf";

function Ship() {
  // deck plan, bow to the right: hull, frames every 10 units, three main vertical zones, two stair cores, cabins
  const hull = "M60 70 L760 70 Q860 74 930 150 Q860 226 760 230 L60 230 Q44 230 44 214 L44 86 Q44 70 60 70 Z";
  const frames = Array.from({ length: 36 }, (_, i) => 70 + i * 20);
  const cabins = Array.from({ length: 30 }, (_, i) => 90 + i * 22);
  return (
    <svg viewBox="0 0 980 320" className="home-ship" role="img" aria-label="Line drawing of a ship deck plan with fire zones and stairs; three elements lit as findings">
      <defs>
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#1d2633" strokeWidth="1" /></pattern>
        <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0V6" stroke={INK} strokeWidth="1" /></pattern>
      </defs>
      <rect width="980" height="320" fill="url(#grid)" />
      <path d={hull} fill="none" stroke={INK} strokeWidth="2" />
      {/* longitudinal corridors */}
      <path d="M60 128H800 M60 172H800" stroke={LINE} strokeDasharray="6 4" />
      <path d="M60 150H880" stroke={LINE} strokeDasharray="14 4 2 4" opacity=".7" />
      {/* cabins port and starboard */}
      {cabins.map((x) => <path key={x} d={`M${x} 70V128 M${x} 172V230`} stroke={LINE} strokeWidth="1" />)}
      {/* main vertical zone bulkheads (A-60) */}
      {[250, 470, 690].map((x, i) => (
        <g key={x}><path d={`M${x} 64V236`} stroke={INK} strokeWidth="3.5" />
          <text x={x - 30} y={56} fill={INK} fontSize="11" fontFamily="IBM Plex Mono, monospace">MVZ {i + 3}|{i + 4}</text></g>
      ))}
      {/* stair cores */}
      <rect x="330" y="132" width="60" height="36" fill="url(#hatch)" stroke={INK} />
      <rect x="560" y="132" width="56" height="36" fill="url(#hatch)" stroke={PASS} strokeWidth="2.5" />
      <text x="560" y="186" fill={PASS} fontSize="11" fontFamily="IBM Plex Mono, monospace">✓ Stair 3B · Pass</text>
      {/* lit findings */}
      <rect x="464" y="96" width="12" height="18" fill="none" stroke={FAIL} strokeWidth="2.5" />
      <text x="482" y="104" fill={FAIL} fontSize="11" fontFamily="IBM Plex Mono, monospace">✕ F-01 door A-0 in A-60</text>
      <rect x="150" y="172" width="70" height="20" fill="none" stroke={WARN} strokeWidth="2.5" strokeDasharray="5 3" />
      <text x="150" y="206" fill={WARN} fontSize="11" fontFamily="IBM Plex Mono, monospace">! corridor 900 / 915 mm</text>
      {/* frame ruler */}
      {frames.map((x, i) => <path key={x} d={`M${x} 262V${i % 5 === 0 ? 272 : 267}`} stroke={LINE} />)}
      {frames.filter((_, i) => i % 5 === 0).map((x, i) => <text key={x} x={x - 8} y={286} fill={LINE} fontSize="10" fontFamily="IBM Plex Mono, monospace">Fr {140 + i * 5}</text>)}
      {/* one dimension line */}
      <path d="M250 300H470 M250 294V306 M470 294V306" stroke="#e9eaed" strokeWidth="1.5" />
      <rect x="320" y="291" width="80" height="18" fill="#0e1218" />
      <text x="327" y="304" fill="#e9eaed" fontSize="11" fontFamily="IBM Plex Mono, monospace">MVZ ≤ 40 m</text>
      <text x="890" y="104" fill={LINE} fontSize="10" fontFamily="IBM Plex Mono, monospace">FWD →</text>
    </svg>
  );
}

function Team() {
  // four engineers as flat silhouettes around a drawing table; no faces, no photos
  const people = [[60, "#5c9dff"], [130, "#e27dff"], [200, "#3fd0e6"], [270, "#b98cff"]] as const;
  return (
    <svg viewBox="0 -50 330 200" className="home-team" role="img" aria-label="Illustration: four engineers around a drawing table">
      {people.map(([x, c], i) => (
        <g key={i} transform={`translate(${x} ${i % 2 ? 18 : 10})`}>
          <path d="M-14 -38 a14 14 0 0 1 28 0 v2 h-28z" fill={c} opacity=".9" />{/* hard hat */}
          <circle cx="0" cy="-26" r="12" fill="#2d3036" />
          <path d="M-26 30 Q-26 -6 0 -8 Q26 -6 26 30z" fill="#2d3036" />
          <path d="M-8 -6 L0 6 L8 -6" fill="none" stroke={c} strokeWidth="2" />
        </g>
      ))}
      <path d="M10 112 L320 112 L300 140 L30 140 Z" fill="#1b2230" stroke={INK} />
      <path d="M60 120 H200 M60 128 H160 M220 118 l30 0 l0 16 l-30 0z" stroke={LINE} fill="none" />
    </svg>
  );
}

export default function Home({ onLogin }: { onLogin: () => void }) {
  return (
    <div className="sq sq-dark home">
      <header className="home-top">
        <b style={{ fontSize: 18 }}>SonarIQ</b>
        <span style={{ flex: 1 }} />
        <a className="home-link" href="downloads/">FreeCAD add-on</a>
        <button className="sq-btn is-primary" onClick={onLogin}>Login</button>
      </header>
      <main className="home-main">
        <section className="home-copy">
          <div className="home-kicker mono">Fire &amp; life safety · SOLAS II-2 · FSS Code</div>
          <h1>AI-assisted design review for ship safety</h1>
          <p className="home-sub">Review in the browser. Fix in your CAD tool.</p>
          <p className="sq-muted" style={{ maxWidth: 520 }}>A deterministic rule engine checks the IFC model and decides every verdict. AI explains, cites the clause and drafts fixes; it never sets a status.</p>
          <div className="flex gap-3 items-center" style={{ marginTop: 20 }}>
            <button className="sq-btn is-primary home-cta" onClick={onLogin}>Login</button>
            <span className="sq-faint">Opens the demo workspace · no account needed</span>
          </div>
        </section>
        <Team />
      </main>
      <Ship />
      <footer className="home-foot sq-faint">Data stays on-premises · v0.2 prototype · drawing is illustrative</footer>
    </div>
  );
}
