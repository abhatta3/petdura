#!/usr/bin/env python3
"""Background continuous OC deep collector via API (prompt stays open)."""
import time, csv, signal, sys, json, os
from pathlib import Path
import pandas as pd, requests
from playwright.sync_api import sync_playwright
from build_catalog import build_catalog

LOG = Path('/tmp/oc_deep_bg.log')
STATUS = Path('/tmp/oc_deep_bg_status.json')
parquet_path = Path('data/pet_services.parquet')
tsv_path = Path('data/rover_ca_sitters.tsv')
CHECKPOINT_EVERY = 100
MAX_PAGE = 10

existing_ids = set(str(i) for i in pd.read_parquet(parquet_path)['listing_id'].dropna())
all_sitters = {}
if tsv_path.exists():
    with tsv_path.open('r', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            all_sitters[row['listing_id']] = row
            existing_ids.add(row['listing_id'])

FIELDS = ['listing_id','source','provider_name','zip_code','city','state','service_type','description','price_usd','price_unit','rating','review_count','profile_url','search_business_name','verified_status']
added = 0; last_ckpt = 0; stopping = False

def save(reason):
    global last_ckpt
    try:
        with tsv_path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter='\t'); w.writeheader()
            for r in all_sitters.values(): w.writerow(r)
        rep = build_catalog(tsv_path, parquet_path, mode='upsert')
        with LOG.open('a') as f: f.write(f'[CHECKPOINT {reason}] added={added} parquet={rep["final_count"]}\n')
        last_ckpt = added; STATUS.write_text(json.dumps({'added':added,'last_ckpt':last_ckpt,'running':True,'ts':time.time()}))
    except Exception as e:
        with LOG.open('a') as f: f.write(f'[CKPT FAIL {reason}] {e}\n')

def on_sig(s,f):
    global stopping; stopping = True
    with LOG.open('a') as f: f.write(f'[SIG {s}] saving...\n')
signal.signal(signal.SIGINT, on_sig); signal.signal(signal.SIGTERM, on_sig)

OC_ZIPS = ['92602','92603','92604','92605','92606','92607','92608','92609','92610','92611','92612','92613','92614','92615','92616','92617','92618','92619','92620','92621','92622','92623','92624','92625','92626','92627','92628','92629','92630','92631','92632','92633','92634','92635','92636','92637','92638','92639','92640','92641','92642','92643','92644','92645','92646','92647','92648','92649','92650','92651','92652','92653','92654','92655','92656','92657','92658','92659','92660','92661','92662','92663','92664','92665','92666','92667','92668','92669','92670','92671','92672','92673','92674','92675','92676','92677','92678','92679','92680','92681','92682','92683','92684','92685','92686','92687','92688','92689','92690','92691','92692','92693','92694','92695','92696','92697','92698','92699','92700','92701','92702','92703','92704','92705','92706','92707','92708','92709','92710','92711','92712','92713','92714','92715','92716','92717','92718','92719','92720','92721','92722','92723','92724','92725','92726','92727','92728','92729','92730','92731','92732','92733','92734','92735','92736','92737','92738','92739','92740','92741','92742','92743','92744','92745','92746','92747','92748','92749','92750','92751','92752','92753','92754','92755','92756','92757','92758','92759','92760','92761','92762','92763','92764','92765','92766','92767','92768','92769','92770','92771','92772','92773','92774','92775','92776','92777','92778','92779','92780','92781','92782','92783','92784','92785','92786','92787','92788','92789','92790','92791','92792','92793','92794','92795','92796','92797','92798','92799','92800','92801','92802','92803','92804','92805','92806','92807','92808','92809','92810','92811','92812','92813','92814','92815','92816','92817','92818','92819','92820','92821','92822','92823','92824','92825','92826','92827','92828','92829','92830','92831','92832','92833','92834','92835','92836','92837','92838','92839','92840','92841','92842','92843','92844','92845','92846','92847','92848','92849','92850','92851','92852','92853','92854','92855','92856','92857','92858','92859','92860','92861','92862','92863','92864','92865','92866','92867','92868','92869','92870','92871','92872','92873','92874','92875','92876','92877','92878','92879','92880','92881','92882','92883','92884','92885','92886','92887','92888','92889','92890','92891','92892','92893','92894','92895','92896','92897','92898','92899']
SERVICES = [('overnight-boarding','Boarding'),('dog-walking','Dog Walking'),('day-care','Doggy Day Care'),('house-sitting','House Sitting'),('drop-in-visits','Drop-In Visits')]

