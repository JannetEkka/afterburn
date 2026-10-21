"""The message each farmer gets after their verdict, in Punjabi and English, written by Gemini from the verdict's
facts only. Most farmers in the pact will read it on WhatsApp, not on a block explorer.

The Punjabi is machine-written and hasn't been checked by a native speaker yet.
"""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key=" + os.environ.get("GEMINI_API_KEY", "")

PROMPT = """You write short WhatsApp messages from a farmers' cooperative in Punjab to its members, about the
crop-residue pact they joined. For each field below, write two versions of the same message: Punjabi in Gurmukhi
script, then English. Plain, warm and respectful. Never accuse or lecture. Use only the facts given for that field;
don't add numbers, names or dates. At most 70 words per version. No greeting by name (we don't have one).
Return one JSON object keyed by plot number: {{"1": {{"pa": "...", "en": "..."}}, ...}}

The cooperative checked every field in satellite images from {first} to {last}. If a member thinks a result is
wrong, the cooperative can file a challenge for them within the 72-hour window, and anyone can recheck the images.
Every message should end by saying so.

Fields:
{fields}
"""


def facts(p, terms, village_clean):
    burnt = p["burnt_bps"] >= terms["burntThresholdBps"]
    upfront = terms["upfrontBps"] // 100
    if burnt:
        a, b = p["burnt_between"]
        result = f"about {p['burnt_bps'] / 100:.0f}% of the field shows a burn scar, which appeared between {a} and {b}."
        money = f"the {upfront}% paid at sign-up is yours to keep; the remaining {100 - upfront}% is not paid this season."
    else:
        result = "no burn scar on the field. Thank you for managing the straw without fire."
        money = f"the remaining {100 - upfront}% of the payment has been sent to you (you received {upfront}% at sign-up)."
    if village_clean:
        bonus = "every enrolled field in the village stayed clean, so the village bonus is unlocked."
    else:
        bonus = "at least one enrolled field in the village burned, so there is no village bonus this season."
    return dict(result=result, money=money, bonus=bonus)


def ask(text):
    body = {"contents": [{"parts": [{"text": text}]}], "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"content-type": "application/json"})
    for attempt in range(4):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=300))
            return json.loads(r["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as e:  # rate limits on the free tier: back off and retry
            print("retry", attempt, e, file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("Gemini didn't answer")


def main():
    d = json.load(open(f"{ROOT}/docs/data/plots.json"))
    terms = {"burntThresholdBps": 2000, "upfrontBps": 2500}
    clean_by_village = {}
    for p in d["plots"]:
        clean_by_village.setdefault(p["village"], True)
        if p["burnt_bps"] >= terms["burntThresholdBps"]:
            clean_by_village[p["village"]] = False
    lines, per = [], {}
    for p in d["plots"]:
        f = facts(p, terms, clean_by_village[p["village"]])
        per[p["plot"]] = f
        lines.append(f"- Plot {p['plot']} in {p['village_name']}, {p['ares'] / 100:.2f} hectares. Result: {f['result']} "
                     f"Money: {f['money']} Village bonus: {f['bonus']}")
    got = ask(PROMPT.format(first=d["season"][0], last=d["season"][-1], fields="\n".join(lines)))
    out = {str(n): {**got[str(n)], "facts": per[n], "model": MODEL} for n in per}
    json.dump(out, open(f"{ROOT}/docs/data/notices.json", "w"), ensure_ascii=False, indent=1)
    print(len(out), "notices;", out[str(d["plots"][-1]["plot"])]["en"])


if __name__ == "__main__":
    main()
