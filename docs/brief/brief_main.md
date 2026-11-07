

# SonarIQ — Route Decision & Project Brief

 · 

**Next steps (7 Nov 02:30):**  for the Saturday plan and RCRV conversion;  for the UI design.

## SonarIQ in one page (v2, 7 Nov)

**One sentence:** SonarIQ is a co-pilot inside the ship design tool that tells engineers, the moment they change something, which safety rules it breaks, where and why.

**The real problem, felt by everyone.** You change one thing, something else silently breaks, and nobody notices until it's expensive. At Meyer, compliance is checked by hand, again and again, and errors sometimes slip into production, where fixes cost the most. No engineer can hold every combination of SOLAS, FSS, DNV and accessibility rules in their head.

**What we build.** Three parts that share one rule engine:
- 

**In the design tool:** a docked SonarIQ panel in FreeCAD with Analyse, a Live toggle, findings that light up the 3D objects, and a chat that can explain and fix.
- 

**In the browser:** a web portal where each discipline (fire safety, architecture, HVAC, systems, structure) reviews its inbox, approves or declines, and keeps a signed history.
- 

**Underneath:** the SonarIQ engine as an MCP server, so any design tool or AI client can call the same checks.

**How it works, step by step.**
- 

The engineer opens the ship model (IFC) in FreeCAD; the SonarIQ panel is docked on the right.
- 

**Analyse** (or Live on): the engine reads the model and runs the discipline rule packs deterministically: SOLAS II-2, FSS Ch.13, PVAG/ADA and one DNV rule.
- 

Findings colour the 3D objects red. Each has a clause, the required and measured values, and how it was measured.
- 

A change, made by hand or by asking the chat ("add four cabins aft of frame 150"), triggers a ping. Only the affected checks re-run, including indirect ones, such as a stairway nobody touched.
- 

The chat (open Qwen model) explains using only the engine's numbers and proposes fixes. The engine re-checks each fix before it is shown.
- 

The engineer applies a fix or accepts with a reason. The decision goes to the portal and out as a BCF issue file.

**Tech stack.**
|

Layer |

Choice |
|

Design tool |

FreeCAD 1.x: exact-geometry kernel (OpenCascade), BIM workbench that edits IFC directly, Python + Qt panel |
|

Tool bridge |

[neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) add-on (MIT) + our SonarIQ MCP server |
|

Engine |

Python: IfcOpenShell, Shapely, NetworkX, pint; YAML rule packs |
|

Portal |

