// Home (design/screens/14-Homepage.pdf, brand 13-Brand.pdf). SVG/CSS only. One "Login" button enters the demo
// workspace (Inbox, no auth); the hero's "Open live demo" does the same. Numbers are the engine's: 96 checks per Rev B
// run, F-07 1,380 required / 1,350 measured, fix 2 gives 1,340; the OR-117 edit re-runs 7 checks and changes 2.
// Links we don't have yet stay null and render as "link follows" instead of a fake URL.
import { useEffect, useRef, type ReactNode } from "react";
import { Lockup, Mark } from "../components/Brand";

const LINKS: { github: string | null; video: string | null; deck: string | null; sinceai: string | null; docs: string | null } = {
  github: null, video: null, deck: null, sinceai: null, docs: null,
};
const HOST = "34-88-130-224.sslip.io";

const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });

// Subtle motion: sections and cards fade up as they scroll into view (opacity/transform only, no layout shift).
// Without JS or with prefers-reduced-motion everything is simply visible.
function useReveal() {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = root.current;
    if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) return;
    el.querySelectorAll(".hp-reveal-kids > *").forEach((n, i, all) => {
      const k = Array.prototype.indexOf.call(n.parentElement!.children, n);
      n.classList.add("hp-reveal"); (n as HTMLElement).style.setProperty("--d", `${(k % 4) * 90}ms`); void all; void i;
    });
    el.classList.add("hp-js");
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); } }),
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    el.querySelectorAll(".hp-reveal").forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, []);
  return root;
}
const d = (i: number) => ({ ["--d" as any]: `${i * 90}ms` });

