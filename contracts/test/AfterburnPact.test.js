const { expect } = require("chai");
const { ethers } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

const E = (x) => ethers.parseEther(String(x));
const V1 = ethers.id("village-1");
const V2 = ethers.id("village-2");
const poly = (n) => ethers.id(`polygon-${n}`);
const DAY = 24 * 3600;

const terms = (over = {}) => ({
  ratePerHa: E(1), // 1 token per hectare
  bonusPerHa: E(0.5),
  upfrontBps: 2500, // a quarter upfront
  burntThresholdBps: 2000, // 20% of the plot scarred = burnt
  villageCleanBps: 10000, // every plot must stay clean for the bonus
  challengeWindow: 3 * DAY,
  challengeBond: E(0.1),
  verdictsFrom: 0,
  ...over,
});

async function deploy(over = {}, fund = E(20)) {
  const [funder, enroller, verifier, arbiter, a, b, c, d, watcher] = await ethers.getSigners();
  const Pact = await ethers.getContractFactory("AfterburnPact");
  const pact = await Pact.deploy(enroller.address, verifier.address, arbiter.address, terms(over), { value: fund });
  return { pact, funder, enroller, verifier, arbiter, farmers: [a, b, c, d], watcher };
}

describe("AfterburnPact", function () {
  it("pays the upfront slice at enrolment and reserves the rest", async function () {
    const { pact, enroller, farmers } = await deploy();
    const f = farmers[0];
    // 2.00 ha: payment 2, upfront 0.5, remainder 1.5, bonus 1
    await expect(pact.connect(enroller).enrol(f.address, V1, 200, poly(1), [11, 12])).to.changeEtherBalance(f, E(0.5));
    expect(await pact.reserved()).to.equal(E(1.5) + E(1));
    expect(await pact.available()).to.equal(E(20) - E(0.5) - E(2.5));
  });

  it("refuses land that is already enrolled, under any name", async function () {
    const { pact, enroller, farmers } = await deploy();
    await pact.connect(enroller).enrol(farmers[0].address, V1, 100, poly(1), [11, 12, 13]);
    await expect(pact.connect(enroller).enrol(farmers[1].address, V2, 100, poly(2), [99, 13]))
      .to.be.revertedWithCustomError(pact, "CellTaken")
      .withArgs(13, 1);
  });

  it("won't promise money it doesn't hold", async function () {
    const { pact, enroller, farmers } = await deploy({}, E(1));
    // 1 ha needs 1 + 0.5 bonus
    await expect(pact.connect(enroller).enrol(farmers[0].address, V1, 100, poly(1), [1])).to.be.revertedWithCustomError(pact, "NotEnoughFunds");
  });

  it("only the enroller enrols and only the verifier posts verdicts", async function () {
    const { pact, enroller, farmers, watcher, funder } = await deploy();
    await expect(pact.connect(watcher).enrol(farmers[0].address, V1, 100, poly(1), [1])).to.be.revertedWithCustomError(pact, "NotAllowed");
    await pact.connect(enroller).enrol(farmers[0].address, V1, 100, poly(1), [1]);
    await pact.connect(funder).closeEnrolment();
    await expect(pact.connect(watcher).postVerdict(1, 0, ethers.ZeroHash, "")).to.be.revertedWithCustomError(pact, "NotAllowed");
  });

  it("waits for enrolment to close and for the season to end", async function () {
    const now = await time.latest();
    const { pact, enroller, verifier, funder, farmers } = await deploy({ verdictsFrom: now + 10 * DAY });
    await pact.connect(enroller).enrol(farmers[0].address, V1, 100, poly(1), [1]);
    await expect(pact.connect(verifier).postVerdict(1, 0, ethers.ZeroHash, "")).to.be.revertedWithCustomError(pact, "TooEarly");
    await time.increase(10 * DAY);
    await expect(pact.connect(verifier).postVerdict(1, 0, ethers.ZeroHash, "")).to.be.revertedWithCustomError(pact, "EnrolmentStillOpen");
    await pact.connect(funder).closeEnrolment();
    await pact.connect(verifier).postVerdict(1, 0, ethers.ZeroHash, "");
  });

  it("pays the remainder on a clean verdict once the challenge window has passed", async function () {
    const { pact, enroller, verifier, funder, farmers, watcher } = await deploy();
    const f = farmers[0];
    await pact.connect(enroller).enrol(f.address, V1, 100, poly(1), [1]);
    await pact.connect(funder).closeEnrolment();
    await pact.connect(verifier).postVerdict(1, 300, ethers.id("evidence"), "evidence/1.json"); // 3% scarred: under threshold
    await expect(pact.connect(watcher).finalize(1)).to.be.revertedWithCustomError(pact, "TooEarly");
    await time.increase(3 * DAY);
    await expect(pact.connect(watcher).finalize(1)).to.changeEtherBalance(f, E(0.75));
    expect((await pact.plots(1)).status).to.equal(4); // Clean
  });

  it("pays nothing more on a burnt verdict and frees the money", async function () {
    const { pact, enroller, verifier, funder, farmers } = await deploy();
    const f = farmers[0];
    await pact.connect(enroller).enrol(f.address, V1, 100, poly(1), [1]);
    await pact.connect(funder).closeEnrolment();
    const before = await pact.available();
    await pact.connect(verifier).postVerdict(1, 6500, ethers.id("evidence"), "");
    await time.increase(3 * DAY);
    await expect(pact.finalize(1)).to.changeEtherBalance(f, 0);
    expect((await pact.plots(1)).status).to.equal(5); // Burnt
    expect(await pact.reserved()).to.equal(0);
    expect(await pact.available()).to.equal(before + E(0.75) + E(0.5));
  });

  it("a challenge the arbiter upholds overturns the verdict and returns the bond", async function () {
    const { pact, enroller, verifier, arbiter, funder, farmers, watcher } = await deploy();
    const f = farmers[0];
    await pact.connect(enroller).enrol(f.address, V1, 100, poly(1), [1]);
    await pact.connect(funder).closeEnrolment();
    await pact.connect(verifier).postVerdict(1, 0, ethers.id("clean"), "");
    await expect(pact.connect(watcher).challenge(1, 8000, ethers.id("scar"), "", { value: E(0.05) })).to.be.revertedWithCustomError(pact, "WrongBond");
    await pact.connect(watcher).challenge(1, 8000, ethers.id("scar"), "ipfs://counter", { value: E(0.1) });
    await expect(pact.finalize(1)).to.be.revertedWithCustomError(pact, "WrongStatus");
    await expect(pact.connect(arbiter).resolve(1, true)).to.changeEtherBalances([watcher, f], [E(0.1), 0]);
    const p = await pact.plots(1);
    expect(p.status).to.equal(5); // Burnt
    expect(p.burntBps).to.equal(8000);
  });

  it("a challenge the arbiter rejects keeps the verdict and the bond joins the pool", async function () {
    const { pact, enroller, verifier, arbiter, funder, farmers, watcher } = await deploy();
    const f = farmers[0];
    await pact.connect(enroller).enrol(f.address, V1, 100, poly(1), [1]);
    await pact.connect(funder).closeEnrolment();
    await pact.connect(verifier).postVerdict(1, 0, ethers.id("clean"), "");
    await pact.connect(watcher).challenge(1, 8000, ethers.id("scar"), "", { value: E(0.1) });
    const avail = await pact.available();
    await expect(pact.connect(arbiter).resolve(1, false)).to.changeEtherBalances([watcher, f], [0, E(0.75)]);
    expect(await pact.available()).to.equal(avail + E(0.1));
  });

  it("no challenges after the window closes", async function () {
    const { pact, enroller, verifier, funder, farmers, watcher } = await deploy();
    await pact.connect(enroller).enrol(farmers[0].address, V1, 100, poly(1), [1]);
    await pact.connect(funder).closeEnrolment();
    await pact.connect(verifier).postVerdict(1, 0, ethers.id("clean"), "");
    await time.increase(3 * DAY);
    await expect(pact.connect(watcher).challenge(1, 8000, ethers.id("scar"), "", { value: E(0.1) })).to.be.revertedWithCustomError(pact, "TooLate");
  });

  async function village(burnt) {
    const ctx = await deploy();
    const { pact, enroller, verifier, funder, farmers } = ctx;
    for (let i = 0; i < 3; i++) await pact.connect(enroller).enrol(farmers[i].address, V1, 100, poly(i), [100 + i]);
    await pact.connect(enroller).enrol(farmers[3].address, V2, 100, poly(9), [200]);
    await pact.connect(funder).closeEnrolment();
    for (let i = 1; i <= 4; i++) await pact.connect(verifier).postVerdict(i, burnt.includes(i) ? 9000 : 0, ethers.id(`e${i}`), "");
    await time.increase(3 * DAY);
    return ctx;
  }

  it("unlocks the village bonus only when every plot has settled clean", async function () {
    const { pact, farmers } = await village([]);
    await pact.finalize(1);
    await pact.finalize(2);
    await expect(pact.claimBonus(1)).to.be.revertedWithCustomError(pact, "NoBonus"); // plot 3 not settled yet
    await expect(pact.finalize(3)).to.emit(pact, "VillageSettled").withArgs(V1, 3, 3, true);
    await expect(pact.claimBonus(1)).to.changeEtherBalance(farmers[0], E(0.5));
    await expect(pact.claimBonus(1)).to.be.revertedWithCustomError(pact, "NoBonus");
  });

  it("one burnt plot costs the whole village its bonus, and the money goes back to the pool", async function () {
    const { pact, funder } = await village([2]);
    for (let i = 1; i <= 4; i++) await pact.finalize(i);
    expect((await pact.villages(V1)).bonusUnlocked).to.equal(false);
    expect((await pact.villages(V2)).bonusUnlocked).to.equal(true);
    await expect(pact.claimBonus(1)).to.be.revertedWithCustomError(pact, "NoBonus");
    await pact.releaseBonus(1);
    await pact.releaseBonus(3);
    await pact.claimBonus(4);
    expect(await pact.reserved()).to.equal(0);
    const all = await pact.available();
    await expect(pact.connect(funder).withdrawAvailable(all)).to.changeEtherBalance(funder, all);
  });

  it("the funder can't take money farmers are owed", async function () {
    const { pact, enroller, funder, farmers } = await deploy({}, E(2));
    await pact.connect(enroller).enrol(farmers[0].address, V1, 100, poly(1), [1]);
    const avail = await pact.available();
    await expect(pact.connect(funder).withdrawAvailable(avail + 1n)).to.be.revertedWithCustomError(pact, "NotEnoughFunds");
  });
});
