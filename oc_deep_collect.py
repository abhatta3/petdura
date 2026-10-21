"""Orange County deep collector: pages 2+ per zip x service, checkpointed."""
import time, json, csv, re, signal
from pathlib import Path
from playwright.sync_api import sync_playwright
import pandas as pd
from build_catalog import build_catalog

parquet_path = Path('data/pet_services.parquet')
tsv_path = Path('data/rover_ca_sitters.tsv')
LOG = Path('/tmp/oc_deep.log')
CHECKPOINT_EVERY = 100

existing_ids = set(str(i) for i in pd.read_parquet(parquet_path)['listing_id'].dropna())
all_sitters = {}
if tsv_path.exists():
    with tsv_path.open('r', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            all_sitters[row['listing_id']] = row
            existing_ids.add(row['listing_id'])

FIELDS = ['listing_id','source','provider_name','zip_code','city','state','service_type','description','price_usd','price_unit','rating','review_count','profile_url','search_business_name','verified_status']
added = 0
last_ckpt = 0
stopping = False


def save(reason):
    global last_ckpt
    try:
        with tsv_path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, delimiter='\t')
            w.writeheader()
            for r in all_sitters.values():
                w.writerow(r)
        rep = build_catalog(tsv_path, parquet_path, mode='upsert')
        with LOG.open('a') as f:
            f.write(f'[CHECKPOINT {reason}] added={added} parquet={rep["final_count"]}\n')
        last_ckpt = added
    except Exception as e:
        with LOG.open('a') as f:
            f.write(f'[CKPT FAIL {reason}] {e}\n')


def on_sig(s, f):
    global stopping
    stopping = True
    with LOG.open('a') as f:
        f.write(f'[SIGNAL {s}] saving...\n')


signal.signal(signal.SIGINT, on_sig)
signal.signal(signal.SIGTERM, on_sig)


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


OC_ZIPS = ['92602','92603','92604','92605','92606','92607','92608','92609','92610','92611','92612','92613','92614','92615','92616','92617','92618','92619','92620','92621','92622','92623','92624','92625','92626','92627','92628','92629','92630','92631','92632','92633','92634','92635','92636','92637','92638','92639','92640','92641','92642','92643','92644','92645','92646','92647','92648','92649','92650','92651','92652','92653','92654','92655','92656','92657','92658','92659','92660','92661','92662','92663','92664','92665','92666','92667','92668','92669','92670','92671','92672','92673','92674','92675','92676','92677','92678','92679','92680','92681','92682','92683','92684','92685','92686','92687','92688','92689','92690','92691','92692','92693','92694','92695','92696','92697','92698','92699','92700','92701','92702','92703','92704','92705','92706','92707','92708','92709','92710','92711','92712','92713','92714','92715','92716','92717','92718','92719','92720','92721','92722','92723','92724','92725','92726','92727','92728','92729','92730','92731','92732','92733','92734','92735','92736','92737','92738','92739','92740','92741','92742','92743','92744','92745','92746','92747','92748','92749','92750','92751','92752','92753','92754','92755','92756','92757','92758','92759','92760','92761','92762','92763','92764','92765','92766','92767','92768','92769','92770','92771','92772','92773','92774','92775','92776','92777','92778','92779','92780','92781','92782','92783','92784','92785','92786','92787','92788','92789','92790','92791','92792','92793','92794','92795','92796','92797','92798','92799','92800','92801','92802','92803','92804','92805','92806','92807','92808','92809','92810','92811','92812','92813','92814','92815','92816','92817','92818','92819','92820','92821','92822','92823','92824','92825','92826','92827','92828','92829','92830','92831','92832','92833','92834','92835','92836','92837','92838','92839','92840','92841','92842','92843','92844','92845','92846','92847','92848','92849','92850','92851','92852','92853','92854','92855','92856','92857','92858','92859','92860','92861','92862','92863','92864','92865','92866','92867','92868','92869','92870','92871','92872','92873','92874','92875','92876','92877','92878','92879','92880','92881','92882','92883','92884','92885','92886','92887','92888','92889','92890','92891','92892','92893','92894','92895','92896','92897','92898','92899']
SERVICES = [('overnight-boarding','Boarding'),('dog-walking','Dog Walking'),('day-care','Doggy Day Care'),('house-sitting','House Sitting'),('drop-in-visits','Drop-In Visits')]
PAGES = [2, 3, 4]

try:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox', '--disable-setuid-sandbox'])
        page = b.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
            viewport={'width': 1440, 'height': 900}, locale='en-US').new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        for slug, sname in SERVICES:
            for z in OC_ZIPS:
                if stopping:
                    break
                for pg in PAGES:
                    if stopping:
                        break
                    url = (f'https://www.rover.com/search/?service_type={slug}'
                           f'&location={z}&location_type=zip-code&page={pg}')
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
                            lid = f'rover-{opk}-{slug}'
                            if lid in existing_ids:
                                continue
                            existing_ids.add(lid)
                            added += 1
                            n_new += 1
                            name = s.get('shortName') or ''
                            all_sitters[lid] = {
                                'listing_id': lid, 'source': 'Rover', 'provider_name': name,
                                'zip_code': s.get('zip') or z, 'city': s.get('city') or 'California',
                                'state': (s.get('state') or 'CA').upper(), 'service_type': sname,
                                'description': (s.get('description') or s.get('title') or '').replace('\n', ' ').replace('\r', ' '),
                                'price_usd': str(s.get('price')) if s.get('price') else '0',
                                'price_unit': s.get('priceUnit') or 'night',
                                'rating': str(s.get('ratingsAverage')) if s.get('ratingsAverage') else '0',
                                'review_count': str(s.get('reviewsCount')) if s.get('reviewsCount') is not None else '0',
                                'profile_url': s.get('webUrl') or '',
                                'search_business_name': f'Rover - {name}', 'verified_status': 'True',
                            }
                        if n_new:
                            with LOG.open('a') as f:
                                f.write(f'{sname} {z} p{pg}: {len(arr)} results, +{n_new} new (total {added})\n')
                    except Exception as e:
                        with LOG.open('a') as f:
                            f.write(f'ERR {sname} {z} p{pg}: {str(e)[:70]}\n')
                    if added - last_ckpt >= CHECKPOINT_EVERY:
                        save('auto')
                    time.sleep(1.5)
            if stopping:
                break
        b.close()
finally:
    save('final')

print(f'OC DEEP DONE added={added} total={len(all_sitters)}')