React + [That Open Engine](https://github.com/ThatOpen/engine_fragment) (web-ifc WebAssembly, three.js) |
|

Model |

Qwen, served through Vertex AI (see note) |
|

Formats |

IFC4 primary; BCF for issues; OCX optional for hull structure |
|

Real-ship data |

RCRV .nwd → [svf-utils](https://github.com/petrbroz/svf-utils) → glTF + IFC |

**Model note: yes to Qwen, two ways on Vertex AI.** (a) Managed: Qwen3-235B runs as a [serverless API](https://discuss.google.dev/t/now-ga-openais-gpt-oss-qwen3-models-on-vertex-ai-as-open-model-apis/253945), with no GPUs or quota to request, but its listed region is us-south1. (b) Self-deployed: Model Garden deploys an open Qwen model to your own endpoint in an EU region, which needs GPU quota. Decided 7 Nov: the demo runs on (a). The README notes that production would deploy the same open model in GCP Finland (europe-north1) or Meyer's own cloud; this stays out of the pitch. Build against an OpenAI-compatible URL so switching is one setting. Accuracy comes from the deterministic engine; the model affects explanation and tool-use quality.

**Scope fence (the three must-haves).**
- 

Analyse in FreeCAD: highlighted findings with evidence.
- 

A change, then the ping, then Stair 3B fails, with the formula.
- 

Approve or decline with a signed history in the portal.

**Trade-offs to name on stage.** SonarIQ checks and suggests; it never approves a design. The engineer and class do. The rule set is small (about 15 rules), and paragraphs marked verify are confirmed with Meyer. FreeCAD stands in for Cadmatic and NAPA, whose plug-in APIs we couldn't access this weekend; the MCP server is what makes the tool swappable.

**Why judges remember it.** They type a change and watch a stairway nobody touched turn red, with the exact rule and numbers.

## Demo flow v2 (video 2:45, equal split)

Half the video is the designer in FreeCAD, half is the team in the portal. Each beat ends on a number on screen, and the change in beat 2 is typed, not clicked, so judges see the AI respond live.
- 

**Hook (0:00–0:12).** "You change one thing, something else silently breaks, and nobody notices until it's expensive." Then the one sentence.

**In the design tool (0:12–1:15)**
- 

**Analyse (0:12–0:27).** Deck 5 (IFC) open in FreeCAD with the SonarIQ panel docked. Click Analyse: 96 checks in about 2 s. One fire door on the MVZ bulkhead turns red: A-0 where A-60 is required. The evidence card shows clause, required, measured. This is the baseline every team will show.
- 

**Type a change (0:27–0:50).** In the chat: "Add four cabins aft of frame 150." SonarIQ previews the edit; the engineer confirms. Ping: 14 checks re-run, and a dead end, a corridor pinch and Stair 3B turn red. 3B needs 1,380 mm and has 1,350 mm.
- 

**Ask and fix (0:50–1:08).** "Why does 3B fail, and what can I do?" The answer uses the engine's numbers and offers three fixes, each re-checked (✓). Apply option 2; the stair turns green.
- 

**Send to review (1:08–1:15).** One click sends the decision and the open findings to the portal, and writes a BCF file for the other design tools.

**In the portal (1:15–2:20)**
- 

**Disciplines (1:15–1:35).** The fire-safety inbox shows the decision thread. The HVAC inbox has a duct through the A-60 bulkhead with no damper. Approve, decline, signed history.
- 

**Real ship, 30 s (1:35–2:05).** Meyer's own RCRV model in the browser. Applicability: research vessel, 28 people aboard, so SOLAS rules for more than 36 passengers show not applicable. Accessibility: doors measured in inches; the planted 30-in door fails 32 in, and a 34-in control door passes.
- 

**Proof (2:05–2:20).** Benchmark: N of N planted violations caught, 0 false alarms. Badges show that SonarIQ reads text, drawings and 3D models.
- 

**Close (2:20–2:45).** Open formats (IFC and BCF, OCX next), the one sentence, and the trade-off.

**Live finals (4:00): a judge drives.** Hook 0:30 · judge types in the FreeCAD panel 1:45 · portal and RCRV 0:45 · proof and pilot 1:00. Keep the video open, muted, as a fallback.

**Prompts a judge can type, and that must always work:**
|

Prompt |

What SonarIQ does |
|

Add four cabins aft of frame 150 |

Previews the edit, then pings: Stair 3B, dead end, pinch |
|

Make the starboard corridor at frame 152 900 mm wide |

Corridor clears FSS; still under PVAG's 915 mm, so one finding stays |
|

Why does stair 3B fail? |

Formula with N₁…N₄ from the model; three verified fixes |
|

Swap door FD-5-165P to A-60 |

Fire finding clears; nothing else changes |
|

What did my last change affect? |

Lists the 14 re-run checks and the 3 that changed |

The chat can only call a fixed set of model edits (add a cabin block, move a wall, set a door's width or fire class). That is what keeps a live demo reliable, and it is honest: the engineer confirms every edit.

## Decision

**Go with Route A, Fire & Life Safety Co-pilot (31/35).** Borrow one check from Route B (a duct or pipe crossing a fire division without a damper or certified penetration) and one forecast from Route C (escape capacity before and after a change).
- 

**Why A:** it is the only route that hits every word of Meyer's brief (SOLAS, DNV, PVAG, accessibility). It uses public rules, gets verdicts you can prove, and matches the example their naval architect gave you: fire insulation between decks and fire-rated glazing.
- 

**Why not B alone:** it is the most visual route, but it depends on reading the RCRV 3D model (format still unknown), and clash accuracy is hard to prove in 28 hours.
- 

**Why not C alone:** it is the most visionary, but it drifts from "compliance checking" and its forecasts can't be verified on a weekend. Meyer said accuracy matters most.
- 

**Scope fence (the three must-haves):** (1) click Analyse → findings drawn on the plan; (2) realtime mode with change impact; (3) approve or decline with a documented trail.
- 

**Pitch line:** "Compliance that keeps pace with the design: see what a change breaks, with the proof, before it reaches the yard."

Screens for all three routes: [SonarIQ](https://claude.ai/artifact/SMXodBHQ8tk2Tu9ioNa6iv)[ UI Mockups](https://claude.ai/artifact/SMXodBHQ8tk2Tu9ioNa6iv) (A1 Analyse, A2 live check and co-pilot, A3 web workspace, B systems clashes, C forecast).

## Locked on 7 Nov

**SonarIQ, Route A****: a panel inside FreeCAD plus a web portal, both on one rule engine.** Updated 02:00 after your answers; this replaces the portal-only plan from 01:20.
|

Decision |

Choice |

Why |
|

Name |

**SonarIQ** (team name) |

Sonar finds hazards before you hit them; the re-check after a change is the "ping" |
|

Route |

A · Fire & Life Safety Co-pilot |

Best brief fit, provable accuracy |
|

Where designers work |

**FreeCAD** with a docked SonarIQ panel: chat, Analyse, Live, Fix, Accept |

Designers stay in a design tool; free and runs on your Mac or a Linux VM |
|

Where the team reviews |

Web portal (three.js + web-ifc) with inboxes per discipline |

Reviewers and class don't need CAD; RCRV shown here |
|

Demo split |

Equal: about 1:05 in FreeCAD, 1:05 in the portal |

Your call, 7 Nov |
|

Main format |

**IFC4**, all disciplines; OCX optional for hull structure |

IFC carries walls, doors, spaces, ducts and pipes, and renders in the browser |
|

Tool sync |

FreeCAD edits the IFC directly, and SonarIQ re-checks on each change through MCP |

Sync comes from the format and MCP, not a custom bridge. Shown only if the accuracy tests pass |
|

Issues back to other tools |

BCF |

Open standard for issue round-trips |
|

Model |

Qwen on Vertex AI: managed API; README notes EU deployment for production, not in the pitch |

Strong tool use; verdicts stay deterministic |
|

Organisation |

Modules per discipline: rules, viewer colours, inbox |

Matches how Meyer splits the work |

New pitch line: "Ships use sonar to see hazards before they hit them. SonarIQ does that for ship designs."

## Prototype: export once, check in one portal

Two front doors, one rule engine. The designer works in FreeCAD, which talks to the SonarIQ server live over MCP. Other tools export a file. Reviewers use the portal. Issues go back to the tools as BCF.
[chart: SonarIQ prototype flow · export, check, review, issues back]

- 

**IFC4 is the main format.** It carries every discipline we check, and [Cadmatic Plant Modeller exports it](https://docs.cadmatic.com/plant/Content/Integration/exchanger_ifc.htm). FreeCAD's BIM workbench edits it directly, and the portal renders it through web-ifc (WebAssembly) and [That Open Engine](https://github.com/ThatOpen/engine_fragment).
- 

**OCX is optional, for hull structure.** It is the class-approval format: [Cadmatic Hull exports it](https://docs.cadmatic.com/hull/Content/Application_Menus/am_export_to_ocx.htm), [NAPA imports and exports it](https://www.marinelink.com/news/napa-bureau-veritas-enable-d-model-usage-493594), and DNV, BV and LR [review designs in it](https://www.dnv.com/news/dnv-damen-and-napa-use-3d-model-based-approval-to-streamline-ship-design-approval-244942).
- 

**BCF carries issues back.** Cadmatic's information management [supports BCF markups](https://www.cadmatic.com/en/resources/release-information/release-highlights-2021t1-print.pdf), so a finding opens on the right object.
- 

**MCP makes the panel portable.** The FreeCAD panel calls the SonarIQ MCP server ([FreeCAD MCP add-on](https://github.com/neka-nat/freecad-mcp) for reading and editing the model). A Cadmatic, NAPA or AutoCAD adapter would call the same server.

## Discipline modules

Each professional opens SonarIQ in their own module: their rules, their viewer colouring, their inbox. Cross-discipline conflicts land in both inboxes. Fire safety and architecture are built in full for the demo; the others are shells with one real check, or a stub.
|

Module |

Who uses it |

Reads |

Example checks |

Demo depth |
|

Fire safety |

Fire-safety engineer |

IFC walls, doors, zones (fire class) |

MVZ boundary A-60 (SOLAS II-2/9.2.2.1.1); door matches the wall's fire class; MVZ length ≤ 40 m |

Full |
|

Architecture & escape |

Interior / arrangement designer |

IFC spaces, doors, stairs, berths |

Dead ends (II-2/13.3.1.2); stair width formula (FSS Ch.13 §2.1.2); PVAG/ADA door 32 in, route 36 in |

Full, incl. the ripple |
|

HVAC |

HVAC engineer |

IFC duct segments + fire divisions |

Duct through an A-class division needs a damper (SOLAS II-2/9.7, verify) |

One check |
|

Systems / piping |

Systems engineer |

IFC pipe segments + fire divisions |

Pipe through A-60 needs a certified penetration (II-2/9.3, verify) |

One check |
|

Structure |

Hull engineer |

OCX plates, stiffeners, materials |

Plate thickness ≥ class minimum, e.g. the 4.5 + 0.02·L2 mm type of rule ([CSR example](https://koreascience.kr/article/CFKO201106737200579.pdf); exact DNV-RU-SHIP clause to verify on rules.dnv.com) |

Stretch: only with a public OCX sample model |

Each module is a rule pack (YAML) plus a viewer lens. Adding a discipline means adding a pack, not changing the engine.

## Getting the RCRV model into the demo

The file Meyer shared is a Navisworks document, [12100-RCRV-199_07-08-2021.nwd](https://oregonstate.app.box.com/s/hh0tfmz6icc5avvup57ltew5m0nxwqap). Navisworks can't export IFC, so convert it in two layers: a mesh for viewing, and a semantic model for checking, linked by each object's source ID.
|

Path |

How |

Needs |

Time |

You get |
|

**1 · Recommended** |

Upload the .nwd to Autodesk's [Model Derivative API](https://forge.autodesk.com/en/docs/model-derivative/v2/developers_guide/supported-translations) (NWD → SVF2), then [svf-utils](https://github.com/petrbroz/svf-utils) converts it to glTF and downloads the property database as `properties.sqlite` |

Free Autodesk developer account; runs from Linux or Mac |

1–2 h |

Full 3D plus every object's name, layer and source properties |
|

2 · Licence route |

Navisworks Manage via an Autodesk Education licence (the university account Meyer hinted at): export FBX and the selection-tree properties, then Blender or assimp to glTF |

Windows + education licence |

2–3 h |

Same, with more manual steps |
|

3 · Fallback |

Navisworks Freedom (free viewer) to inspect and measure, plus the RCRV GA PDF for a 2D semantic model |

Windows |

1 h |

Screenshots and a 2D deck, no 3D export |

Cloud conversion is fine here because the file is public. The README should say production would use an on-prem converter.

**Turning geometry into a model SonarIQ can check:**
- 

**Classify** each object into a discipline and IFC class (door, wall, space, duct, pipe, plate) from its name, layer and properties. Rules first, the local LLM for leftovers, and an engineer confirms the mapping on one review screen.
- 

**Write IFC4** with IfcOpenShell: triangulated geometry plus property sets, keeping the source object ID so BCF issues point back to the right object.
- 

**Fill gaps from the drawings:** room names and fire classes from the GA PDF. Anything still missing is marked unknown, and its checks report "cannot verify" instead of guessing.
- 

**Measure honestly:** door clear width comes from the leaf's oriented bounding box. Flat faces survive triangulation exactly; curved hull surfaces are display-only. This answers Meyer's warning about mesh conversion.
- 

**Plant test cases** on a copy: narrow one door to 30 in, swap one fire class. Untouched copies serve as compliant controls.

**Applicability is a free accuracy win.** The RCRV is a research vessel (16 scientists and 12 crew in the [2013 UNOLS ](https://www.unols.org/sites/default/files/201304rvoap38.pdf)[presentation](https://www.unols.org/sites/default/files/201304rvoap38.pdf)), so SOLAS rules for ships carrying more than 36 passengers don't apply. SonarIQ should say "not applicable" there. US [academic research vessels have been designed with ADA features, such as 32-inch doors to the mess, lounge and labs on the ARRV, so the accessibility module still applies](https://unols.org/sites/default/files/200410ficap05.PDF), in the vessel's own inches.

## Does it meet Meyer's brief?

It meets all 13 points if we close one gap: **the brief names DNV class rules twice, and the rulebook has no DNV rule yet.** Everything else is covered, and four points go beyond what was asked.
|

Brief says (section) |

SonarIQ's answer |

Status |

Action |
|

Check designs against **class rules (e.g. DNV)** (§02, §03) |

Rule packs are source-tagged; a structure module reads OCX, the class-approval format |

**Gap** |

Add one DNV rule with its clause, verified on rules.dnv.com. Structure min thickness via OCX, or a DNV fire or accessibility clause on IFC |
|

…and SOLAS (§02, §03) |

SOLAS II-2/9 and II-2/13, FSS Ch.13 |

Met |

— |
|

…and regulations: PVAG, ADA, MARPOL, COLREG, Load Line, Tonnage (§02) |

PVAG/ADA in full; the rest out of scope |

Met (scoped) |

Say on the architecture slide that new packs plug in |
|

Check **early**, before conflicts propagate downstream (§03) |

Ripple re-checks what a change touches; maturity keeps concept zones quiet |

Beyond |

Make the stair-3B moment the centre of the video |
|

Inform engineers of issues found (§02) |

Discipline inboxes; BCF back to their tools |

Met |

Show one BCF export in the video |
|

Use public data: RCRV 3D model and GA drawings (§05) |

RCRV .nwd converted and checked in its own inches |

Met |

Path 1 above, Saturday morning |
|

**Accuracy** is very important (§06) |

Deterministic verdicts; planted violations plus compliant controls; applicability says what doesn't apply |

Beyond |

Put the benchmark numbers on screen |
|

Interpret **written text** (§06) |

Rule text compiled into checks; vessel particulars read from the spec PDF to set applicability |

Met |

Label it "reads text" in the video |
|

Interpret **technical drawings** (§06) |

Room names and fire classes taken from the GA PDF |

Met if built |

Keep it, timeboxed to 3 h |
|

Interpret **3D models** (§06) |

IFC and OCX ingest; RCRV converted |

Met |

— |
|

Highlight **why** something fails, against a specific part of a standard (§06) |

Evidence card: clause, required vs measured, method |

Met |

— |
|

Solid foundation over polish; good usability a plus (§06) |

Engine and benchmark first; CAD-native UI |

Met |

Freeze features Saturday 22:00 |
|

Submit a short demo, code repo and **deployment docs** (§07) |

Video, repo, DEPLOYMENT.md, Docker Compose, on-prem model |

Met |

— |

**Beyond the brief:** OCX and BCF match where class approval is heading. NAPA, Cadmatic and AVEVA already export OCX, and the [OCX consortium](https://newsletter.prostep.com/en/newsletter/prostep-newsletter-12023/prostep-fully-supports-ocx-based-data-exchange-in-the-shipbuilding-industry) wants to add commenting so designers see class remarks in their own tool. SonarIQ shows that loop working with open standards, on Meyer's own servers.

Source: Meyer Turku challenge brief, Since AI 2026 (your PDF), sections 02–07.

## The problem all three routes share

Meyer engineers check compliance by hand, again and again, while a one-off cruise ship keeps changing. Errors that slip through are found in manufacturing, where they cost the most.
|

Field |

Answer |
|

Who suffers |

Naval architects and design engineers in basic and detail design; the fire-safety specialist who signs off |
|

When |

Every owner change (more cabins, a new venue, more capacity) and every design-spiral loop, for about 1.5 years |
|

Why it's hard |

SOLAS, FSS, DNV and PVAG rules interact. One change propagates across disciplines. No one can hold every combination in their head (your Q&A) |
|

Why now |

Class societies are moving toward 3D model-based approval; local open models can now run on a 32 GB engineer laptop |
|

What they asked for |

A tool that checks the design while engineers work, flags the issue and says why. Accuracy over polish; data stays under their control (transcript §3, §6; brief §06) |
|

Measurable pain to show |

Issues caught at design time instead of in the yard; time to re-check after a change; false alarms |

Judges have felt this kind of pain themselves: a small change that silently broke something elsewhere. Lead with that, not with the technology.

## Route scores

Route A wins on the two things Meyer weighs most: brief fit and provable accuracy. B and C become features inside A, not separate products.
|

Criterion (1–5) |

A · Fire & Life Safety Co-pilot |

B · Systems Conflict Guard |

C · Design Consequence Forecaster |
|

Fit with Meyer's brief |

5 |

4 |

2 |
|

Accuracy you can prove on stage |

5 |

4 |

2 |
|

Public rules + data available |

4 |

3 |

2 |
|

Buildable in ~28 h |

4 |

3 |

2 |
|

Demo wow |

4 |

5 |

5 |
|

Different from other teams |

4 |

4 |

5 |
|

Pilot value for Meyer |

5 |

4 |

3 |
|

**Total (of 35)** |

**31** |

**27** |

**21** |

Scores are my judgement from the brief, the transcript and your Q&A notes. Change any cell you disagree with; A leads B by 4 points and C by 10, so one changed cell won't flip the ranking.

## Route A · Fire & Life Safety Co-pilot (recommended)

**Real problem.** Fire divisions, escape routes and accessibility are re-checked by hand after every change. One added cabin can make a corridor too narrow, create a dead end, or overload a stair that serves four decks.

**What you build.** A co-pilot that docks next to the drawing. It checks SOLAS II-2, the FSS Code and PVAG/ADA rules on demand or live, draws each finding on the deck plan, and keeps an approve/decline trail.

**How it works.**
- 

An adapter turns the design (IFC/DXF export, or a generated test deck) into a small ship model: decks, frames, zones, spaces, walls with fire class, doors, stairs.
- 

A deterministic engine measures widths, dead ends, persons per stair and fire classes against a rulebook in YAML.
- 

A change diff finds which checks a change affects and re-runs only those (the ripple).
- 

A local LLM explains findings, drafts new rules from clause text, and proposes fixes. The engine re-checks every fix before it is shown.

**Features.**
|

Feature |

Tier |

Sticky note it answers |
|

Click **Analyse** → findings list + highlights on the plan |

Must |

On demand, Visual feedback (actual highlight) |
|

Realtime mode, toggle on/off, re-checks each change |

Must |

Realtime (while designing) |
|

Change ripple: what this edit broke elsewhere |

Must |

Conflict detection (space) |
|

Evidence card: clause, required vs measured, formula |

Must |

High accuracy of the codes |
|

Approve / decline / accept-with-reason, logged like a GitHub review |

Must |

Approvals and declines well documented |
|

Fire classes + escape + accessibility rule packs |

Must |

Fire, accessibility compliance |
|

Local or EU-hosted model, works offline |

Must |

Private / EU models / offline |
|

Ask-the-co-pilot chat, grounded in findings |

Should |

Co-architect, small chat |
|

Maturity per zone (concept zones stay quiet) |

Should |

Ease of access (UX) |
|

Duct/pipe through fire division without damper or penetration |

Should |

Conflict detection (material, technology) |
|

Escape-capacity forecast before vs after a change |

Should |

Bridge to Route C |
|

Versioned, hash-chained decision log |

Should |

Sync and versioning |
|

Web workspace: search, history, export to tasks |

Should |

Expanded web app |

**Tech.** Python (FastAPI, Shapely, NetworkX, pint, IfcOpenShell), React + SVG plan, Ollama with an open model, Docker Compose.

**Trade-off to disclose.** Only a small rule set is implemented (about 10–15 rules); paragraph numbers marked "verify" are confirmed with Meyer. Real CAD plug-ins are roadmap; the demo uses neutral exports.

**Why judges remember it.** The stair nobody touched: four new cabins on Deck 5 make Stair 3B fail the FSS width formula, with the measured proof on screen in a second.

**Demo tip.** Keep a recorded take of the ripple; cache LLM explanations so the live demo never waits on the model.

## Route B · Systems Conflict Guard

**Real problem.** Piping, HVAC and cable routes are modelled by different disciplines in different tools. A duct that crosses an A-60 bulkhead without a fire damper, or a pipe with no certified penetration, is often found only in the yard, where rework is expensive.

**What you build.** A 3D model checker that finds conflicts between systems and the fire and space layout: hard clashes, missing clearance, and wrong penetrations through fire divisions.

**How it works.**
- 

Read the RCRV 3D model (pipes, ducts, machinery) or an IFC export into an exact-geometry kernel (OpenCascade).
- 

Intersect system runs with walls and decks; classify each crossing by the fire class of the division.
- 

Check rules: dampers and penetration seals in A-class divisions (SOLAS II-2/9.3 and 9.7, verify), maintenance clearance, hard clashes.
- 

Show conflicts in a 3D view with an isolate-and-zoom camera; the LLM groups and explains them.

**Features.**
|

Feature |

Tier |
|

Click Analyse → clash list + 3D highlight |

Must |
|

Penetration check per fire class (damper, sealed penetration) |

Must |
|

Clearance zones for maintenance access |

Should |
|

Clash grouping (same root cause → one issue) |

Should |
|

Assign to discipline owner, track status |

Should |

**Tech.** OpenCascade (pythonOCC or build123d), IfcOpenShell, three.js or That Open Engine, FastAPI, Ollama.

**Trade-off to disclose.** Depends on 3D data quality. Meyer warned that mesh conversions lose the geometry needed for checks, and the RCRV file format is still unknown.

**Why judges remember it.** A 3D model that lights up red where a duct punches through a fire wall.

**Risk for this weekend.** If the RCRV model can't be read by Saturday 09:00, this route has no data. Keep its best check (penetration through a fire division) as a Should inside Route A, using 2D duct lines on the deck plan.

## Route C · Design Consequence Forecaster

**Real problem.** Design decisions lock in how the ship operates for 30+ years: evacuation flow, crew walking distances, maintenance access, energy use. These effects are rarely visible while the layout is still easy to change.

**What you build.** A "what-if" panel. For each design change it forecasts operational effects alongside compliance: evacuation time per zone, crowding at stairs, crew walking distance, and maintenance reachability.

**How it works.**
- 

Same ship model as Route A, plus occupancy and flow assumptions.
- 

Simple agent-based or flow model for evacuation (the IMO evacuation analysis guidelines, MSC.1/Circ.1238, give the method).
- 

Before/after comparison of each change, with a confidence band.
- 

The LLM writes a short consequence note for the engineer.

**Features.**
|

Feature |

Tier |
|

Before/after forecast card per change |

Must |
|

Evacuation flow and stair crowding heatmap |

Must |
|

Crew route and maintenance access distance |

Should |
|

Scenario compare (option A vs B) |

Should |

**Tech.** Python simulation (NetworkX flows or a simple crowd model), React charts, Ollama.

**Trade-off to disclose.** Forecasts are estimates; they can't be validated against real operations this weekend, and the brief asks for compliance checking with accuracy.

**Why judges remember it.** "This change adds 40 seconds to evacuation of MVZ 3."

**How to use it inside Route A.** One Should feature: an escape-capacity forecast that reuses the FSS stair formula (required vs available width, persons per stair) before and after each change. It's grounded in a regulation, so it stays accurate. Put full operational forecasting on the roadmap slide.

## Where each of your ideas lands

All 16 notes have a place: 12 ship as Must, 4 as Should, and two are reshaped (crypto becomes a hash chain; the web app becomes one workspace screen).
|

Your note |

Decision |

Tier |

Interface |

How it shows in the demo |
|

Fire, accessibility compliance |

Keep, core rule packs |

Must |

Both |

SOLAS II-2, FSS Ch.13, PVAG/ADA checks |
|

High accuracy of the codes |

Keep |

Must |

Both |

Deterministic verdicts, evidence card, benchmark |
|

Visual feedback (actual highlight) |

Keep |

Must |

In-tool panel |

Revision clouds and dimension strings on the plan |
|

Visual feedback |

Merge with the one above |

Must |

In-tool panel |

Severity colours, ripple rings |
|

Conflict detection: space |

Keep |

Must |

In-tool panel |

Change ripple, widths, dead ends, stair capacity |
|

Conflict detection: material, technology |

Narrow |

Should |

In-tool panel |

Duct or pipe through a fire division without a damper or seal |
|

Easy approvals and declines, documented like GitHub |

Keep |

Must |

Both |

Approve / Decline / Accept-with-reason, with a review thread |
|

Private / EU models / offline |

Keep |

Must |

Both |

Wi-Fi off in the video; Docker on-prem |
|

Ease of access (UX) |

Keep |

Must |

Both |

Naval vocabulary, keyboard shortcuts, one-click Analyse |
|

Co-architect |

Keep, as a grounded assistant |

Should |

In-tool panel |

"Why does this fail? What are my options?" |
|

Some UI with actions and small chat |

Keep |

Must |

In-tool panel |

The docked SonarIQ panel |
|

Possibly tool agnostic |

Keep |

Must (design) |

Both |

Neutral ship model + adapters; one CAD shell in the demo |
|

Sync and versioning (maybe crypto) |

Reshape: hash-chained log, no blockchain |

Should |

Web workspace |

Every decision signed and chained; revision A vs B diff |
|

Expanded web app: search, documenting, collaboration, tasks/Linear |

Reshape: one workspace screen |

Should |

Web workspace |

Findings inbox, history, export to Jira/Linear (metadata only) |
|

Realtime (turn on or off) |

Keep |

Must |

In-tool panel |

"Live check" toggle |
|

On demand (Analyse) |

Keep |

Must |

In-tool panel |

The basic click-and-analyse |

On crypto: a hash chain gives the same tamper-evidence with no wallets or network. That matters, because Meyer wants nothing leaving their servers. Save Midnight for a later "share findings with class without revealing the design" idea.

On Linear: it's a cloud service, so send only finding IDs and titles, never geometry. Meyer's own tracker (Jira) is the likelier target.

## Two modes, two interfaces

The engineer works in the **in-tool panel**; the team reviews in the **web workspace**. Both run on the same engine on Meyer's server.
|

 |

On demand (Analyse) |

Realtime (Live check on) |
|

**In-tool panel** (docked beside the CAD view) |

Engineer picks a scope (deck, zone, rule pack) → Analyse → findings list + highlights. The basic expectation every judge looks for |

Each saved change triggers a re-check of only the affected rules; ripple rings show what moved. The off switch stays visible, so it never nags |
|

**Web workspace** (browser, for the team) |

Full-ship run before a class submission; export an evidence pack |

Inbox of new findings from everyone's changes; review thread, approve/decline, history per revision |

The demo shows the panel first (the click-and-analyse, then live), and spends 15 seconds on the workspace to show the documented approvals and versioning.

## Demo storyline (SonarIQ, 2:45, two acts)

Act 1 proves accuracy on Meyer's own example ship; Act 2 shows the change ripple in Meyer's world. Each beat ends on a number on screen.

Superseded by Demo flow v2 at the top of this doc (7 Nov 02:00). The two-act version is kept below for reference only.

Old beats, in short: hook → RCRV import and applicability → accessibility Analyse in inches → fire-class mismatch → cruise-deck change and Stair 3B → co-pilot fixes → discipline inboxes and BCF → benchmark and close.

## Open decisions for you
- 

Confirm Route A, with B's penetration check and C's capacity forecast as Shoulds
- 

Name: SonarIQ (your team name), decided 7 Nov
- 

CAD shell: settled on 7 Nov. The web portal is the shell; no imitation of Meyer's tools
- 

Baseline beat: rev A now shows one fire-door finding on Analyse, so the click-and-analyse has something to find. The starter kit's SPEC assumes rev A is clean; I'll update it once you confirm
- 

Web workspace: one screen (inbox + review thread + history) or skip it and show approvals only in the panel
- 

Task export: Jira (Meyer's likely tracker) or Linear, metadata only

**New on 7 Nov:**
- 

Install FreeCAD 1.x on your Mac and check that the BIM workbench opens an IFC file
- 

Enable Vertex AI in your GCP project and get access to a Qwen model (managed API); optionally request EU GPU quota for a self-deployed endpoint
- 

Sign up for an Autodesk developer account and start the RCRV .nwd conversion (path 1) first thing Saturday
- 

Pick the one DNV rule to add, and verify its clause on rules.dnv.com
- 

Run the five judge prompts end to end before recording; each must work three times in a row
- 

Refresh SPEC, starter kit and mockups to v2: FreeCAD panel + portal, IFC, MCP

Sources: Meyer challenge brief and briefing transcript (your uploads); framing fields from [NextAgile: top hackathon project ideas](https://nextagile.ai/blogs/gen-ai/top-hackathon-project-ideas/) (real problem, what you build, how it works, tech, scope fence, trade-off, why judges remember).
