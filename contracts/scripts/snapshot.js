// Snapshot the pact's on-chain state into docs/data/chain.json, so the site renders at once and doesn't depend
// on the public RPC answering every visitor; the page still refreshes from the chain when it can.
//   npx hardhat run scripts/snapshot.js --network monadTestnet
const fs = require("fs");
const path = require("path");
const { ethers } = require("hardhat");

const DOCS = path.join(__dirname, "..", "..", "docs", "data");
const retry = async (fn, n = 6) => {
  for (let i = 0; ; i++) {
    try { return await fn(); } catch (e) { if (i >= n) throw e; await new Promise((r) => setTimeout(r, 500 * (i + 1))); }
  }
};

async function main() {
  const dep = JSON.parse(fs.readFileSync(path.join(DOCS, "deployment.json")));
  const plots = JSON.parse(fs.readFileSync(path.join(DOCS, "plots.json"))).plots;
  const pact = await ethers.getContractAt("AfterburnPact", dep.pact);
  const out = { pact: dep.pact, block: await retry(() => ethers.provider.getBlockNumber()), at: new Date().toISOString(), plots: {}, villages: {} };
  out.available = (await retry(() => pact.available())).toString();
  out.reserved = (await retry(() => pact.reserved())).toString();
  for (const p of plots) {
    const r = await retry(() => pact.plots(p.plot));
    out.plots[p.plot] = { farmer: r.farmer, status: Number(r.status), burntBps: Number(r.burntBps), deadline: Number(r.deadline), bonusDone: r.bonusDone, evidenceHash: r.evidenceHash, polygonHash: r.polygonHash };
  }
  for (const v of [...new Set(plots.map((p) => p.village))]) {
    const id = plots.find((p) => p.village === v).village_id;
    const r = await retry(() => pact.villages(id));
    out.villages[v] = { plots: Number(r.plots), settled: Number(r.settled), clean: Number(r.clean), bonusUnlocked: r.bonusUnlocked };
  }
  fs.writeFileSync(path.join(DOCS, "chain.json"), JSON.stringify(out, null, 1));
  console.log("snapshot at block", out.block, Object.values(out.plots).map((p) => p.status).join(""), out.villages);
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
