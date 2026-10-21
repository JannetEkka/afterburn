// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Afterburn pact: pay farmers for not burning crop residue, judged on the burn scar.
/// @notice One contract is one season. A funder deposits the money; a field agent enrols plots;
/// each farmer gets part of the payment upfront (the J-PAL Punjab trial found this lifts compliance
/// by about 10 points). After the season a verifier posts each plot's burn verdict with a hash of
/// its evidence (Sentinel-2 scene IDs, the rule version and the numbers). Anyone can recompute the
/// verdict from public imagery and challenge it within the window. A village bonus is paid only if
/// enough of the village's plots stay clean, so neighbours have a reason to talk each other out of it.
contract AfterburnPact {
    // ---------------------------------------------------------------- roles and terms
    address public immutable funder; // deposits money, closes enrolment, recovers what isn't owed
    // Roles are fixed at deploy, so the funder can't swap in a friendlier verifier mid-season.
    address public immutable enroller; // the cooperative or NGO field agent who signs farmers up
    address public immutable verifier; // runs the open burn-scar pipeline and posts verdicts
    address public immutable arbiter; // settles challenges (a multisig in a real deployment)

    uint256 public immutable ratePerHa; // wei per hectare for a clean plot, upfront slice included
    uint256 public immutable bonusPerHa; // wei per hectare from the village bonus
    uint16 public immutable upfrontBps; // share of the plot payment paid at enrolment
    uint16 public immutable burntThresholdBps; // a plot is burnt if at least this share of it scarred
    uint16 public immutable villageCleanBps; // share of a village's plots that must stay clean for the bonus
    uint64 public immutable challengeWindow; // seconds a verdict stays open to challenge
    uint256 public immutable challengeBond; // wei a challenger stakes
    uint64 public immutable verdictsFrom; // no verdicts before the season ends

    // ---------------------------------------------------------------- state
    enum Status {
        None,
        Enrolled,
        Verdict, // posted, inside its challenge window
        Disputed, // challenged, waiting for the arbiter
        Clean,
        Burnt
    }

    struct Plot {
        address payable farmer;
        bytes32 village;
        uint32 ares; // area in ares (1 ha = 100 ares)
        Status status;
        uint16 burntBps;
        uint64 deadline;
        bool bonusDone; // bonus paid, or released back to the pool
        bytes32 polygonHash; // keccak256 of the plot's GeoJSON polygon; the polygon itself stays with the cooperative
        bytes32 evidenceHash; // keccak256 of the verdict's evidence JSON
    }

    struct Challenge {
        address payable challenger;
        uint16 claimedBps;
        bytes32 evidenceHash;
    }

    struct Village {
        uint32 plots;
        uint32 settled;
        uint32 clean;
        bool bonusUnlocked;
    }

    mapping(uint256 => Plot) public plots;
    mapping(uint256 => Challenge) public challenges;
    mapping(bytes32 => Village) public villages;
    /// @notice Land cell (a 50 m grid square, keyed by its centre) to the plot that holds it, plus one.
    /// A cell can be enrolled once, so the same land can't be paid twice under two names.
    mapping(uint64 => uint256) public cellPlot;

    uint256 public plotCount;
    uint256 public reserved; // owed to enrolled farmers and not yet paid
    bool public enrolmentOpen = true;
    uint256 private locked = 1;

    // ---------------------------------------------------------------- events
    event Funded(address indexed from, uint256 amount);
    event Enrolled(uint256 indexed plotId, address indexed farmer, bytes32 indexed village, uint32 ares, bytes32 polygonHash, uint64[] cells, uint256 upfront);
    event EnrolmentClosed(uint256 plots);
    event VerdictPosted(uint256 indexed plotId, uint16 burntBps, bytes32 evidenceHash, string evidenceURI, uint64 deadline);
    event Challenged(uint256 indexed plotId, address indexed challenger, uint16 claimedBps, bytes32 evidenceHash, string evidenceURI);
    event Resolved(uint256 indexed plotId, bool challengeUpheld, uint16 burntBps);
    event Finalized(uint256 indexed plotId, bool clean, uint256 paid);
    event VillageSettled(bytes32 indexed village, uint32 clean, uint32 plots, bool bonusUnlocked);
    event BonusClaimed(uint256 indexed plotId, uint256 amount);
    event Withdrawn(uint256 amount);

    // ---------------------------------------------------------------- errors
    error NotAllowed();
    error BadTerms();
    error EnrolmentClosedErr();
    error EnrolmentStillOpen();
    error NotEnoughFunds(uint256 available, uint256 needed);
    error CellTaken(uint64 cell, uint256 plotId);
    error WrongStatus(Status status);
    error TooEarly(uint64 at);
    error TooLate(uint64 at);
    error WrongBond(uint256 sent, uint256 required);
    error NoBonus();
    error TransferFailed();

    modifier only(address who) {
        if (msg.sender != who) revert NotAllowed();
        _;
    }

    modifier nonReentrant() {
        if (locked != 1) revert NotAllowed();
        locked = 2;
        _;
        locked = 1;
    }

    struct Terms {
        uint256 ratePerHa;
        uint256 bonusPerHa;
        uint16 upfrontBps;
        uint16 burntThresholdBps;
        uint16 villageCleanBps;
        uint64 challengeWindow;
        uint256 challengeBond;
        uint64 verdictsFrom;
    }

    constructor(address enroller_, address verifier_, address arbiter_, Terms memory t) payable {
        if (t.upfrontBps > 10_000 || t.burntThresholdBps == 0 || t.burntThresholdBps > 10_000 || t.villageCleanBps > 10_000) revert BadTerms();
        funder = msg.sender;
        enroller = enroller_;
        verifier = verifier_;
        arbiter = arbiter_;
        ratePerHa = t.ratePerHa;
        bonusPerHa = t.bonusPerHa;
        upfrontBps = t.upfrontBps;
        burntThresholdBps = t.burntThresholdBps;
        villageCleanBps = t.villageCleanBps;
        challengeWindow = t.challengeWindow;
        challengeBond = t.challengeBond;
        verdictsFrom = t.verdictsFrom;
        if (msg.value > 0) emit Funded(msg.sender, msg.value);
    }

    receive() external payable {
        emit Funded(msg.sender, msg.value);
    }

    // ---------------------------------------------------------------- money views
    function payment(uint32 ares) public view returns (uint256) {
        return (ratePerHa * ares) / 100;
    }

    function upfront(uint32 ares) public view returns (uint256) {
        return (payment(ares) * upfrontBps) / 10_000;
    }

    function bonus(uint32 ares) public view returns (uint256) {
        return (bonusPerHa * ares) / 100;
    }

    /// @notice Money in the contract that no farmer is owed yet.
    function available() public view returns (uint256) {
        return address(this).balance - reserved;
    }

    // ---------------------------------------------------------------- enrolment
    function enrol(address payable farmer, bytes32 village, uint32 ares, bytes32 polygonHash, uint64[] calldata cells)
        external
        only(enroller)
        nonReentrant
        returns (uint256 id)
    {
        if (!enrolmentOpen) revert EnrolmentClosedErr();
        if (ares == 0 || cells.length == 0 || farmer == address(0)) revert BadTerms();
        uint256 owed = payment(ares) + bonus(ares);
        if (available() < owed) revert NotEnoughFunds(available(), owed);

        id = ++plotCount;
        for (uint256 i; i < cells.length; ++i) {
            uint256 holder = cellPlot[cells[i]];
            if (holder != 0) revert CellTaken(cells[i], holder);
            cellPlot[cells[i]] = id;
        }
        plots[id] = Plot(farmer, village, ares, Status.Enrolled, 0, 0, false, polygonHash, bytes32(0));
        villages[village].plots += 1;

        uint256 now_ = upfront(ares);
        reserved += owed - now_;
        emit Enrolled(id, farmer, village, ares, polygonHash, cells, now_);
        _pay(farmer, now_);
    }

    /// @notice Ends sign-ups so each village's plot count is fixed before any plot settles.
    function closeEnrolment() external only(funder) {
        enrolmentOpen = false;
        emit EnrolmentClosed(plotCount);
    }

    // ---------------------------------------------------------------- verdicts and challenges
    function postVerdict(uint256 id, uint16 burntBps, bytes32 evidenceHash, string calldata evidenceURI) external only(verifier) {
        if (block.timestamp < verdictsFrom) revert TooEarly(verdictsFrom);
        if (enrolmentOpen) revert EnrolmentStillOpen();
        if (burntBps > 10_000) revert BadTerms();
        Plot storage p = plots[id];
        if (p.status != Status.Enrolled) revert WrongStatus(p.status);
        p.status = Status.Verdict;
        p.burntBps = burntBps;
        p.evidenceHash = evidenceHash;
        p.deadline = uint64(block.timestamp) + challengeWindow;
        emit VerdictPosted(id, burntBps, evidenceHash, evidenceURI, p.deadline);
    }

    /// @notice Anyone who recomputes a verdict and gets a different answer can stake the bond to dispute it.
    function challenge(uint256 id, uint16 claimedBps, bytes32 evidenceHash, string calldata evidenceURI) external payable {
        Plot storage p = plots[id];
        if (p.status != Status.Verdict) revert WrongStatus(p.status);
        if (block.timestamp >= p.deadline) revert TooLate(p.deadline);
        if (msg.value != challengeBond) revert WrongBond(msg.value, challengeBond);
        if (claimedBps > 10_000) revert BadTerms();
        p.status = Status.Disputed;
        challenges[id] = Challenge(payable(msg.sender), claimedBps, evidenceHash);
        reserved += msg.value; // the bond is held, not spendable
        emit Challenged(id, msg.sender, claimedBps, evidenceHash, evidenceURI);
    }

    /// @notice The arbiter rules on a dispute. If the challenger was right their figure replaces the
    /// verdict and the bond comes back; if not, the bond joins the pool. Either way the plot then settles.
    function resolve(uint256 id, bool upheld) external only(arbiter) nonReentrant {
        Plot storage p = plots[id];
        if (p.status != Status.Disputed) revert WrongStatus(p.status);
        Challenge memory c = challenges[id];
        reserved -= challengeBond;
        if (upheld) p.burntBps = c.claimedBps;
        emit Resolved(id, upheld, p.burntBps);
        _settle(id, p);
        if (upheld) _pay(c.challenger, challengeBond);
    }

    /// @notice Settles an unchallenged verdict once its window has passed. Anyone can call it.
    function finalize(uint256 id) external nonReentrant {
        Plot storage p = plots[id];
        if (p.status != Status.Verdict) revert WrongStatus(p.status);
        if (block.timestamp < p.deadline) revert TooEarly(p.deadline);
        _settle(id, p);
    }

    function claimBonus(uint256 id) external nonReentrant {
        Plot storage p = plots[id];
        if (p.status != Status.Clean || p.bonusDone || !villages[p.village].bonusUnlocked) revert NoBonus();
        p.bonusDone = true;
        uint256 amount = bonus(p.ares);
        reserved -= amount;
        emit BonusClaimed(id, amount);
        _pay(p.farmer, amount);
    }

    /// @notice The funder takes back money nobody is owed, e.g. what burnt plots forfeited.
    function withdrawAvailable(uint256 amount) external only(funder) nonReentrant {
        if (amount > available()) revert NotEnoughFunds(available(), amount);
        emit Withdrawn(amount);
        _pay(payable(funder), amount);
    }

    // ---------------------------------------------------------------- internals
    function _settle(uint256 id, Plot storage p) private {
        if (enrolmentOpen) revert EnrolmentStillOpen();
        bool clean = p.burntBps < burntThresholdBps;
        p.status = clean ? Status.Clean : Status.Burnt;
        uint256 rest = payment(p.ares) - upfront(p.ares);
        reserved -= rest;

        Village storage v = villages[p.village];
        v.settled += 1;
        if (clean) v.clean += 1;
        // a burnt plot never gets the bonus, so its share is free again
        if (!clean) reserved -= bonus(p.ares);
        emit Finalized(id, clean, clean ? rest : 0);
        if (v.settled == v.plots) {
            v.bonusUnlocked = uint256(v.clean) * 10_000 >= uint256(v.plots) * villageCleanBps;
            emit VillageSettled(p.village, v.clean, v.plots, v.bonusUnlocked);
        }
        if (clean) _pay(p.farmer, rest);
    }

    /// @notice If the bonus didn't unlock, the clean plots' reserved bonus goes back to the pool.
    function releaseBonus(uint256 id) external {
        Plot storage p = plots[id];
        Village storage v = villages[p.village];
        if (p.status != Status.Clean || p.bonusDone || v.settled != v.plots || v.bonusUnlocked) revert NoBonus();
        p.bonusDone = true;
        reserved -= bonus(p.ares);
    }

    function _pay(address payable to, uint256 amount) private {
        if (amount == 0) return;
        (bool ok,) = to.call{value: amount}("");
        if (!ok) revert TransferFailed();
    }
}
