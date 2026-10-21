# Afterburn

Punjab's official farm-fire count fell more than 90% between 2021 and 2025. Burnt area fell by about a third. The fires moved to the hours after the satellite passes.

Afterburn checks each field for the burn scar a fire leaves for days, whatever time it was lit. It runs a pay-for-not-burning pact on that check: part of the money upfront, the rest after a clean season, and a village bonus only if every enrolled field stays clean. Every verdict goes on-chain with the exact satellite scenes it came from, so anyone can recompute it from public data and challenge it.

IEEE ClimateChain Global Hackathon 2026 · Track: **Climate Data & Environmental Monitoring**

- Live demo: https://jannetekka.github.io/afterburn (after Pages is switched on)
- Pact on Monad testnet: see [`docs/data/deployment.json`](docs/data/deployment.json)
- Demo video: _link added at submission_

## The problem

Every October and November, farmers in Punjab and Haryana burn paddy straw to clear fields for wheat. The smoke is a large share of Delhi's winter air pollution. For years the official measure has been the count of active fires from NASA's MODIS and VIIRS sensors, which pass over at about 10:30 am and 1:30 pm.

That count says the problem is nearly solved. It isn't. The iFOREST *Stubble Burning Status Report 2025* used geostationary satellites that image every 15 minutes and found that more than 90% of large farm fires in Punjab in 2024 and 2025 started after 3 pm, against about 3% in 2021. Active-fire counts fell over 90% since 2021, while burnt area mapped from Sentinel-2 fell 25–35%. NASA researchers reported the same shift in timing.

So any scheme that pays farmers, or fines them, based on fire counts is now paying for nothing. Payments for not burning do work when they're designed well: in a randomised trial with about 1,700 farmers in 171 Punjab villages, paying part of the reward upfront raised compliance by 10 percentage points over pay-after contracts (Jack, Jayachandran, Kala and Pande, *Money (Not) to Burn*, J-PAL). The missing piece is a check that the fire-timing trick doesn't beat.

## What Afterburn does

