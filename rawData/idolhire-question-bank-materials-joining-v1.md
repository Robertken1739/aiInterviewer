# idolHire Question Bank v1 — Materials Joining / Manufacturing Engineering

Built from an MIT 3.37 (Joining Processes) lecture-note set. Domain: welding, brazing, soldering, diffusion bonding, adhesives, and thermal cutting — a solid "core engineering" vertical for idolHire's demo, since it's technical enough to be credible and specific enough that a generic AI answer is easy to catch being wrong.

Each sequence extends the anchor → constraint → trap framework to five beats. The added two beats (a second contradiction, and a stakeholder-communication close) give more surface area to hit all six rubric axes per sequence instead of three, and every trap is seeded from a mistake the source material itself calls out as a real, historically-made error — not an invented gotcha.

---

## Sequence 1 — Shielding Gas Selection for a Robotic Welding Cell

**Stage 1 (Anchor).** You're programming a robotic GMAW (MIG) cell to weld carbon-steel structural beams. Recommend a baseline shielding gas and justify it in terms of arc behavior and bead quality.
*Tests: Technical Correctness.* Expected reasoning lands on an Ar-CO2 or Ar-O2 blend for carbon steel — smoother arc, acceptable spatter, industry-standard choice.

**Stage 2 (Constraint).** Procurement mandates a 60% cut in shielding-gas spend. Revise your recommendation.
*Tests: Trade-off Reasoning.* Forces the move toward cheaper 100% CO2, and an explicit statement of what's given up — more spatter, more oxidation, worse cosmetic finish — and where that's acceptable (non-cosmetic structural members) versus not.

**Stage 3 (Contradiction).** QA flags a spike in porosity failures — but only on a batch of brackets that turn out to be nickel-based superalloy, not carbon steel, welded in the same cell under the new gas.
*Tests: Constraint Adaptability.* The candidate has to notice the material changed underneath the "one gas for the cell" decision — nickel alloys want Ar or Ar-1%O2, not CO2 — and correct the blanket policy rather than patching around the porosity symptom.

**Stage 4 (AI Trap).** Ask the copilot why argon-helium blends transfer more heat to the workpiece than pure argon. It answers: *"Helium has a higher ionization potential, so the arc has to run hotter to sustain it."*
*Tests: AI Oversight & Skepticism.* That's the textbook explanation the source material explicitly flags as wrong — the real driver is helium's roughly 3x higher thermal conductivity, not ionization potential. A candidate who repeats this without checking fails the axis that matters most.

**Stage 5 (Synthesis).** The plant manager, non-technical, asks for a one-paragraph explanation of the final gas strategy: cost, quality risk, and why you can't just standardize on one gas for the whole cell.
*Tests: Communication Clarity* and closes the loop on Stage 1–3's reasoning.

---

## Sequence 2 — Solder vs. Braze for a Satellite Electronics Assembly

**Stage 1 (Anchor).** Connecting a copper lead to a gold-plated PCB pad. Solder or braze — pick one and justify using the ~425°C (800°F) threshold and expected joint strength.

**Stage 2 (Constraint).** New spec: the joint must survive 300°C thermal cycling in a satellite payload. A typical solder joint creeps above roughly 1000 psi sustained load — revise your approach, and weigh braze/TLP options against the added cost, weight, and the vacuum-environment risk of alloying elements (zinc, magnesium) vaporizing off.

**Stage 3 (Contradiction).** Program office reveals the connector housing next to this joint is aluminum. Aluminum's oxide is stable and won't clean with a standard flux — titanium and zirconium have the same problem and, per the source material, still have no flux active enough below their soldering-relevant temperatures to work reliably.
*Tests: Constraint Adaptability.* The candidate must flag that the joining plan can't be uniform across the assembly once aluminum enters the picture.

**Stage 4 (AI Trap).** Copilot suggests reusing the same RMA rosin flux for the aluminum joint "since it worked fine on the copper pad."
*Tests: AI Oversight & Skepticism.* RMA rosin lacks the chemical activity to clean aluminum oxide — this is exactly the kind of same-flux-for-everything generalization the material warns against. A skeptical candidate asks the copilot to justify flux choice per base metal, not copy-paste it.

**Stage 5 (Synthesis).** Explain to a (non-technical) program manager, in one paragraph, why this joint costs more and takes longer to qualify than a standard PCB solder joint.

---

## Sequence 3 — Diffusion Bonding vs. TLP for a Turbine Seal

**Stage 1 (Anchor).** Joining a nickel-superalloy honeycomb seal for a turbine engine. Compare conventional diffusion bonding (500–5000 psi, hours at 0.6–0.8 of melting temperature) against transient liquid-phase (TLP) bonding (as low as ~5 psi) and recommend one.

**Stage 2 (Constraint).** The program has no budget for heavy diffusion-bonding fixturing capable of holding thousands of psi. Revise toward TLP, and state clearly what TLP still requires to work (a correctly chosen interlayer chemistry — e.g., boron diffusing into nickel — not just "less pressure, same result").