export default function Home({ onLogin }: { onLogin: () => void }) {
  const root = useReveal();
  return (
    <div className="sq sq-dark hp" ref={root}>
      <header className="hp-nav">
        <div className="hp-wrap hp-nav-in">
          <a href="#" onClick={(e) => { e.preventDefault(); scrollTo("top"); }} aria-label="SonarIQ"><Lockup size={20} /></a>
          <nav className="hp-links">
            <button onClick={() => scrollTo("how")}>How it works</button>
            <button onClick={() => scrollTo("evidence")}>Evidence</button>
            <button onClick={() => scrollTo("hackathon")}>Hackathon</button>
            <button onClick={() => scrollTo("resources")}>Resources</button>
          </nav>
          <span style={{ flex: 1 }} />
          {LINKS.github && <a className="hp-navlink hp-hide-sm" href={LINKS.github}>GitHub</a>}
          <a className="hp-navlink hp-hide-sm" href="downloads/">FreeCAD add-on</a>
          <button className="hp-btn is-light" onClick={onLogin}>Login</button>
        </div>
      </header>

      <main id="top">
        {/* ---------------------------------------------------------------- hero */}
        <section className="hp-grid-bg">
          <div className="hp-wrap hp-hero">
            <div className="hp-hero-copy">
              <span className="hp-badge mono">Since AI 2026 · hackathon project</span>
              <div className="hp-kicker mono">Fire &amp; life safety · SOLAS II-2 · FSS Code</div>
              <h1>Ship safety, checked while you <span className="hp-blue">design.</span></h1>
              <p className="hp-lead">SonarIQ finds the fire-safety rule a design change breaks, shows it on the model with the rule’s own numbers, and offers fixes it has already re-checked.</p>
              <div className="hp-ctas">
                <button className="hp-btn is-light is-lg" onClick={onLogin}>Open live demo →</button>
                {LINKS.video
                  ? <a className="hp-btn is-lg" href={LINKS.video}>▶ Watch the 2-min demo</a>
                  : <button className="hp-btn is-lg" onClick={() => scrollTo("video")}>▶ Watch the 2-min demo</button>}
              </div>
              <div className="hp-facts mono"><span>No account needed</span><span>IFC4 in · BCF out</span></div>
              <div className="hp-facts mono"><span>Rule engine decides · AI explains</span></div>
            </div>
            <HeroCard />
          </div>
        </section>

        {/* ---------------------------------------------------------------- standards strip */}
        <section className="hp-strip">
          <div className="hp-wrap">
            <div className="hp-strip-row mono hp-reveal"><b>Checks against</b><span>SOLAS II-2</span><span>FSS Code Ch.13</span><span>PVAG 2013 (draft)</span><span>ADA 2010</span><span>DNV class · to verify</span></div>
            <div className="hp-strip-row mono sq-faint">Works with FreeCAD · IFC4 · BCF</div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- how it works */}
        <section id="how" className="hp-sec">
          <div className="hp-wrap">
            <div className="hp-eyebrow mono hp-reveal">How it works</div>
            <h2 className="hp-reveal" style={d(1)}>One change. Every rule it touches.<br />Seconds later.</h2>
            <p className="hp-p hp-reveal" style={d(2)}>Four cabins added at frame 140 make a stair that serves four decks too narrow. SonarIQ catches it before anyone opens a report.</p>
            <div className="hp-cards3" id="evidence">
              <Step i={1} n="01 · In FreeCAD" title="Analyse where you design" text="A docked panel checks the open IFC model. Findings light up on the 3D model first, then in a list.">
                <MiniPanel />
              </Step>
              <Step i={2} n="02 · Evidence" title="Proof, not a score" text="Every verdict shows the clause, required against measured, and the formula filled with the model’s own inputs.">
                <div className="hp-formula mono">
                  <div>W = (N₁ + N₂ + 0.5 N₃ + 0.25 N₄) × 10</div>
                  <div>&nbsp;&nbsp;= (68 + 44 + 20 + 6) × 10</div>
                  <div>&nbsp;&nbsp;= 1,380 mm required</div>
                  <div className="hp-fail">✕ 1,350 mm measured · −30 mm</div>
                </div>
              </Step>
              <Step i={3} n="03 · Review portal" title="Decide, sign, hand back" text="Discipline leads approve, request changes or decline. Every action is signed. Issues go back to any CAD tool as BCF.">
                <div className="hp-thread">
                  <div><i className="o" />Rule engine found F-07<span className="mono">14:32</span></div>
                  <div><i className="f" />Designer applied fix 2<span className="mono">14:36</span></div>
                  <div><i className="b" />Fire &amp; life safety lead approved<span className="mono">15:06</span></div>
                  <span className="hp-btn is-light is-sm" aria-hidden>Approve · signed</span>
                </div>
              </Step>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- trust */}
        <section className="hp-sec hp-grid-bg">
          <div className="hp-wrap hp-two">
            <div>
              <div className="hp-eyebrow mono hp-reveal">Trust by design</div>
              <h2 className="hp-reveal" style={d(1)}>The engine decides.<br />The engineer decides.<br /><span className="sq-faint">AI explains.</span></h2>
              <p className="hp-p hp-reveal" style={d(2)}>A deterministic rule engine sets every Pass and Fail. AI only explains in plain words, turns typed requests into edits you confirm, and proposes fixes the engine re-checks before you see them. When the model is missing data, SonarIQ says “Cannot verify”. It never guesses.</p>
            </div>
            <div className="hp-trust hp-reveal-kids">
              <div className="hp-card"><span className="hp-tag mono">◘ Rule engine</span><b>Sets every verdict</b><span className="sq-muted">Same input, same answer. Tested rule by rule.</span></div>
              <div className="hp-card"><span className="hp-tag mono">✓ AI explanation · numbers checked</span><b>Never sets a status</b><span className="sq-muted">Uses only numbers the engine produced.</span></div>
              <div className="hp-card hp-span2">
                <div className="hp-pills">
                  <span className="sq-pill s-fail"><i className="sq-ico" />Fail</span>
                  <span className="sq-pill s-warn"><i className="sq-ico" />Warning</span>
                  <span className="sq-pill s-unk"><i className="sq-ico" />Cannot verify</span>
                  <span className="sq-pill s-pass"><i className="sq-ico" />Pass</span>
                  <span className="sq-pill s-acc"><i className="sq-ico" />Accepted with reason</span>
                </div>
                <span className="sq-muted">Every status has an icon and a word. Colour-blind safe, WCAG 2.1 AA.</span>
              </div>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- video */}
        <section id="video" className="hp-sec">
          <div className="hp-wrap" style={{ textAlign: "center" }}>
            <div className="hp-eyebrow mono hp-reveal">Demo video</div>
            <h2 className="hp-reveal" style={{ marginTop: 0, ...d(1) }}>See the golden path in two minutes</h2>
            <div className="hp-video hp-reveal" style={d(2)}>
              <div className="hp-intro" aria-hidden><Mark size={72} /><span className="hp-intro-word">Sonar<b>IQ</b></span></div>
              {LINKS.video
                ? <a className="hp-btn is-light" href={LINKS.video}>▶ Play · 2:00</a>
                : <span className="hp-btn is-light is-static">Video follows with the submission</span>}
              <div className="hp-video-cap mono">Analyse → typed change → ping → fix → review</div>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- hackathon */}
        <section id="hackathon" className="hp-sec hp-grid-bg">
          <div className="hp-wrap hp-two">
            <div>
              <div className="hp-eyebrow mono hp-reveal">Built at Since AI 2026</div>
              <h2 className="hp-reveal" style={d(1)}>A 36-hour prototype for the Meyer Turku challenge</h2>
              <p className="hp-p hp-reveal" style={d(2)}>The challenge: automated class and regulatory compliance checking for cruise ship design. SonarIQ is our answer, a working prototype rather than a product. Rules marked “To verify” have not been checked by a class society.</p>
              <div className="hp-chips"><span>Hackathon project</span><span>Not class approved</span></div>
            </div>
            <div className="hp-stats3 hp-reveal-kids">
              <div className="hp-card"><b className="hp-num mono">36 h</b><span className="sq-muted">from brief to demo</span></div>
              <div className="hp-card"><b className="hp-num mono">96</b><span className="sq-muted">checks in 3 rule packs</span></div>
              <div className="hp-card"><b className="hp-num mono">2</b><span className="sq-muted">ship models: demo ship and RCRV</span></div>
              <div className="hp-card hp-span3 hp-team"><b>Team SonarIQ</b><span style={{ flex: 1 }} /><span className="mono sq-faint">Turku · November 2026</span></div>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- resources */}
        <section id="resources" className="hp-sec">
          <div className="hp-wrap">
            <div className="hp-eyebrow mono hp-reveal">Resources</div>
            <h2 className="hp-reveal" style={d(1)}>Everything we submitted</h2>
            <div className="hp-res hp-reveal-kids">
              <Res k="Live demo" t="Open the demo workspace" d="Portal with the demo ship and RCRV. No account needed." link={HOST} onClick={onLogin} />
              <Res k="FreeCAD" t="FreeCAD add-on" d="The docked panel and the one-line macOS setup." link={`${HOST}/downloads`} href="downloads/" />
              <Res k="Code" t="GitHub repository" d="Rule engine, FreeCAD add-on, portal and tests." href={LINKS.github} />
              <Res k="Video" t="Demo video · 2 min" d="The golden path from Analyse to a signed approval." href={LINKS.video} />
              <Res k="Deck" t="Pitch deck" d="Problem, approach, results and what comes next." href={LINKS.deck} />
              <Res k="Since AI" t="Hackathon submission" d="Our entry for the Meyer Turku challenge." href={LINKS.sinceai} />
              <Res k="Docs" t="Spec and design hand-off" d="Product spec, rulebook and the UI design canvas." href={LINKS.docs} />
            </div>
          </div>
        </section>

        {/* ---------------------------------------------------------------- closing CTA */}
        <section className="hp-sec hp-cta">
          <div className="hp-ring" aria-hidden />
          <h2 className="hp-reveal">Review in the browser.<br />Fix in your CAD tool.</h2>
          <div className="hp-ctas" style={{ justifyContent: "center" }}>
            <button className="hp-btn is-light" onClick={onLogin}>Open live demo →</button>
            <a className="hp-btn" href="downloads/">Get the FreeCAD add-on</a>
            {LINKS.github && <a className="hp-btn" href={LINKS.github}>View on GitHub</a>}
          </div>
        </section>
      </main>

      <footer className="hp-foot">
        <div className="hp-wrap hp-foot-in">
          <Lockup size={14} />
          <span className="sq-faint">Hackathon prototype for Since AI 2026 · not a class-approved tool · design insight only</span>
          <span style={{ flex: 1 }} />
          {LINKS.github && <a href={LINKS.github}>GitHub</a>}
          <button onClick={() => scrollTo("resources")}>Resources</button>
          <button onClick={onLogin}>Demo</button>
        </div>
      </footer>
    </div>
  );
}

