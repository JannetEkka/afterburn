// Runs the demo season end to end: deploy, enrol the 24 real fields, close enrolment, post the verdicts,
// one frivolous challenge, then settle and pay. Each step is recorded in docs/data/deployment.json so a re-run
// picks up where it stopped.
//
//   AFTERBURN_KEY=0x... npx hardhat run scripts/demo.js --network monadTestnet
//   STEP=settle ... (after the challenge window has passed)
const fs = require("fs");
const path = require("path");
const { ethers, network } = require("hardhat");

const DOCS = path.join(__dirname, "..", "..", "docs");
const OUT = path.join(DOCS, "data", network.name === "monadTestnet" ? "deployment.json" : `deployment-${network.name}.json`);
const KEYS = process.env.AFTERBURN_ROLE_KEYS; // JSON file with role wallets, kept out of the repo
const E = (x) => ethers.parseEther(String(x));

const TERMS = {
  ratePerHa: E(0.004), // testnet MON per hectare, upfront slice included
  bonusPerHa: E(0.002),
  upfrontBps: 2500, // a quarter at enrolment
  burntThresholdBps: 2000, // 20% of the plot scarred = burnt
  villageCleanBps: 10000, // every plot in the village clean = bonus
  challengeWindow: Number(process.env.WINDOW || 600), // 10 minutes for the demo; 72 h in a real season
  challengeBond: E(0.002),
  verdictsFrom: 0,
};

function load() {
  return fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT)) : { network: network.name, chainId: network.config.chainId, txs: {} };
}
function save(s) {
  fs.writeFileSync(OUT, JSON.stringify(s, null, 1));
}

async function roles(funder) {
  let k;
  if (KEYS && fs.existsSync(KEYS)) k = JSON.parse(fs.readFileSync(KEYS));
  else {
    k = Object.fromEntries(["enroller", "verifier", "arbiter", "watcher"].map((r) => [r, ethers.Wallet.createRandom().privateKey]));
    if (KEYS) fs.writeFileSync(KEYS, JSON.stringify(k), { mode: 0o600 });
  }
  const w = Object.fromEntries(Object.entries(k).map(([r, pk]) => [r, new ethers.Wallet(pk, ethers.provider)]));
  return w;
}

// Monad's reserve-balance rule: an account holding under 10 MON gets one value-spending transaction per
// k = 3 blocks; a second one inside the window is included but reverts. So after each one, wait 3 blocks.
async function afterValueSpend(receipt) {
  if (network.name === "hardhat") return;
  while ((await ethers.provider.getBlockNumber()) <= receipt.blockNumber + 3) await new Promise((r) => setTimeout(r, 700));
}

async function send(s, key, txp) {
  const tx = await txp;
  const r = await tx.wait();
  s.txs[key] = r.hash;
  save(s);
  console.log(key.padEnd(18), r.hash, "gas", r.gasUsed.toString());
  return r;
}

