#!/usr/bin/env python3
import urllib.request, json
req = urllib.request.Request("http://127.0.0.1:5050/api/catalog")
with urllib.request.urlopen(req, timeout=5) as resp:
    d = json.load(resp)
    z = d.get('zip_codes', [])
    print('Type:', type(z))
    print('Count:', len(z))
    if z:
        r = z[0]
        print('First zip keys:', list(r.keys()))
        print('Zip:', r.get('zip_code'), r.get('city'), r.get('state'))
        print('Sources:', json.dumps(r.get('sources', {}), indent=2)[:400])
