"""Recompute a verdict from public imagery and compare it with the one on-chain.

    python pipeline/recheck.py docs/evidence/plot-23.json
    python pipeline/recheck.py https://jannetekka.github.io/afterburn/evidence/plot-23.json --pact 0x... --plot 23

It reads the evidence file, fetches exactly the Sentinel-2 scenes it lists for the plot's window from the public
Earth Search catalogue, reruns the rule, rebuilds the evidence and hashes it. If the hash matches the one the
verifier posted, the verdict stands on public data. If it doesn't, you have grounds to challenge.
"""
import argparse
import json
import sys
import urllib.request

import s2
import burnscar as bs
import verdict as vd

RPC = "https://testnet-rpc.monad.xyz"


def onchain_evidence_hash(pact, plot):
    sel = vd.keccak256(b"plots(uint256)")[2:10]
    data = "0x" + sel + hex(plot)[2:].rjust(64, "0")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": pact, "data": data}, "latest"]}).encode()
    res = json.load(urllib.request.urlopen(urllib.request.Request(RPC, body, {"content-type": "application/json"}), timeout=30))["result"]
    words = [res[2 + 64 * i: 2 + 64 * (i + 1)] for i in range((len(res) - 2) // 64)]
    return "0x" + words[8], int(words[4], 16)  # evidenceHash, burntBps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("evidence")
    ap.add_argument("--pact")
    ap.add_argument("--plot", type=int)
    a = ap.parse_args()
    src = a.evidence
    raw = urllib.request.urlopen(src, timeout=30).read() if src.startswith("http") else open(src, "rb").read()
    ev = json.loads(raw)
    if ev["rule_id"] != bs.RULE_ID:
        sys.exit(f"evidence uses rule {ev['rule_id']}, this code is rule {bs.RULE_ID}")

    poly = vd.to_utm(ev["polygon"])
    win = vd.window(poly)
    print(f"plot {ev['plot']}: {ev['ares']} ares, window {win['shape'][1]}x{win['shape'][0]} px at 20 m")
    scenes = []
    for s in ev["scenes"]:
        print("  reading", s["date"], ", ".join(s["items"]))
        scenes.append((s["date"], s["items"], s2.read_grid(s2.items(s["items"]), win)))
    nums = vd.judge(poly, win, scenes)
    mine = vd.canonical(vd.evidence(ev["plot"], ev["polygon"], ev["ares"], win, scenes, nums))
    h_mine, h_file = vd.keccak256(mine), vd.keccak256(raw)
    print(f"recomputed: {nums['burnt_bps'] / 100:.2f}% of the plot scarred"
          + (f", between {nums['burnt_between'][0]} and {nums['burnt_between'][1]}" if nums["burnt_between"] else ""))
    print(f"evidence file says: {ev['burnt_bps'] / 100:.2f}%")
    print("evidence hash, recomputed:", h_mine)
    print("evidence hash, file:      ", h_file)
    ok = h_mine == h_file
    if a.pact:
        h_chain, bps_chain = onchain_evidence_hash(a.pact, a.plot or ev["plot"])
        print("evidence hash, on-chain:  ", h_chain, f"({bps_chain / 100:.2f}%)")
        ok = ok and h_chain == h_mine
    print("MATCH: the verdict stands on public data." if ok else "MISMATCH: you have grounds to challenge this verdict.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