async function main() {
  const [funder] = await ethers.getSigners();
  const w = await roles(funder);
  const plots = JSON.parse(fs.readFileSync(path.join(DOCS, "data", "plots.json"))).plots;
  const s = load();
  const step = process.env.STEP || "all";

  if (!s.pact) {
    // gas money for each role
    // gas money for each role, sized to its share of the work (Monad testnet charges the gas limit)
    const gas = { enroller: 0.9, verifier: 0.3, arbiter: 0.05, watcher: 0.05 };
    for (const r of Object.keys(gas)) {
      if (s.txs[`gas:${r}`]) continue;
      const rc = await send(s, `gas:${r}`, funder.sendTransaction({ to: w[r].address, value: E(gas[r]) }));
      await afterValueSpend(rc);
    }
    const ha = plots.reduce((a, p) => a + p.ares, 0) / 100;
    const pool = (TERMS.ratePerHa + TERMS.bonusPerHa) * BigInt(Math.ceil(ha * 100)) / 100n + E(0.002);
    const Pact = await ethers.getContractFactory("AfterburnPact");
    const pact = await Pact.deploy(w.enroller.address, w.verifier.address, w.arbiter.address, TERMS, { value: pool });
    const r = await pact.deploymentTransaction().wait();
    await afterValueSpend(r);
    Object.assign(s, {
      pact: await pact.getAddress(),
      deployTx: r.hash,
      block: r.blockNumber,
      roles: { funder: funder.address, enroller: w.enroller.address, verifier: w.verifier.address, arbiter: w.arbiter.address, watcher: w.watcher.address },
      terms: Object.fromEntries(Object.entries(TERMS).map(([k, v]) => [k, v.toString()])),
      farmers: {},
    });
    save(s);
    console.log("pact", s.pact, "pool", ethers.formatEther(pool));
  }
  const pact = (await ethers.getContractAt("AfterburnPact", s.pact)).connect(funder);

  if (step === "all" || step === "enrol") {
    for (const p of plots) {
      if (s.txs[`enrol:${p.plot}`]) continue;
      // simulated farmers: a fresh address each, nobody holds these keys
      const farmer = s.farmers[p.plot] || ethers.Wallet.createRandom().address;
      s.farmers[p.plot] = farmer;
      await send(s, `enrol:${p.plot}`, pact.connect(w.enroller).enrol(farmer, p.village_id, p.ares, p.polygon_hash, p.cells.map(BigInt)));
    }
    if (await pact.enrolmentOpen()) await send(s, "close", pact.closeEnrolment());
  }

  if (step === "all" || step === "verdicts") {
    for (const p of plots) {
      if (s.txs[`verdict:${p.plot}`]) continue;
      await send(s, `verdict:${p.plot}`, pact.connect(w.verifier).postVerdict(p.plot, p.burnt_bps, p.evidence_hash, p.evidence_uri));
    }
    // A watcher claims the most clearly burnt plot was clean. The imagery says otherwise, so the arbiter
    // will reject it and the bond goes to the pool: challenging costs something when you're wrong.
    const target = plots.filter((p) => p.burnt_bps >= 2000).sort((a, b) => b.burnt_bps - a.burnt_bps)[0];
    if (!s.txs[`challenge:${target.plot}`]) {
      s.challenged = target.plot;
      await send(s, `challenge:${target.plot}`, pact.connect(w.watcher).challenge(target.plot, 0, ethers.id("claim: no fire on this plot"), "", { value: TERMS.challengeBond }));
    }
  }

  if (network.name === "hardhat") {
    // local dry run only: skip past the challenge window
    await network.provider.send("evm_increaseTime", [TERMS.challengeWindow + 1]);
    await network.provider.send("evm_mine", []);
  }

  if (step === "all" || step === "settle") {
    const now = (await ethers.provider.getBlock("latest")).timestamp;
    if (s.challenged && !s.txs[`resolve:${s.challenged}`]) await send(s, `resolve:${s.challenged}`, pact.connect(w.arbiter).resolve(s.challenged, false));
    for (const p of plots) {
      if (s.txs[`finalize:${p.plot}`] || p.plot === s.challenged) continue;
      const pl = await pact.plots(p.plot);
      if (pl.deadline > now) {
        console.log(`plot ${p.plot}: window open until ${new Date(Number(pl.deadline) * 1000).toISOString()}, run STEP=settle later`);
        return;
      }
      await send(s, `finalize:${p.plot}`, pact.finalize(p.plot));
    }
    for (const p of plots) {
      const pl = await pact.plots(p.plot);
      const v = await pact.villages(p.village_id);
      if (pl.status !== 4n || pl.bonusDone) continue;
      if (v.bonusUnlocked) await send(s, `bonus:${p.plot}`, pact.claimBonus(p.plot));
      else await send(s, `release:${p.plot}`, pact.releaseBonus(p.plot));
    }
  }
  console.log("available", ethers.formatEther(await pact.available()), "reserved", ethers.formatEther(await pact.reserved()));
}

main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
