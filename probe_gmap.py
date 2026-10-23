#!/usr/bin/env python3
"""Capture Google Maps tbm=map payload and analyze its JSON structure."""
import time, json, re
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.2.1 Safari/605.1.15")

captured = []
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA, locale="en-US", viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    def on_resp(r):
        try:
            if "tbm=map" in r.url:
                captured.append(r.text())
        except Exception:
            pass

    page.on("response", on_resp)
    page.goto("https://www.google.com/maps/search/pet+services+in+92694",
              wait_until="domcontentloaded", timeout=45000)
    time.sleep(6)
    b.close()

if not captured:
    print("no payload")
    raise SystemExit(1)

raw = captured[0]
open("/tmp/gmap_payload.txt", "w").write(raw)
print("raw len:", len(raw))
body = raw.split("\n", 1)[-1]
data = json.loads(body)
print("top type:", type(data).__name__, "len:", len(data))

# Find arrays of arrays containing a name-like string and coordinates
def find_place_arrays(obj, path="", depth=0, out=None):
    if out is None: out = []
    if depth > 8: return out
    if isinstance(obj, list):
        if len(obj) >= 2 and isinstance(obj[0], str) and isinstance(obj[1], list):
            # heuristic: name + coordinates
            out.append((path, obj))
        for i, v in enumerate(obj[:200]):
            find_place_arrays(v, f"{path}[{i}]", depth+1, out)
    return out

cands = find_place_arrays(data)
print("candidate place arrays:", len(cands))
for path, arr in cands[:12]:
    print(" ", path, "->", json.dumps(arr)[:220])
