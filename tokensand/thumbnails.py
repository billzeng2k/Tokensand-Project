"""Per-account thumbnail backfill, keyed by exact Amazon product/variant ID."""
import json
from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit
from . import observability as ledger,shopping

def safe_image(url):
    if not isinstance(url,str):return None
    parsed=urlsplit(url)
    return url if parsed.scheme=='https' and parsed.netloc in ('m.media-amazon.com','images-na.ssl-images-amazon.com') and parsed.path.startswith('/images/') else None

def images():
    with ledger.db() as c:return {r[0]:json.loads(r[1]) for r in c.execute('SELECT item_key,payload FROM product_images')}

def refresh(event_id):
    if not isinstance(event_id,str) or len(event_id)!=64:raise ValueError('Invalid calendar event')
    with ledger.db() as c:
        rows=c.execute("SELECT payload FROM runs WHERE mode='live' AND status='completed' AND json_extract(payload,'$.event_id')=? ORDER BY created_at",(event_id,)).fetchall()
    products={};known={}
    for row in rows:
        for item in (json.loads(row[0]).get('result') or {}).get('items',[]):
            key=shopping.key(item['source_url']);products[key]=item
            if safe_image(item.get('image_url')):known[key]=item['image_url']
    cache=images();attempts=0
    for key,item in products.items():
        previous=cache.get(key)
        if previous and safe_image(previous.get('image_url')):continue
        if previous and previous.get('checked_at','')>(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat():continue
        url='https://www.amazon.com/dp/'+key
        image=known.get(key);record={'source_url':url,'checked_at':ledger.now(),'status':'unavailable'}
        if not image:
            if attempts>=6:continue
            from .amazon_bridge import valid_url
            if not valid_url(url):continue
            from .local_browser import read
            attempts+=1
            try:
                page=read(url)
                if not page.get('error'):image=safe_image(page.get('image_url'))
            except (RuntimeError,ValueError):pass
        if image:record.update(status='available',image_url=image)
        with ledger.db() as c:c.execute('INSERT INTO product_images VALUES(?,?) ON CONFLICT(item_key) DO UPDATE SET payload=excluded.payload',(key,json.dumps(record)))
    return images()