1. **Reads the scar, not the flame.** Sentinel-2 (10–20 m, a pass every 2–5 days with three satellites) sees each field before and after. A burnt field has no green crop, turns dark, and its Mid-Infrared Burn Index (MIRBI, the index ISRO's NRSC uses for burnt area) rises to the level of fresh char. The time of day the fire was lit doesn't matter.
2. **Pays farmers through a pact on-chain.** A funder (a state scheme, a CSR budget, a buyer of clean straw) deposits the money. A cooperative enrols fields. Each farmer gets 25% at sign-up, the other 75% after a clean verdict, and a village bonus if every enrolled field in the village stays clean, so neighbours have a reason to talk each other out of it.
3. **Lets anyone check the verdict.** The verifier posts each verdict with the keccak-256 hash of an evidence file: the plot polygon's hash, the Sentinel-2 scene IDs, the rule and its thresholds, and the numbers. `pipeline/recheck.py` refetches those scenes from the public catalogue, reruns the rule and compares hashes. A mismatch, or a different reading of the images, is grounds for a challenge during the 72-hour window.
4. **Talks to farmers in Punjabi.** Each verdict produces a short WhatsApp-style message in Punjabi and English, written by Gemini from the verdict's facts only.

## Results on this season's data

Study area: 80 × 52 km of Amritsar, Tarn Taran and Kapurthala districts (lat 31.15–31.62 N, lon 74.65–75.45 E), the densest fire cluster in Indian Punjab this week. Sentinel-2 passes of Sep 23, Oct 3, Oct 13 and Oct 18, 2026. The Sep 25 and Oct 8 passes were skipped as cloudy or hazy.

| Interval | Burnt area found by the scar rule |
|---|---|
| Sep 23 → Oct 3 | 4,824 ha |
| Oct 3 → Oct 13 | 7,836 ha |
| Oct 13 → Oct 18 | 11,303 ha |
| Season so far | 23,963 ha |

Between the Oct 13 and Oct 18 passes:
- the rule found 5,585 burnt patches (8,528 ha on fields seen clearly on both dates)
- VIIRS logged 125 fire detections over the same fields
- 2.9% of the patches have a VIIRS detection within 375 m
- on Oct 18 at 11:20 IST, Sentinel-2 caught 160 fields actually in flames; only 8% of them had a VIIRS detection within 1 km that day

**Validation against an independent sensor.** VIIRS is a different satellite on a different schedule, so it's a fair check. Inside the 375 m footprint of each VIIRS detection, the rule calls 18.9% of the harvested land newly burnt. On random harvested land the figure is 5.6%. That's a 3.4× lift ([`docs/data/validation.json`](docs/data/validation.json), from [`experiments/validate.py`](experiments/validate.py)).

**What we tried that didn't make it.** A positive-unlabeled gradient-boosting model, trained on fields Sentinel-2 caught in flames, scored a 2.5× lift against the rule's 3.7× in the same comparison ([`experiments/pu_model.py`](experiments/pu_model.py), [`experiments/pu_result.json`](experiments/pu_result.json)). The rule also has the property the pact needs: it's a dozen published thresholds, so anyone can recompute a verdict exactly. So the rule makes the verdicts.

## The demo pact

24 real fields, cut from the 10 m imagery, in three villages. They are real fields and their verdicts are real, but nobody enrolled them: the farmers, their payout addresses and the enrolment are simulated. The villages aren't named here on purpose. Stubble burning carries fines, and a verdict from an imperfect detector shouldn't point at a real family.

| Village | Fields | Burnt (≥ 20% of the field scarred) | Bonus |
|---|---|---|---|
| A, Kapurthala district | 8 | 0 | paid |
| B, Tarn Taran district | 8 | 1 | lost |
| C, Kapurthala district | 8 | 3 | lost |

The contract is [`contracts/contracts/AfterburnPact.sol`](contracts/contracts/AfterburnPact.sol). One deployment is one season.

| Step | Who | What happens on-chain |
|---|---|---|
| Fund | funder | deposit; the contract won't promise money it doesn't hold |
| Enrol | cooperative | records the plot's polygon hash, area and 50 m land cells; pays 25% to the farmer; reserves the rest and the bonus share. A land cell can be enrolled once, so the same field can't be paid twice under two names |
| Close enrolment | funder | fixes each village's plot count before anything settles |
| Post verdict | verifier | the share of the field scarred, the evidence hash and its URL; opens the challenge window |
| Challenge | anyone | stakes a bond with a counter-claim and its own evidence hash |
| Resolve | arbiter | upholds (the challenger's figure replaces the verdict, bond returned) or rejects (bond joins the pool) |
| Finalize | anyone | after the window: a clean plot gets its remaining 75%; a burnt plot gets nothing more and its money is freed |
| Bonus | anyone | once every plot in a village has settled: paid to each clean plot if all stayed clean, otherwise returned to the pool |
| Withdraw | funder | only money no farmer is owed |

Roles are fixed at deploy, so a funder can't swap in a friendlier verifier mid-season. The demo uses a 10-minute challenge window instead of 72 hours, so the whole season fits in one session. It also runs one deliberately wrong challenge: a watcher claims the most clearly burnt field was clean, and the arbiter rejects it.

Tests: `cd contracts && npm install && npx hardhat test` (13 passing).

## Recheck a verdict yourself

```bash
pip install -r requirements.txt
python pipeline/recheck.py docs/evidence/plot-19.json
# or straight from the site and the chain:
python pipeline/recheck.py https://jannetekka.github.io/afterburn/evidence/plot-19.json --pact <address> --plot 19
```

It prints the recomputed share of the field scarred, the dates it burned between, and the evidence hash next to the file's and the chain's. All 24 demo verdicts match.

## The burn-scar rule

[`pipeline/burnscar.py`](pipeline/burnscar.py), rule version 2. Between a pixel's last clear view and the next one:

| Test | Threshold | Why |
|---|---|---|
| NDVI after | < 0.35 | no green crop left |
| MIRBI rise | ≥ 0.25 | char brightens the 2.2 µm band against the 1.6 µm band |
| MIRBI after | ≥ 1.6 | char level: the 10th percentile of fields next to fires Sentinel-2 caught burning. Ploughed wet soil also darkens but stays near 1.5 |
| SWIR-1 drop | ≥ 0.02 | the field got darker in shortwave infrared |
| Visible after | ≤ 0.10 | dark |
| NIR after | ≤ 0.25 | dark |
| Patch | 3×3 median, ≥ 10 pixels (0.4 ha) | ignores single noisy pixels |

Only pixels the Sentinel-2 scene classification marks clear are used. A whole pass is skipped if the darkest tenth of its pixels is brighter than 0.05 in blue, which is how smoke haze shows up. A plot counts as burnt when at least 20% of it scarred over the season.

Fires Sentinel-2 catches in flames come from a second test: SWIR-2 at least 1.5× SWIR-1 and above NIR. Spots that burn on several passes are brick kilns and are dropped.

## Data model

**Evidence file** (`docs/evidence/plot-N.json`, hashed with keccak-256 over its canonical JSON):
- the plot polygon (lon/lat, 6 decimals) and its hash
- the area in ares
- the computation window, snapped to the Sentinel-2 20 m grid with a 200 m margin
- each Sentinel-2 scene ID with its date
- the full rule with its thresholds and rule ID
- pixel counts, the burnt share in basis points, and the dates it burned between

**On-chain**, per plot:
- farmer address and village ID
- area
- status: Enrolled → Verdict → (Disputed) → Clean / Burnt
- burnt share
- challenge deadline
- polygon hash and evidence hash

The polygon itself stays with the cooperative. Per land cell: the plot that holds it. Per village: plots, settled, clean, bonus unlocked.

## Run it

```bash
pip install -r requirements.txt
cd pipeline
python run_season.py      # fetch new passes and VIIRS detections, map the scars, export the site's layers
python fields.py          # (once) segment the three village windows into fields; see plots.py for the windows
python plots.py           # judge the demo fields, write docs/data/plots.json and docs/evidence/
python chips.py           # before/after images for the site
python notices.py         # Punjabi + English messages (needs GEMINI_API_KEY)
python ../experiments/validate.py
cd ../contracts && npm install && AFTERBURN_KEY=0x... npx hardhat run scripts/demo.js --network monadTestnet
```

Sentinel-2 L2A comes from the Earth Search STAC catalogue on AWS Open Data and is read with byte-range requests, so a 40 km box costs a few MB. Fire detections come from the NASA FIRMS 7-day files (no key needed).

## What it can't do yet

- **It misses fields ploughed right after burning.** A field burnt and ploughed within a day or two, before the next clear pass, can look like ordinary ploughed soil. The rule is tuned to avoid false "burnt" verdicts, since those take money from a farmer who did the right thing, so it misses some burns. The challenge window is where a missed burn gets raised, for example with a geostationary or commercial image.
- **Accuracy per field is unproven at scale.** The lift against VIIRS shows the rule finds burns, but it isn't a field-level accuracy figure. The best published Sentinel-2 model for Punjab burn patches (a CNN, Anand et al., *Remote Sensing* 2025) reports a Dice score of 0.64. A real pilot needs ground visits on a sample of fields.
- **Clouds and haze cost passes.** Two of six October passes were unusable here. A season has enough passes, but a verdict can rest on fewer looks than you'd like, and the evidence file records how many.
- **The arbiter is one address in the demo.** In a real season it would be a multisig of the funder, a farmers' union and an independent scientist.
- **Money is testnet MON.** A real pilot would pay in rupees through a stablecoin and a UPI off-ramp, or keep the pact as a public ledger and pay through the existing direct-benefit-transfer system.
- **The Punjabi notices haven't been checked by a native speaker.**

## Sources

- iFOREST, *Stubble Burning Status Report 2025* (Dec 2025): fire timing after 3 pm, fire counts vs burnt area.
- NASA (H. Jethva) analysis of GEO-KOMPSAT-2A data on later-day burning, reported Dec 2025.
- Jack, Jayachandran, Kala, Pande, *Money (Not) to Burn: Payments for Ecosystem Services to Reduce Crop Residue Burning*, J-PAL / NBER working paper.
- Anand et al., deep learning for crop-residue burn detection in Punjab from Sentinel-2, *Remote Sensing* 17(6), 2025.
- Copernicus Sentinel-2 L2A via Element 84 Earth Search; NASA FIRMS VIIRS active fires (S-NPP, NOAA-20, NOAA-21).

## How this was built

Jannet Ekka built this with Claude Code (Anthropic) as a coding assistant, for the IEEE ClimateChain Global Hackathon 2026. Gemini writes the farmer notices.

MIT licence.