**Stage 3 (Contradiction).** Reliability review raises a real historical failure mode: an 82Au–18Ni braze on a similar part turned out too brittle in service. Candidate must connect this to why the eventual fix used gold as an interstitial diffuser in a TLP joint instead of a straight braze — same "TLP" label, different mechanism, avoids the same intermetallic-embrittlement trap.

**Stage 4 (AI Trap).** Copilot states: *"Thinner braze or TLP joints are always weaker because there's less material carrying the load."*
*Tests: AI Oversight & Skepticism.* This is backwards for tension loading — contact strengthening means a sufficiently thin joint, constrained by non-yielding base material on both sides, can outperform the joint material's own bulk strength. The catch has a second layer: this benefit does *not* extend to shear or fatigue loading, so a candidate who overcorrects into "thin is always better" is only half right.

**Stage 5 (Synthesis).** Write the one-paragraph case for a design review board explaining why a thin TLP joint is not, by itself, a reliability red flag.

---

## Sequence 4 — Flame Cutting vs. Plasma Cutting for Structural Fabrication

**Stage 1 (Anchor).** A fabrication yard needs to cut structural steel I-beams. Recommend oxyfuel flame cutting or plasma cutting and justify on cost and cut quality.

**Stage 2 (Constraint).** 30% of the parts turn out to be stainless steel. Stainless can't be flame cut — chromium oxide melts at ~2800°C, above the base metal's ~1875°C, so the oxide never clears to expose fresh metal (unlike plain iron, where the oxide melts at 1380°C, below the metal's 1536°C, which is exactly why flame cutting works there). Revise the plan for a mixed-material batch.

**Stage 3 (Contradiction).** A separate batch labeled "structural steel" turns out to be titanium brackets. Candidate must recall titanium's oxide (1750°C) melts below its metal (1668°C is close but the process still works in practice) so flame cutting *is* viable — but it smokes heavily, and that smoke is a nuisance, not a toxicity hazard (TiO2 is not toxic), so the response should be procedural (ventilation, notice to staff) rather than switching processes.

**Stage 4 (AI Trap).** Copilot claims: *"Titanium can't be flame cut — it's a reactive, exotic metal, same issue as aluminum."*
*Tests: AI Oversight & Skepticism.* False generalization by surface-level similarity ("exotic metal") instead of the actual physical criterion (does the oxide melt above or below the base metal). Aluminum fails that specific test; titanium doesn't.

**Stage 5 (Synthesis).** Brief the shop floor supervisor, plainly, on the cutting plan across all three materials and why the batch needs to be sorted before anyone starts cutting.

---

## Sequence 5 — Adhesive Bonding vs. Spot Welding for an Automotive Body Panel

**Stage 1 (Anchor).** Choosing between adhesive bonding and spot welding for galvanized-steel door panels, given a rust-through warranty (spot welding locally burns off the galvanized coating, creating a corrosion starting point that adhesive bonding avoids).

**Stage 2 (Constraint).** Cost team caps adhesive spend at $10/lb — the historical ceiling automakers actually hit for adhesives durable enough not to debond over years of service. Revise the recommendation to fit inside that budget rather than specifying the highest-performance adhesive available.

**Stage 3 (Contradiction).** Field warranty data shows adhesive-only doors failing at the corners — in peel, not shear. Candidate should recall adhesives are known to fail in peel loading well before shear, and recommend a targeted fix (local mechanical reinforcement — a rivet or a spot weld placed only at low-visibility, low-corrosion-risk points) rather than reworking the whole joint, echoing how aircraft manufacturers have historically added rivets alongside structural adhesive "just to make sure."

**Stage 4 (AI Trap).** Copilot recommends thickening the adhesive layer at the corners "since more material means more strength."
*Tests: AI Oversight & Skepticism.* Backwards — thicker, less-controlled bondlines are typically weaker due to voids and uneven cure, and thickness doesn't address a peel-mode failure at all. The candidate should catch both the wrong mechanism and the wrong failure mode being targeted.

**Stage 5 (Synthesis).** Draft a plain-language paragraph for a product manager explaining why "just spot-weld it like before" breaks the rust warranty, and why "just add more glue" doesn't fix the corner failures either.

---

## Rubric mapping (for reference — see evaluation-rubric.md)

| Stage | Primary axis tested |
|---|---|
| 1 — Anchor | Technical Correctness |
| 2 — Constraint | Trade-off Reasoning Quality |
| 3 — Contradiction | Constraint Adaptability |
| 4 — AI Trap | AI Oversight & Skepticism |
| 5 — Synthesis | Communication Clarity |

AI-Steering Efficiency is scored transcript-wide across all five stages, not tied to one beat.

## Note on source use

Every trap in this set is seeded from a real "the handbook/rule-of-thumb is wrong" moment in the underlying course material (ionization potential vs. thermal conductivity for helium, oxide-vs-metal melting point as the real flame-cutting criterion, contact strengthening's tension-only benefit, peel vs. shear failure for adhesives). That's deliberate: it keeps the traps grounded in genuine expert-level nuance rather than invented trivia, which is what makes them hard to game by pattern-matching alone.