function Step({ n, title, text, children, i = 0 }: { n: string; title: string; text: string; children: ReactNode; i?: number }) {
  return <div className="hp-card hp-step hp-reveal" style={d(i)}><span className="hp-eyebrow mono">{n}</span><h3>{title}</h3><p className="sq-muted">{text}</p><div className="hp-step-art">{children}</div></div>;
}

function Res({ k, t, d, link, href, onClick }: { k: string; t: string; d: string; link?: string; href?: string | null; onClick?: () => void }) {
  const tail = <span className="mono hp-res-link">{href || onClick ? `${link ?? href} →` : "link follows with the submission"}</span>;
  const body = <><span className="hp-eyebrow mono">{k}</span><b>{t}</b><span className="sq-muted">{d}</span>{tail}</>;
  if (onClick) return <button className="hp-card hp-res-card" onClick={onClick}>{body}</button>;
  if (href) return <a className="hp-card hp-res-card" href={href}>{body}</a>;
  return <div className="hp-card hp-res-card is-off">{body}</div>;
}

function MiniPanel() {
  return (
    <svg viewBox="0 0 300 120" className="hp-mini" aria-hidden>
      <rect x="0.5" y="0.5" width="299" height="119" fill="#111215" stroke="#2a2d33" />
      <rect x="10" y="10" width="160" height="100" fill="#15171b" stroke="#2a2d33" />
      <circle cx="90" cy="60" r="12" fill="none" stroke="#5c9dff" strokeWidth="1.5" />
      <rect x="84" y="54" width="12" height="12" fill="none" stroke="#ff8a50" strokeWidth="2" />
      {[14, 34, 54, 74].map((y, i) => <rect key={y} x="180" y={y} width="110" height="14" fill={i === 1 ? "#24262b" : "#1b1d21"} />)}
      <rect x="180" y="34" width="3" height="14" fill="#ff8a50" />
    </svg>
  );
}

