"""Experiment: can a learned model beat the transparent rule? (It couldn't, so the rule makes the verdicts.)

Labels come from Sentinel-2 itself: fields next to pixels it caught in flames at its 11:20 IST pass. Everything else
is unlabeled, not "unburnt", because most fires are never seen burning, so the model is trained positive-vs-unlabeled
(Elkan & Noto 2008). Whether a fire is caught in flames depends on when it was lit, not on what its scar looks like,
which is the condition positive-unlabeled learning needs.

Both are scored the same way: at the same share of harvested land flagged, how much more burnt land does each find
inside VIIRS fire footprints (an independent satellite at other hours) than on random harvested land?
"""
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from sklearn.ensemble import HistGradientBoostingClassifier

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipeline"))
import burnscar as bs  # noqa: E402
import validate  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def feats(pre, post):
    a, b = bs.indices(post), bs.indices(pre)
    with np.errstate(invalid="ignore", divide="ignore"):
        f = [a["MIRBI"] - b["MIRBI"], b["S1"] - a["S1"], b["NIR"] - a["NIR"], b["VIS"] - a["VIS"], a["VIS"], a["NIR"], a["S1"], a["MIRBI"],
             post["B12"], post["B04"] / np.maximum(post["B02"], 1e-3)]
    return np.dstack(f).astype(np.float32)


def domain(pre, post):
    return bs.clear(pre) & bs.clear(post) & (bs.indices(post)["NDVI"] < bs.RULE["harvested_ndvi_max"])


def main():
    S = {d: dict(np.load(f"{ROOT}/data/s2_{d}.npz")) for d in ["2026-09-23", "2026-10-03", "2026-10-13", "2026-10-18"]}
    rng = np.random.default_rng(0)
    Xp, Xu = [], []
    # flames at the middle pass; judge the field on the passes either side
    for pre, mid, post in [("2026-09-23", "2026-10-03", "2026-10-13"), ("2026-10-03", "2026-10-13", "2026-10-18")]:
        fl = bs.flames(S[mid])
        o = np.zeros_like(fl)
        for d, z in S.items():
            if d != mid:
                o |= bs.flames(z)
        fl &= ~ndi.binary_dilation(o, iterations=2)  # spots that burn on several passes are brick kilns
        X = feats(S[pre], S[post])
        D = domain(S[pre], S[post]) & np.all(np.isfinite(X), axis=2)
        p = ndi.binary_dilation(fl, iterations=2) & D
        u = D & ~ndi.binary_dilation(fl, iterations=3)
        Xp.append(X[p])
        ui = np.flatnonzero(u.ravel())
        Xu.append(X.reshape(-1, X.shape[2])[rng.choice(ui, 80000, replace=False)])
    Xp, Xu = np.vstack(Xp), np.vstack(Xu)
    idx = rng.permutation(len(Xp))
    k = len(Xp) // 5
    hold, tr = Xp[idx[:k]], Xp[idx[k:]]
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=80, l2_regularization=2.0, random_state=0)
    clf.fit(np.vstack([tr, Xu]), np.r_[np.ones(len(tr)), np.zeros(len(Xu))], sample_weight=np.r_[np.full(len(tr), len(Xu) / len(tr)), np.ones(len(Xu))])
    c = float(clf.predict_proba(hold)[:, 1].mean())

    pre, post = S["2026-10-13"], S["2026-10-18"]
    rule, _ = bs.burnt_between(pre, post)
    X = feats(pre, post)
    D = domain(pre, post) & np.all(np.isfinite(X), axis=2)
    g = np.zeros(D.shape, np.float32)
    g[D] = clf.predict_proba(X[D])[:, 1] / c
    rate = rule[D].mean()
    thr = np.quantile(g[D], 1 - rate * 1.2)  # post-processing trims a little, so start slightly above the rule's rate
    model = ndi.median_filter((g >= thr).astype(np.uint8), 3).astype(bool)
    lab, n = ndi.label(model)
    model = np.r_[False, ndi.sum(model, lab, range(1, n + 1)) >= bs.RULE["min_patch_px"]][lab]
    res = {"positives": int(len(Xp)), "unlabeled": int(len(Xu)), "elkan_noto_c": round(c, 3), "rule_id": bs.RULE_ID}
    for name, m in [("rule", rule), ("pu_model", model)]:
        res[name] = {"harvested_flagged": round(float(m[D].mean()), 3), **validate.lift(m, D, "2026-10-13", "2026-10-18")}
    print(json.dumps(res, indent=1))
    json.dump(res, open(f"{ROOT}/experiments/pu_result.json", "w"), indent=1)


if __name__ == "__main__":
    main()