# Grab session cookies once
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15'
with sync_playwright() as p:
    b = p.chromium.launch(headless=False, args=['--disable-blink-features=AutomationControlled','--no-sandbox','--disable-setuid-sandbox','--window-position=-3000,-3000','--window-size=1280,800','--start-minimized'])
    ctx = b.new_context(user_agent=UA, viewport={'width':1440,'height':900}, locale='en-US')
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    page.goto('https://www.rover.com/search/?service_type=overnight-boarding&location=92602&location_type=zip-code&page=1', wait_until='domcontentloaded', timeout=45000)
    time.sleep(2)
    cookies = ctx.cookies()
    b.close()
s = requests.Session()
s.headers.update({'User-Agent':UA,'Accept':'application/json, text/plain, */*','Referer':'https://www.rover.com/search/','Origin':'https://www.rover.com'})
for c in cookies: s.cookies.set(c['name'],c['value'],domain=c['domain'],path=c['path'])

def fetch_json(slug, z, pg):
    url = (f'https://www.rover.com/api/v7/search-optimized?service_type={slug}&location={z}&location_type=zip-code'
           f'&page={pg}&fulltime_availability=false&monday=false&tuesday=false&wednesday=false&thursday=false'
           f'&friday=false&saturday=false&sunday=false&morning_availability=false'
           f'&midday_availability=false&evening_availability=false&is_initial_search=true')
    r = s.get(url, timeout=15)
    return r.json()

try:
    with open(LOG,'a') as f: f.write('[BG START] session ready; looping pages 2-%d\n'%MAX_PAGE)
    # Continuous loop: rotate services/zips/pages; stop when paused or interrupted
    while not stopping:
        new_this_round = 0
        for slug, sname in SERVICES:
            for z in OC_ZIPS:
                if stopping: break
                # Fetch page 1 to learn page_count for this zip/service (once per combo; cached implicitly by just iterating)
                try:
                    d = fetch_json(slug, z, 1)
                    max_p = min(d.get('page_count', 1), MAX_PAGE)
                except Exception as e:
                    max_p = 2
                    with open(LOG,'a') as f: f.write(f'[BG PAGE1 ERR {sname} {z}]: {str(e)[:60]}\n')
                    continue
                for pg in range(2, max_p+1):
                    if stopping: break
                    try:
                        d = fetch_json(slug, z, pg)
                        arr = d.get('results') or []
                        n_new = 0
                        for sitem in arr:
                            opk = sitem.get('personOpk') or sitem.get('person_opk')
                            if not opk: continue
                            lid = f"rover-{opk}-{slug}"
                            if lid in existing_ids: continue
                            existing_ids.add(lid); added += 1; n_new += 1
                            name = sitem.get('shortName') or sitem.get('short_name') or ''
                            all_sitters[lid] = {
                                'listing_id': lid, 'source': 'Rover', 'provider_name': name,
                                'zip_code': sitem.get('zip') or z, 'city': sitem.get('city') or 'California',
                                'state': (sitem.get('state') or 'CA').upper(), 'service_type': sname,
                                'description': (sitem.get('description') or sitem.get('title') or '').replace('\n',' ').replace('\r',' '),
                                'price_usd': str(sitem.get('price')) if sitem.get('price') is not None else '0',
                                'price_unit': sitem.get('priceUnit') or sitem.get('price_unit') or 'night',
                                'rating': str(sitem.get('ratingsAverage') or sitem.get('rating')) if (sitem.get('ratingsAverage') is not None or sitem.get('rating') is not None) else '0',
                                'review_count': str(sitem.get('reviewsCount') or sitem.get('review_count')) if (sitem.get('reviewsCount') is not None or sitem.get('review_count') is not None) else '0',
                                'profile_url': sitem.get('webUrl') or sitem.get('profile_url') or '',
                                'search_business_name': f"Rover - {name}", 'verified_status': 'True',
                            }
                        if n_new:
                            with open(LOG,'a') as f: f.write(f'{sname} {z} p{pg}: +{n_new} new (total {added})\n')
                        new_this_round += n_new
                        if added - last_ckpt >= CHECKPOINT_EVERY: save('auto')
                    except Exception as e:
                        with open(LOG,'a') as f: f.write(f'ERR BG {sname} {z} p{pg}: {str(e)[:70]}\n')
                    time.sleep(0.5)
                if stopping: break
            if stopping: break
        with open(LOG,'a') as f: f.write(f'[ROUND DONE] added={added} new_this_round={new_this_round}\n')
        STATUS.write_text(json.dumps({'added':added,'last_ckpt':last_ckpt,'running':True,'ts':time.time(),'pg_max':MAX_PAGE}))
        # After one full pass, sleep briefly then loop again (continuous background)
        if not stopping:
            time.sleep(2)
    save('final')
    STATUS.write_text(json.dumps({'added':added,'running':False,'ts':time.time()}))
    with open(LOG,'a') as f: f.write('[BG STOPPED]\n')
except Exception as e:
    with open(LOG,'a') as f: f.write(f'[BG FATAL] {e}\n')
    save('final')
