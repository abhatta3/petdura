import pyarrow.parquet as pq
import os

f = "data/pet_services.parquet"
p = pq.read_table(f).to_pandas()

print("PARQUET STATE:")
print(f"  Total rows: {len(p)}")
print(f"  Sources: {dict(p['source'].value_counts())}")
print(f"  File size: {os.path.getsize(f)/1e6:.1f} MB")

r = p[p['source'] == 'Rover']
print(f"  Rover rows: {len(r)}")
print(f"  Rover unique zips: {r['zip_code'].nunique()}")
print(f"  Rover top zips: {dict(r['zip_code'].value_counts().head(5))}")

yp = p[p['source'] == 'YellowPages']
print(f"  YellowPages rows: {len(yp)}")
print(f"  YellowPages zips: {yp['zip_code'].unique().tolist()}")

print(f"  Rows without profile_url: {(p['profile_url'] == '').sum()}")
print(f"  NaN price_usd: {p['price_usd'].isna().sum()}")