// Live · Deck 5 · Rev B: the general arrangement around Stair 3B, laid back in perspective. Positions follow the
// engine's locations (frames 140–176, P up): F-08 Fr 146–150 P, F-09 Fr 152 S, F-07 Stair 3B Fr 160–164,
// F-01 Fr 165 P (MVZ 4/5 A-60 bulkhead), U-01 Fr 171 S, OR-117 cabin block from Fr 140.
function HeroCard() {
  const X = (fr: number) => (fr - 138) * 16;
  const frames = Array.from({ length: 39 }, (_, i) => 138 + i);
  const cabins = Array.from({ length: 19 }, (_, i) => 138 + i * 2);
  const tag = (x: number, y: number, txt: string, cls = "f") => (
    <g transform={`translate(${x} ${y})`} className={`hp-iso-tag ${cls}`}>
      <rect x="0" y="-9" width={txt.length * 5.6 + 18} height="13" rx="2" />
      <text x="13" y="0.5">{txt}</text><text x="3.5" y="0.5" className="i">{cls === "u" ? "?" : "✕"}</text>
    </g>
  );
  return (
    <div className="hp-card hp-live" role="img" aria-label="Deck 5, Rev B: four findings on the deck plan; F-07 Stair 3B fails, the fix is re-checked">
      <div className="hp-live-head mono"><i className="hp-dot" />Live · Deck 5 · Rev B</div>
      <div className="hp-callouts">
        <div className="hp-callout mono"><span className="hp-fail">✕ Fail</span> F-07 · Stair 3B<br /><span>required 1,380 mm · measured 1,350 mm</span></div>
        <div className="hp-callout mono"><span className="hp-pass">✓ Fix re-checked</span><br /><span>N₁ 64 → 1,340 ≤ 1,350 mm</span></div>
      </div>
      <div className="hp-iso-stage">
        <svg viewBox="-20 -30 680 270" className="hp-iso" aria-hidden>
          <path d={`M0 0 H${X(172)} Q${X(178)} 2 ${X(180) + 6} 100 Q${X(178)} 198 ${X(172)} 200 H0 Z`} className="hull" />
          {cabins.map((f) => <path key={f} d={`M${X(f)} 0V60 M${X(f)} 140V200`} className="thin" />)}
          <path d={`M0 60H${X(176)} M0 78H${X(176)} M0 122H${X(176)} M0 140H${X(176)}`} className="dash" />
          <path d={`M0 100H${X(179)}`} className="cl" />
          <text x={X(179) - 4} y="96" className="lbl">CL</text><text x="4" y="-4" className="lbl">P</text><text x="4" y="212" className="lbl">S</text>
          {/* OR-117: four cabins, eight berths */}
          <rect x={X(140)} y="80" width={X(150) - X(140)} height="18" className="new" />
          <text x={X(140) + 4} y="93" className="lbl">OR-117 · 4 cabins · 8 berths</text>
          {/* MVZ bulkheads (A-60) */}
          <path d={`M${X(150)} -6V206 M${X(165)} -6V206`} className="a60" />
          <text x={X(150) - 40} y="-12" className="lbl">MVZ 4</text><text x={X(165) + 6} y="-12" className="lbl">MVZ 5 · A-60 · Fr 165</text>
          {/* stairs, lifts, service */}
          <rect x={X(170)} y="84" width={X(174) - X(170)} height="32" className="room" /><text x={X(170) + 10} y="104" className="lbl">Stair 3A</text>
          <rect x={X(154)} y="84" width={X(158) - X(154)} height="32" className="room" /><text x={X(154) + 12} y="104" className="lbl">Lifts</text>
          <text x={X(166) + 6} y="72" className="lbl">Service</text>
          {/* F-07 Stair 3B, selected */}
          <rect x={X(160)} y="82" width={X(164) - X(160)} height="36" className="fail-box" />
          <circle cx={X(162)} cy="100" r="14" className="sel" />
          {tag(X(158) - 6, -22 + 92, "F-07 Fail")}
          {/* F-01 door in the A-60 bulkhead, F-08 dead end, F-09 pinch, U-01 */}
          <rect x={X(165) - 4} y="62" width="8" height="14" className="fail-box" />{tag(X(165) - 34, 52, "F-01 Fail")}
          <rect x={X(146)} y="60" width={X(150) - X(146)} height="18" className="fail-dash" />{tag(X(144), 44, "F-08 Fail")}
          <rect x={X(152) - 6} y="122" width="12" height="18" className="fail-box" />{tag(X(150) - 10, 156, "F-09 Fail · +1")}
          <rect x={X(171) - 5} y="124" width="10" height="14" className="unk-box" />{tag(X(169), 158, "U-01 Cannot verify", "u")}
          {frames.map((f) => <path key={f} d={`M${X(f)} 222V${f % 5 === 0 ? 232 : 227}`} className="thin" />)}
          {frames.filter((f) => f % 5 === 0).map((f) => <text key={f} x={X(f) - 8} y="246" className="lbl">{f}</text>)}
          <text x={X(176)} y="-12" className="lbl">FWD →</text>
        </svg>
      </div>
      <div className="hp-live-stats">
        <div><b className="mono">96</b><span>checks per run</span></div>
        <div><b className="mono">7 · 2</b><span>re-run · changed after one edit</span></div>
        <div><b className="mono">4 decks</b><span>served by the stair that fails</span></div>
      </div>
    </div>
  );
}
