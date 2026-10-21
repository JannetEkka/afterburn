# Devpost submission: Afterburn

## Project name
Afterburn

## Elevator pitch (under 200 characters)
Punjab's fire count fell 90%, burnt area a third: fires moved past the satellite pass. Afterburn reads the burn scar and pays farmers who don't burn, on-chain and rechecked.

## Track
Climate Data & Environmental Monitoring.

Environmental data is fragmented and hard to verify, and here the official data is also wrong. Afterburn is a climate-data verification system: it turns free Sentinel-2 imagery into per-field burn verdicts that anyone can recompute, and it puts them on-chain so a payment scheme can rely on them.

## About the project

### Inspiration
Every October and November, farmers in Punjab and Haryana burn paddy straw to clear their fields for wheat, and the smoke fills Delhi. The official measure is the count of fires NASA's MODIS and VIIRS satellites see, and it has fallen more than 90% since 2021. Burnt area fell only 25–35%. iFOREST's 2025 report used satellites that image every 15 minutes and found that more than 90% of large fires in 2024 and 2025 started after 3 pm, while the counting satellites pass at 10:30 and 1:30. The fires moved to after the satellite leaves.

Paying farmers not to burn can work. In a J-PAL trial with about 1,700 farmers in 171 Punjab villages, paying part of the money upfront raised compliance by 10 percentage points. What's missing is a check the timing trick doesn't beat.

### What it does
- **Reads the scar, not the flame.** For every clear Sentinel-2 pass, each field is compared with its last clear view. A burnt field has no green crop, turns dark, and its Mid-Infrared Burn Index (the index ISRO's NRSC uses for burnt area) rises to the level of fresh char. The scar lasts for days, whatever hour the fire was lit.
- **Pays farmers through a pact on Monad testnet.** A funder deposits, and a cooperative enrols fields. Each farmer gets 25% at sign-up and the remaining 75% after a clean verdict. A village bonus is paid only if every enrolled field stays clean. Each 50 m square of land can be enrolled once, so the same field can't be paid twice.
- **Lets anyone recheck.** Each verdict is posted with the hash of an evidence file: the field's polygon hash, the exact Sentinel-2 scene IDs, the rule and the numbers. A script refetches those scenes from the public catalogue, reruns the rule and compares hashes. Anyone who gets a different answer can stake a bond and challenge within the window, and an arbiter rules.
- **Talks to farmers in Punjabi.** Each verdict becomes a short WhatsApp-style message in Punjabi and English, written by Gemini from the verdict's facts only.

### Results on this season's data
Study area: 80 × 52 km of Amritsar, Tarn Taran and Kapurthala, using the Sentinel-2 passes of Sep 23, Oct 3, Oct 13 and Oct 18, 2026.
- 23,963 ha of burn scars so far this season.
- Between the Oct 13 and Oct 18 passes the rule found 5,585 scars. Only 2.9% have a VIIRS fire detection within 375 m.
- On Oct 18 at 11:20 IST, Sentinel-2 caught 160 fields actually in flames. Only 8% had a VIIRS detection within 1 km that day.
- **Validation:** inside the footprint of each VIIRS detection, the rule finds 18.9% of harvested land newly burnt, against 5.6% on random harvested land. That's a 3.4× lift, measured against an independent satellite on a different schedule.
- A positive-unlabeled machine-learning model trained on fields Sentinel-2 caught in flames did worse (2.5× against 3.7× in the same test), so the transparent rule makes the verdicts.
- The demo pact ran a whole season on Monad testnet with 24 real fields in three villages. Village A stayed clean and got its bonus. One field burnt in village B and three in village C, so neither village gets the bonus. A deliberately wrong challenge was rejected and its bond went to the pool. All 24 verdicts recheck as a match from fresh public reads.

### Who it's for, how it scales, how easily it's adopted
- **Funders:** state residue-management schemes, CSR budgets, and bio-CNG and biomass plants that need straw collected rather than burnt.
- **Cooperatives and NGOs:** they enrol farmers and help them challenge a verdict.
- **Regulators such as CAQM:** they get a burnt-area figure that doesn't depend on the hour of the fire.
- **Scale:** Sentinel-2 covers all of Punjab and Haryana every 2–5 days for free, and an 80 km area runs in minutes on a laptop, so the cost per field-season is close to zero.
- **Adoption:** payments can stay on India's existing direct-benefit-transfer rails, with the pact as the public ledger they settle against.

### How we built it
- **Data:** Sentinel-2 L2A from the Earth Search catalogue on AWS Open Data, read with byte-range requests on cloud-optimised GeoTIFFs (Python, rasterio, numpy, scipy), and NASA FIRMS VIIRS fire detections. Demo fields were segmented from the 10 m imagery with scikit-image.
- **Contract:** Solidity, with 13 Hardhat tests, deployed to Monad testnet. Evidence files are hashed with keccak-256 over canonical JSON so Python and the contract agree byte for byte.
- **Site:** a static page with Leaflet and ethers.js that reads the pact live from the chain. The farmer notices are written by Gemini.
- **AI disclosure:** Jannet built this with Claude Code (Anthropic) as a coding assistant.

### Challenges we ran into
- **Ploughed fields.** Freshly ploughed wet soil also darkens and lifts the burn index when it goes straight from green crop to bare. A visual check of our first verdicts caught it. Fresh char next to fires Sentinel-2 caught burning never sits below a burn index of 1.6, while wet soil stays near 1.5, so rule version 2 requires the char level.
- **Haze.** Smoke haze in October brightens every pixel and hides the darkening, so hazy passes are detected with a dark-object test and skipped.
- **Reproducibility.** Our first rechecks didn't match: the pipeline judged a field's original polygon, while the recheck used the published one rounded to 6 decimals, a one-pixel difference. Everything is now computed from the published polygon, and all 24 match.
- **Monad's reserve-balance rule.** Our deploy script's second fund transfer reverted, because an account holding under 10 MON gets one value-spending transaction per 3 blocks. The script now waits 3 blocks after each one.

### Accomplishments we're proud of
- A finding on real data from this week: thousands of burn scars that the official fire count never sees.
- A verdict anyone can recompute from public data, with the hash on-chain to compare against.
- Keeping the transparent rule over the fancier model because the numbers said so.

### What we learned
For a payment system, being re-checkable matters more than a few points of accuracy. Farmers, funders and challengers all need to land on the same number from the same public data.

### What's next
- A pilot with one cooperative and one funder for one season, ground-checking a sample of verdicts.
- Geostationary fire data as challenge evidence.
- A multisig arbiter: the funder, a farmers' union and an independent scientist.
- A native speaker's review of the Punjabi notices.

### What it can't do yet
- A field burnt and ploughed before the next clear pass can slip through. The rule leans toward clean, since a false "burnt" verdict takes money from a farmer who did the right thing.
- There's no per-field accuracy figure yet. The best published Punjab model reports a Dice score of 0.64.

## Built with
python, rasterio, numpy, scipy, scikit-image, scikit-learn, sentinel-2, nasa-firms, solidity, hardhat, ethers.js, monad, leaflet, gemini, github-pages

## Links
- Live demo: https://jannetekka.github.io/afterburn
- Code: https://github.com/JannetEkka/afterburn
- Contract on Monad testnet: https://testnet.monadvision.com/address/0xC892d8B3FeB08Cb36c705019B500dd646CcF6b2D
- Video: (YouTube link)

## File upload
`afterburn-deck.pdf` (the pitch deck, 10 slides).
