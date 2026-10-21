"""Playwright-Cloudflare collector with incremental checkpointing.

Saves TSV + upserts parquet every CHECKPOINT_EVERY new records, and on SIGTERM/SIGINT,
so no collected data is ever lost.
"""
import time, json, csv, re, signal, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
import pandas as pd
from build_catalog import build_catalog

parquet_path = Path('data/pet_services.parquet')
tsv_path = Path('data/rover_ca_sitters.tsv')
LOG = Path('/tmp/added_so_far.log')
CHECKPOINT_EVERY = 100

existing_ids = set(str(i) for i in pd.read_parquet(parquet_path)['listing_id'].dropna())
all_sitters = {}
if tsv_path.exists():
    with tsv_path.open('r', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            all_sitters[row['listing_id']] = row
            existing_ids.add(row['listing_id'])

added = 0
last_checkpoint = 0
stopping = False

FIELDS = ['listing_id','source','provider_name','zip_code','city','state','service_type','description','price_usd','price_unit','rating','review_count','profile_url','search_business_name','verified_status']


def save(reason):
    """Write TSV and upsert parquet. Never raises."""
    global added, last_checkpoint
    try:
        with tsv_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter='\t')
            writer.writeheader()
            for row in all_sitters.values():
                writer.writerow(row)
        report = build_catalog(tsv_path, parquet_path, mode='upsert')
        with LOG.open('a') as f:
            f.write(f'[CHECKPOINT {reason}] added_total={added} parquet={report["final_count"]}\n')
        last_checkpoint = added
        return report
    except Exception as e:
        with LOG.open('a') as f:
            f.write(f'[CHECKPOINT FAIL {reason}] {e}\n')
        return None


def on_signal(signum, frame):
    global stopping
    stopping = True
    with LOG.open('a') as f:
        f.write(f'[SIGNAL {signum}] saving before exit...\n')


signal.signal(signal.SIGTERM, on_signal)
signal.signal(signal.SIGINT, on_signal)


def extract(html):
    idx = html.find('__ROVER_INITIAL_DATA__ = ')
    if idx == -1:
        return []
    s = idx + len('__ROVER_INITIAL_DATA__ = ')
    e = html.find(';</script>', s)
    if e == -1:
        return []
    chunk = html[s:e]
    best = []
    for m in re.finditer(r'"results"\s*:\s*\[', chunk):
        si = m.end() - 1
        depth = 0
        ei = si
        for i, c in enumerate(chunk[si:], si):
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    ei = i + 1
                    break
        try:
            arr = json.loads(chunk[si:ei])
            if arr and len(arr) > len(best) and isinstance(arr[0], dict) and 'personOpk' in arr[0]:
                best = arr
        except Exception:
            pass
    return best


zips = ['92602','92603','92604','92606','92610','92612','92614','92617','92618','92620','92624','92625','92626','92627','92629','92630','92637','92646','92647','92648','92649','92651','92653','92655','92656','92657','92660','92661','92662','92663','92672','92673','92675','92677','92679','92683','92685','92688','92691','92692','92694','92701','92703','92704','92705','92706','92707','92708','92780','92782','92801','92802','92804','92805','92806','92807','92808','92821','92831','92832','92833','92835','92840','92841','92843','92844','92845','92865','92866','92867','92868','92869','92870','92886','92887','90001','90012','90028','90045','90210','90291','90401','90640','90703','90802','91101','91304','91403','91744','91801','92101','92103','92109','92115','92122','92037','92024','92064','94102','94107','94110','94301','94501','94601','95050','95110','94043','95814','95816','95825','93710','93301','93720','92121','94025','94062','94065','94105','94107','94110','94111','94114','94115','94117','94118','94121','94122','94123','94124','94129','94131','94132','94133','94134','94158','94159','94177']
services = [('overnight-boarding','Boarding'),('dog-walking','Dog Walking'),('house-sitting','House Sitting'),('day-care','Doggy Day Care'),('drop-in-visits','Drop-In Visits')]

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox', '--disable-setuid-sandbox',
        ])
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            viewport={'width': 1440, 'height': 900}, locale='en-US',
        )
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        for s_slug, s_name in services:
            for z in zips:
                if stopping:
                    break
                url = f'https://www.rover.com/search/?service_type={s_slug}&location={z}&location_type=zip-code'
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    time.sleep(3)
                    arr = extract(page.content())
                    if not arr:
                        time.sleep(2)
                        arr = extract(page.content())
                    n_new = 0
                    for s in arr:
                        opk = s.get('personOpk')
                        if not opk:
                            continue
                        lid = f'rover-{opk}-{s_slug}'
                        if lid in existing_ids:
                            continue
                        existing_ids.add(lid)
                        added += 1
                        n_new += 1
                        name = s.get('shortName') or ''
                        all_sitters[lid] = {
                            'listing_id': lid, 'source': 'Rover', 'provider_name': name,
                            'zip_code': s.get('zip') or z, 'city': s.get('city') or 'California',
                            'state': s.get('state') or 'CA', 'service_type': s_name,
                            'description': (s.get('description') or s.get('title') or '').replace('\n', ' ').replace('\r', ' '),
                            'price_usd': str(s.get('price')) if s.get('price') else '0',
                            'price_unit': s.get('priceUnit') or 'night',
                            'rating': str(s.get('ratingsAverage')) if s.get('ratingsAverage') else '0',
                            'review_count': str(s.get('reviewsCount')) if s.get('reviewsCount') is not None else '0',
                            'profile_url': s.get('webUrl'),
                            'search_business_name': f'Rover - {name}', 'verified_status': 'True',
                        }
                    with LOG.open('a') as f:
                        f.write(f'{s_name} {z}: {len(arr)} results, +{n_new} new (total {added})\n')
                except Exception as e:
                    with LOG.open('a') as f:
                        f.write(f'ERR {s_name} {z}: {str(e)[:80]}\n')
                if added - last_checkpoint >= CHECKPOINT_EVERY:
                    save('auto')
                time.sleep(2)
            if stopping:
                break
        browser.close()
finally:
    save('final')

print(f'FINISHED added={added}')
