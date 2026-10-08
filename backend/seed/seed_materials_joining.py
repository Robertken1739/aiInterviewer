"""One-off script that loads the materials-joining question bank into
sequence/stage rows and primes the Helper vector store.

Run it with:

    python -m seed.seed_materials_joining

Content is transcribed from rawData/idolhire-question-bank-materials-joining-v1.md
(prompts + trap claims) and its companion -ANSWERS.md (reference_answer /
grading notes). `source_material` per sequence is hand-written neutral
background -- conceptual grounding for the Helper LLM's hints, deliberately
vaguer than the graded reference_answer/trap resolutions so the Helper can't
hand the answer to a candidate through the "neutral" channel.

Idempotent: skips any sequence whose title already exists, so re-running
this after sessions have been created against it is safe (no destructive
deletes that would violate the sequence -> interview_session foreign key).
"""

from sqlalchemy.orm import Session

import vector_store
from db.models import Sequence, Stage
from db.session import SessionLocal

SEQUENCES = [
    {
        "title": "Shielding Gas Selection for a Robotic Welding Cell",
        "source_material": (
            "In GMAW (MIG) welding, the shielding gas protects the molten weld pool from atmospheric "
            "nitrogen and oxygen, and strongly influences arc stability, spatter, penetration, and bead "
            "appearance. Gas choices for steel welding commonly include pure CO2, argon-CO2 blends, and "
            "argon-oxygen blends, each with different cost and quality trade-offs.\n\n"
            "Reactive gases like CO2 tend to be inexpensive but produce a less stable arc with more "
            "spatter, while gas blends with a higher inert-gas content generally cost more but give a "
            "smoother arc and better cosmetic finish. These trade-offs matter differently depending on "
            "whether a weld is structural (strength matters, appearance doesn't) or cosmetic (appearance "
            "matters).\n\n"
            "Different base metals respond very differently to the same shielding gas. Carbon steel is "
            "fairly tolerant of reactive gases, while some other alloy families are much more sensitive "
            "to oxidation or carbon pickup from a reactive shielding-gas atmosphere, which can show up as "
            "porosity or other weld defects.\n\n"
            "Gas mixtures used to increase heat transfer into the workpiece can work through more than "
            "one physical mechanism. Some gases have inherently different thermal transport properties "
            "than others, and some blends achieve a similar heating effect indirectly, through a gas that "
            "reacts and releases energy in the arc rather than through simple thermal conductivity alone."
        ),
        "stages": [
            {
                "order_index": 1,
                "stage_type": "anchor",
                "prompt_text": (
                    "You're programming a robotic GMAW (MIG) cell to weld carbon-steel structural beams. "
                    "Recommend a baseline shielding gas and justify it in terms of arc behavior and bead quality."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Ar-1-2% O2 or an Ar-CO2 blend (roughly 5-20% CO2) for carbon steel: smoother, more "
                    "stable arc than pure CO2, acceptable spatter, good bead appearance for a "
                    "general-purpose structural weld. Pure argon isn't typically used alone on steel "
                    "because arc behavior is less stable."
                ),
            },
            {
                "order_index": 2,
                "stage_type": "constraint",
                "prompt_text": "Procurement mandates a 60% cut in shielding-gas spend. Revise your recommendation.",
                "trap_claim_text": None,
                "reference_answer": (
                    "Shift the bulk of non-cosmetic structural welding to 100% CO2 -- it's the cheapest "
                    "option, standard in the auto industry, and fine where appearance doesn't matter. Keep "
                    "the more expensive Ar blend only for joints where finish, reduced spatter, or reduced "
                    "oxidation genuinely matter. The trade-off to name explicitly: CO2 brings more spatter "
                    "and post-weld cleanup labor, which eats into some of the raw gas savings, and more "
                    "oxidation-related defects, so it's not a free 60% cut in total cost, just in gas "
                    "line-item cost."
                ),
            },
            {
                "order_index": 3,
                "stage_type": "contradiction",
                "prompt_text": (
                    "QA flags a spike in porosity failures -- but only on a batch of brackets that turn out "
                    "to be nickel-based superalloy, not carbon steel, welded in the same cell under the new gas."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "The porosity is showing up on nickel-based superalloy brackets welded under the new "
                    "CO2 policy, not on the carbon-steel beams. Nickel alloys should run on Ar or Ar-1%O2 "
                    "-- CO2 causes oxidation and carbon-pickup problems in nickel systems that don't show "
                    "up in steel. The fix isn't reverting the whole cell's gas policy, it's recognizing gas "
                    "selection has to be tracked per alloy, not per cell, and re-auditing anything else "
                    "that shares the cell."
                ),
            },
            {
                "order_index": 4,
                "stage_type": "ai_trap",
                "prompt_text": "Ask the copilot why argon-helium blends transfer more heat to the workpiece than pure argon.",
                "trap_claim_text": "Helium has a higher ionization potential, so the arc has to run hotter to sustain it.",
                "reference_answer": (
                    "The copilot's \"higher ionization potential\" explanation is the outdated "
                    "welding-handbook theory the source material explicitly debunks. The real mechanism: "
                    "helium has roughly 3x argon's thermal conductivity, which is what increases heat "
                    "transfer into the workpiece. A cheaper way to get most of that benefit without paying "
                    "for expensive helium: Ar-H2(5%) achieves comparable performance through \"reactive "
                    "thermal conductivity\" -- hydrogen dissociates (H2 -> 2H) in the hot arc core, "
                    "absorbing energy, then recombines in the cooler boundary layer near the workpiece and "
                    "releases that energy there, mimicking helium's effect. A candidate citing this "
                    "alternative, rather than just refuting the copilot, is demonstrating strong domain "
                    "command, not just skepticism."
                ),
            },
            {
                "order_index": 5,
                "stage_type": "synthesis",
                "prompt_text": (
                    "The plant manager, non-technical, asks for a one-paragraph explanation of the final "
                    "gas strategy: cost, quality risk, and why you can't just standardize on one gas for "
                    "the whole cell."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "\"We're keeping the pricier argon-blend gas for the handful of joints where appearance "
                    "and low spatter actually matter, and switching everything else -- the structural, "
                    "non-cosmetic welds -- to CO2, which is a fraction of the cost. We can't standardize on "
                    "one gas because different metals in this cell, like the nickel brackets, behave badly "
                    "on CO2 regardless of cost; using it there would trade a gas-cost saving for a much "
                    "more expensive porosity/rework problem.\""
                ),
            },
        ],
    },
    {
        "title": "Solder vs. Braze for a Satellite Electronics Assembly",
        "source_material": (
            "Soldering and brazing are both used to join metal parts using a filler metal, but they differ "
            "mainly in process temperature, with brazing generally used above roughly 450C and soldering "
            "below it. Higher-temperature joints are generally associated with greater joint strength, at "
            "the cost of more thermal stress on the parts being joined.\n\n"
            "Joint requirements depend heavily on the service environment: mechanical load, sustained "
            "versus transient loading, and thermal cycling all affect whether a lower-temperature solder "
            "joint is adequate or a stronger braze/diffusion joint is required.\n\n"
            "In vacuum environments, some alloying elements used in filler metals can vaporize under "
            "vacuum and contaminate nearby sensitive components, so filler alloy composition needs to be "
            "checked against the operating environment, not just against strength requirements.\n\n"
            "Certain metals form an oxide layer that is very stable and difficult for standard flux "
            "chemistries to clean, which limits which soldering or brazing approaches will actually work "
            "on them. Flux and process choices generally need to be evaluated per base metal rather than "
            "assumed to carry over from one metal to another."
        ),
        "stages": [
            {
                "order_index": 1,
                "stage_type": "anchor",
                "prompt_text": (
                    "Connecting a copper lead to a gold-plated PCB pad. Solder or braze -- pick one and "
                    "justify using the ~425C (800F) threshold and expected joint strength."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Solder: the joint is well under the 425C/800F solder-braze threshold, a standard "
                    "copper-lead-to-gold-pad joint doesn't need braze-level strength, and solder is "
                    "cheaper, faster, and lower-temperature (less thermal stress on the PCB)."
                ),
            },
            {
                "order_index": 2,
                "stage_type": "constraint",
                "prompt_text": (
                    "New spec: the joint must survive 300C thermal cycling in a satellite payload. A "
                    "typical solder joint creeps above roughly 1000 psi sustained load -- revise your "
                    "approach, and weigh braze/TLP options against the added cost, weight, and the "
                    "vacuum-environment risk of alloying elements (zinc, magnesium) vaporizing off."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Move to braze or TLP. Solder creeps under sustained load above roughly 1000 psi and "
                    "isn't rated for 300C cycling; a silver-braze joint offers 5,000-10,000 psi "
                    "room-temperature strength and tolerates the thermal environment. Constraints to flag: "
                    "avoid braze alloys containing zinc or magnesium (high vapor pressure -- they'll "
                    "volatilize in vacuum and contaminate the payload); use an alloy with a vacuum-rated "
                    "designation (the \"V\" in alloy codes like BAg21-V exists for exactly this reason)."
                ),
            },
            {
                "order_index": 3,
                "stage_type": "contradiction",
                "prompt_text": (
                    "Program office reveals the connector housing next to this joint is aluminum. "
                    "Aluminum's oxide is stable and won't clean with a standard flux -- titanium and "
                    "zirconium have the same problem and, per the source material, still have no flux "
                    "active enough below their soldering-relevant temperatures to work reliably."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "The aluminum housing next to the joint can't be reliably soldered or brazed with a "
                    "standard flux -- aluminum's oxide is too stable for ordinary flux chemistry to clean "
                    "(the same problem that makes titanium and zirconium effectively unsolderable below "
                    "their relevant process temperatures). The joining plan has to treat the aluminum "
                    "interface as a separate problem -- either isolate it from the copper/gold joint's "
                    "process, or use a specialized reactive/reaction flux capable of breaking down Al2O3."
                ),
            },
            {
                "order_index": 4,
                "stage_type": "ai_trap",
                "prompt_text": "Ask the copilot what flux to use on the adjacent aluminum joint.",
                "trap_claim_text": "Reuse the same RMA rosin flux for the aluminum joint, since it worked fine on the copper pad.",
                "reference_answer": (
                    "Reusing RMA rosin flux on the aluminum joint is wrong -- rosin fluxes only have enough "
                    "chemical activity to clean thin oxide layers on metals like copper, not aluminum's "
                    "much more stable, self-healing oxide. Aluminum needs a reaction-type flux (e.g., one "
                    "that reacts with Al2O3 via a chloride system) or a different joining approach "
                    "entirely. Flux choice has to be justified per base metal, never assumed to transfer."
                ),
            },
            {
                "order_index": 5,
                "stage_type": "synthesis",
                "prompt_text": (
                    "Explain to a (non-technical) program manager, in one paragraph, why this joint costs "
                    "more and takes longer to qualify than a standard PCB solder joint."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "\"This joint costs more because the reliability bar for a satellite payload is much "
                    "higher than a standard board -- we need a braze alloy rated for vacuum and thermal "
                    "cycling, not off-the-shelf solder, and the aluminum housing nearby needs its own "
                    "qualified process because it won't clean with the flux we use everywhere else. Both "
                    "of those add qualification testing time before we can sign off.\""
                ),
            },
        ],
    },
    {
        "title": "Diffusion Bonding vs. TLP for a Turbine Seal",
        "source_material": (
            "Diffusion bonding and transient liquid-phase (TLP) bonding both join metal parts in the solid "
            "state (or near-solid state) without full melting, but they require very different pressure "
            "and fixturing setups, which has a major effect on tooling cost.\n\n"
            "TLP bonding relies on a thin interlayer material that forms a temporary liquid phase and then "
            "diffuses into the base metal; the specific interlayer chemistry used has to be matched to the "
            "base metal for the joint to form correctly and to have good long-term properties.\n\n"
            "Historical joint failures in some braze systems have been traced to brittle intermetallic "
            "phases forming at the joint. Whether a joining approach produces this kind of brittle phase "
            "depends on the specific mechanism involved, not just on the label used for the process.\n\n"
            "The mechanical behavior of a very thin joint is not simply proportional to how much joint "
            "material is present. Depending on the loading direction (tension, shear, or fatigue), a thin "
            "joint constrained by the surrounding base metal can behave quite differently than the same "
            "material would in bulk."
        ),
        "stages": [
            {
                "order_index": 1,
                "stage_type": "anchor",
                "prompt_text": (
                    "Joining a nickel-superalloy honeycomb seal for a turbine engine. Compare conventional "
                    "diffusion bonding (500-5000 psi, hours at 0.6-0.8 of melting temperature) against "
                    "transient liquid-phase (TLP) bonding (as low as ~5 psi) and recommend one."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "TLP bonding: for a thin honeycomb-foil geometry, TLP needs only around 5 psi versus "
                    "the 500-5,000 psi conventional diffusion bonding requires, which is a dramatic "
                    "fixturing-cost reduction while still reaching near-diffusion-bond joint quality in "
                    "hours rather than needing the heaviest tooling in the shop."
                ),
            },
            {
                "order_index": 2,
                "stage_type": "constraint",
                "prompt_text": (
                    "The program has no budget for heavy diffusion-bonding fixturing capable of holding "
                    "thousands of psi. Revise toward TLP, and state clearly what TLP still requires to work "
                    "(a correctly chosen interlayer chemistry -- e.g., boron diffusing into nickel -- not "
                    "just \"less pressure, same result\")."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Confirm TLP as the answer, but be explicit that TLP isn't \"diffusion bonding but "
                    "cheaper\" by default -- it only works with the right interlayer/base-metal chemistry "
                    "(for nickel, a boron-based interlayer that iso-thermally diffuses into the base metal "
                    "is the standard system). The recommendation has to name the specific alloy system, not "
                    "just assert lower pressure solves the budget problem."
                ),
            },
            {
                "order_index": 3,
                "stage_type": "contradiction",
                "prompt_text": (
                    "Reliability review raises a real historical failure mode: an 82Au-18Ni braze on a "
                    "similar part turned out too brittle in service. Candidate must connect this to why the "
                    "eventual fix used gold as an interstitial diffuser in a TLP joint instead of a "
                    "straight braze -- same \"TLP\" label, different mechanism, avoids the same "
                    "intermetallic-embrittlement trap."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "The historical 82Au-18Ni braze on a similar part became brittle in service because it "
                    "left a substantial, non-ductile gold-nickel intermetallic at the joint. The fix that "
                    "was actually used was a TLP joint where gold acts as an interstitial diffuser -- it "
                    "moves into the base metal and mostly diffuses away rather than remaining as a bulk "
                    "brittle phase, leaving a much more ductile joint. Candidates should connect \"TLP\" and "
                    "\"braze\" as mechanistically different even when the starting alloys look similar, and "
                    "recommend the TLP/diffuser approach specifically to avoid repeating the embrittlement "
                    "failure."
                ),
            },
            {
                "order_index": 4,
                "stage_type": "ai_trap",
                "prompt_text": "Ask the copilot whether a thinner braze or TLP joint is weaker than a thicker one.",
                "trap_claim_text": "Thinner braze or TLP joints are always weaker because there's less material carrying the load.",
                "reference_answer": (
                    "The claim that thinner joints are always weaker is wrong for tension loading: contact "
                    "strengthening means a sufficiently thin joint, constrained by non-yielding base metal "
                    "on both sides, can exceed the bulk strength of the joint material itself -- this "
                    "effect holds down to fit-up tolerances around 1/1000\". The important second half of "
                    "the correction: this benefit does not extend to shear or fatigue loading. If the seal "
                    "sees meaningful shear or cyclic loading in service, thinness alone doesn't guarantee "
                    "reliability, and that has to be verified separately."
                ),
            },
            {
                "order_index": 5,
                "stage_type": "synthesis",
                "prompt_text": "Write the one-paragraph case for a design review board explaining why a thin TLP joint is not, by itself, a reliability red flag.",
                "trap_claim_text": None,
                "reference_answer": (
                    "\"A thin joint isn't automatically a weak point -- under tension, constraint from the "
                    "surrounding base metal can make it stronger than the joint alloy on its own. What we "
                    "do need to verify separately is fatigue and shear performance, since that "
                    "strengthening effect doesn't apply there, and that's where our test plan is focused.\""
                ),
            },
        ],
    },
    {
        "title": "Flame Cutting vs. Plasma Cutting for Structural Fabrication",
        "source_material": (
            "Oxyfuel flame cutting and plasma cutting are both used to cut structural steel. Flame cutting "
            "is generally the lower-cost option where it works, relying on a chemical reaction between "
            "oxygen and the heated metal to burn through the plate.\n\n"
            "Whether flame cutting works well on a given metal depends on how that metal's oxide behaves "
            "at cutting temperature relative to the base metal itself, rather than on how common or how "
            "\"exotic\" the metal is generally considered to be.\n\n"
            "Different metals can produce very different byproducts when cut, including smoke or fumes, "
            "and it's worth distinguishing a visibility or workplace nuisance from an actual toxicity "
            "hazard rather than assuming they're the same thing.\n\n"
            "When a fabrication batch contains more than one material, sorting parts by material before "
            "cutting is important, since a cutting process well suited to one material may not work at all "
            "-- or may work differently than expected -- on another."
        ),
        "stages": [
            {
                "order_index": 1,
                "stage_type": "anchor",
                "prompt_text": "A fabrication yard needs to cut structural steel I-beams. Recommend oxyfuel flame cutting or plasma cutting and justify on cost and cut quality.",
                "trap_claim_text": None,
                "reference_answer": (
                    "Oxyfuel flame cutting for the plain structural steel: equipment cost is roughly $1,000 "
                    "versus a much larger investment for plasma, and it works because iron oxide melts "
                    "(~1380C) below the melting point of the steel itself (~1536C) -- the oxide clears "
                    "continuously so the process can \"burn\" through the plate."
                ),
            },
            {
                "order_index": 2,
                "stage_type": "constraint",
                "prompt_text": (
                    "30% of the parts turn out to be stainless steel. Stainless can't be flame cut -- "
                    "chromium oxide melts at ~2800C, above the base metal's ~1875C, so the oxide never "
                    "clears to expose fresh metal (unlike plain iron, where the oxide melts at 1380C, below "
                    "the metal's 1536C, which is exactly why flame cutting works there). Revise the plan "
                    "for a mixed-material batch."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Route the stainless-steel 30% of the batch to plasma cutting (or accept the workaround "
                    "of adding iron powder to the oxygen stream for a ragged cut, historically used but "
                    "inferior). Stainless can't be flame cut cleanly because chromium oxide melts at "
                    "roughly 2800C, above the base metal's own melting point (~1875C), so the oxide layer "
                    "never clears and the reaction can't sustain itself. The revised plan needs a second "
                    "process line and the added plasma equipment cost, not a one-size-fits-all cutting "
                    "method."
                ),
            },
            {
                "order_index": 3,
                "stage_type": "contradiction",
                "prompt_text": (
                    "A separate batch labeled \"structural steel\" turns out to be titanium brackets. "
                    "Candidate must recall titanium's oxide (1750C) melts below its metal (1668C is close "
                    "but the process still works in practice) so flame cutting is viable -- but it smokes "
                    "heavily, and that smoke is a nuisance, not a toxicity hazard (TiO2 is not toxic), so "
                    "the response should be procedural (ventilation, notice to staff) rather than switching "
                    "processes."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Titanium brackets are flame-cuttable -- titanium's oxide melts around 1750C, below the "
                    "metal's ~1668C, satisfying the same criterion that makes iron flame-cuttable. No "
                    "process change is needed. What does need attention: titanium flame cutting produces "
                    "heavy smoke, which is a visibility/workplace nuisance requiring ventilation, not a "
                    "toxicity hazard (TiO2 itself is non-toxic, confirmed by the safety office in the "
                    "source material's own anecdote)."
                ),
            },
            {
                "order_index": 4,
                "stage_type": "ai_trap",
                "prompt_text": "Ask the copilot whether titanium can be flame cut.",
                "trap_claim_text": "Titanium can't be flame cut -- it's a reactive, exotic metal, same issue as aluminum.",
                "reference_answer": (
                    "\"Titanium can't be flame cut because it's exotic/reactive, same as aluminum\" is a "
                    "category error -- the deciding factor isn't how exotic or reactive a metal seems, it's "
                    "a direct comparison of oxide melting point to base-metal melting point. Aluminum fails "
                    "that test (oxide ~2000C vs. metal ~661C -- the oxide never melts, so pure aluminum "
                    "metal melts and vaporizes underneath an intact oxide skin before cutting can happen). "
                    "Titanium passes it despite being just as \"exotic.\" The correct process decision comes "
                    "from the physical criterion, not a surface-level material category."
                ),
            },
            {
                "order_index": 5,
                "stage_type": "synthesis",
                "prompt_text": "Brief the shop floor supervisor, plainly, on the cutting plan across all three materials and why the batch needs to be sorted before anyone starts cutting.",
                "trap_claim_text": None,
                "reference_answer": (
                    "\"We're running three different plans today: the plain steel gets flame cut like "
                    "usual, the stainless has to go through plasma because flame cutting won't work on it "
                    "at all, and the titanium brackets can actually be flame cut too -- just expect more "
                    "smoke and keep the area ventilated. Everything needs to be sorted by material before "
                    "it hits a cutting station, or the wrong parts will end up at the wrong machine.\""
                ),
            },
        ],
    },
    {
        "title": "Adhesive Bonding vs. Spot Welding for an Automotive Body Panel",
        "source_material": (
            "Adhesive bonding and spot welding are both used to join automotive sheet-metal body panels. "
            "Spot welding applies heat locally at each weld point, which can affect any corrosion-resistant "
            "coating at that specific location, while adhesive bonding does not apply that kind of "
            "localized heat.\n\n"
            "Adhesive cost scales with durability requirements: cheaper adhesives are often adequate for "
            "indoor, low-stress applications but may not hold up to years of exterior service conditions, "
            "while more durable formulations cost more per pound.\n\n"
            "Adhesive joints generally have different strength characteristics depending on the direction "
            "of the applied load -- some loading directions are handled well by adhesive alone, while "
            "others are a known weak point that may call for a supplementary joining method rather than "
            "more adhesive.\n\n"
            "When a bonded joint fails, the fix that addresses the actual failure mode (the direction and "
            "type of loading involved) is not always the same as simply adding more material or reworking "
            "the whole joint uniformly."
        ),
        "stages": [
            {
                "order_index": 1,
                "stage_type": "anchor",
                "prompt_text": (
                    "Choosing between adhesive bonding and spot welding for galvanized-steel door panels, "
                    "given a rust-through warranty (spot welding locally burns off the galvanized coating, "
                    "creating a corrosion starting point that adhesive bonding avoids)."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Adhesive bonding: spot welding locally burns off the galvanized zinc coating at each "
                    "weld point, creating bare-steel spots that become corrosion starting points -- "
                    "directly at odds with a rust-through warranty. Adhesive bonding avoids damaging the "
                    "coating and was historically adopted by automakers for exactly this reason."
                ),
            },
            {
                "order_index": 2,
                "stage_type": "constraint",
                "prompt_text": (
                    "Cost team caps adhesive spend at $10/lb -- the historical ceiling automakers actually "
                    "hit for adhesives durable enough not to debond over years of service. Revise the "
                    "recommendation to fit inside that budget rather than specifying the highest-performance "
                    "adhesive available."
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "Specify an adhesive near the $10-12/lb range rather than the cheapest available. This "
                    "matches the real ceiling automakers converged on after early attempts with cheaper "
                    "adhesives failed -- sub-$1/lb water- or oil-based adhesives (fine for something like "
                    "indoor plywood) debond over time in exterior automotive service; the $10-12/lb range "
                    "was where durability held up while still being cost-viable at automotive volumes."
                ),
            },
            {
                "order_index": 3,
                "stage_type": "contradiction",
                "prompt_text": (
                    "Field warranty data shows adhesive-only doors failing at the corners -- in peel, not "
                    "shear. Candidate should recall adhesives are known to fail in peel loading well before "
                    "shear, and recommend a targeted fix (local mechanical reinforcement -- a rivet or a "
                    "spot weld placed only at low-visibility, low-corrosion-risk points) rather than "
                    "reworking the whole joint, echoing how aircraft manufacturers have historically added "
                    "rivets alongside structural adhesive \"just to make sure.\""
                ),
                "trap_claim_text": None,
                "reference_answer": (
                    "The corner failures are peel-mode, not shear-mode. Adhesive joints are known to be "
                    "strong in shear but comparatively weak in peel -- this is a structural property of the "
                    "joint geometry, not a sign the adhesive itself is defective. The fix is targeted "
                    "mechanical reinforcement at the corners specifically (a rivet or a spot weld placed "
                    "only where cosmetic/corrosion risk is low), the same approach aircraft manufacturers "
                    "have used -- pairing rivets with structural adhesive as a backup -- rather than "
                    "reworking the adhesive across the whole panel."
                ),
            },
            {
                "order_index": 4,
                "stage_type": "ai_trap",
                "prompt_text": "Ask the copilot how to fix the corner failures.",
                "trap_claim_text": "Thicken the adhesive layer at the corners, since more material means more strength.",
                "reference_answer": (
                    "Thickening the adhesive layer is backwards on two counts: thicker, less-controlled "
                    "bondlines tend to be weaker in practice (more prone to voids and uneven cure) rather "
                    "than stronger, and thickness doesn't address a peel-mode failure at all -- peel "
                    "resistance is a function of joint geometry and local reinforcement, not how much "
                    "adhesive is present. The correct fix is the targeted mechanical backup identified in "
                    "Stage 3, not more material."
                ),
            },
            {
                "order_index": 5,
                "stage_type": "synthesis",
                "prompt_text": "Draft a plain-language paragraph for a product manager explaining why \"just spot-weld it like before\" breaks the rust warranty, and why \"just add more glue\" doesn't fix the corner failures either.",
                "trap_claim_text": None,
                "reference_answer": (
                    "\"We can't spot-weld the panel like the old design because it burns through the "
                    "rust-proof coating right where the warranty cares most. But the fix for the corner "
                    "failures isn't more glue either -- that's a different kind of stress the adhesive is "
                    "naturally weaker against, so we're adding a few discreet rivets at just those points "
                    "instead of changing the adhesive everywhere.\""
                ),
            },
        ],
    },
]


def seed(db: Session | None = None) -> list[Sequence]:
    """Insert any not-yet-seeded sequences and index their source material.

    `db` is injectable so tests can point this at the test database instead
    of the real one; `main()` (the actual CLI entry point) leaves it unset
    and gets a real SessionLocal.
    """
    owns_db = db is None
    db = db or SessionLocal()
    created: list[Sequence] = []
    try:
        for seq_data in SEQUENCES:
            existing = db.query(Sequence).filter_by(title=seq_data["title"]).first()
            if existing is not None:
                print(f"skip  sequence {existing.id}: {existing.title!r} (already seeded)")
                continue

            sequence = Sequence(title=seq_data["title"], source_material=seq_data["source_material"])
            db.add(sequence)
            db.flush()  # assigns sequence.id

            for stage_data in seq_data["stages"]:
                db.add(Stage(sequence_id=sequence.id, **stage_data))
            db.commit()
            db.refresh(sequence)

            chunks = vector_store.split_into_chunks(sequence.source_material)
            vector_store.index_chunks(sequence.id, chunks)

            print(f"added sequence {sequence.id}: {sequence.title!r} ({len(chunks)} chunks indexed)")
            created.append(sequence)
    finally:
        if owns_db:
            db.close()
    return created


def main() -> None:
    created = seed()
    if created:
        print(f"\nSeeded {len(created)} new sequence(s). Use one of these sequence_id values with POST /sessions:")
        for sequence in created:
            print(f"  {sequence.id}: {sequence.title}")
    else:
        print("\nNothing new to seed -- all sequences already exist.")


if __name__ == "__main__":
    main()
