"""App-owned browser worker: bounded Amazon reads, no personal browser profile."""
import os
import queue
import re
import threading
from urllib.parse import parse_qs,urlsplit
from .amazon_bridge import valid_url

QUEUE=queue.Queue(maxsize=4)
LOCK=threading.Lock()
THREAD=None

def read(url):
    global THREAD
    if not valid_url(url):raise ValueError('invalid_amazon_url')
    with LOCK:
        if THREAD is None or not THREAD.is_alive():
            THREAD=threading.Thread(target=worker,name='amazon-browser',daemon=True);THREAD.start()
    reply=queue.Queue(maxsize=1)
    QUEUE.put((url,reply),timeout=5)
    try:return reply.get(timeout=120)
    except queue.Empty:raise RuntimeError('amazon_browser_timeout') from None

def worker():
    browser=None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=os.getenv('AMAZON_BROWSER_HEADLESS','false').lower()=='true')
            context=browser.new_context(locale='en-US',viewport={'width':1280,'height':900})
            page=context.new_page();page.set_default_timeout(15000);page.set_default_navigation_timeout(30000)
            product_links={}
            while True:
                job=QUEUE.get()
                if job is None:break
                url,reply=job
                try:
                    p=urlsplit(url)
                    if p.path=='/s':
                        page.goto('https://www.amazon.com/',wait_until='domcontentloaded')
                        # Use the public site's search form rather than guessing result URLs.
                        field=page.locator('#twotabsearchtextbox')
                        field.fill(parse_qs(p.query).get('k',[''])[0])
                        field.press('Enter')
                        page.wait_for_url('https://www.amazon.com/s?**',wait_until='domcontentloaded')
                    else:page.goto(product_links.get(url,url),wait_until='domcontentloaded')
                    actual=urlsplit(page.url)
                    if actual.hostname!='www.amazon.com':raise ValueError('unexpected_amazon_redirect')
                    text=page.locator('body').inner_text()
                    if re.search(r'enter the characters you see|robot check|sorry! something went wrong|verify that you are not a robot',text,re.I):
                        reply.put({'error':'amazon_blocked','text':'','links':[]});continue
                    if p.path.startswith('/dp/'):
                        try:
                            page.wait_for_function("Array.from(document.querySelectorAll('#landingImage,#imgBlkFront,#main-image')).some(i=>i.complete && i.naturalWidth>40)",timeout=5000)
                        except Exception:pass
                    data=page.evaluate('''() => {
                      const products=[];const seen=new Set();
                      for(const a of document.querySelectorAll('a[href]')){
                        const asin=a.href.match(/https:\\/\\/www\\.amazon\\.com\\/(?:[^?#]*\\/)?(?:dp|gp\\/product)\\/([A-Z0-9]{10})(?:[/?#]|$)/)?.[1];
                        if(asin&&!seen.has(asin)){seen.add(asin);products.push({url:'https://www.amazon.com/dp/'+asin,href:a.href});}
                        if(products.length>=100)break;
                      }
                      return {products,title:document.querySelector('#productTitle')?.innerText.trim()||'',image_url:Array.from(document.querySelectorAll('#landingImage,#imgBlkFront,#main-image')).find(i=>i.complete&&i.naturalWidth>40)?.currentSrc||''};
                    }''')
                    for product in data['products']:product_links[product['url']]=product['href']
                    if len(product_links)>300:product_links=dict(list(product_links.items())[-300:])
                    if data['title'] and data['title'] in text:text=text[text.index(data['title']):]
                    if p.path.startswith('/dp/') and (not data['title'] or p.path not in actual.path):
                        reply.put({'error':'amazon_product_unavailable','text':'','links':[]});continue
                    reply.put({'url':url,'text':text[:50000],'image_url':data.get('image_url'),'links':[p['url'] for p in data['products']]})
                except Exception as exc:
                    reply.put({'error':type(exc).__name__,'text':'','links':[]})
            browser.close()
    except Exception as exc:
        # Startup errors also reach the caller; do not hang waiting for a model.
        while True:
            try:
                job=QUEUE.get(timeout=1)
                if job is not None:job[1].put({'error':'browser_startup_'+type(exc).__name__,'text':'','links':[]})
                break
            except queue.Empty:break

def stop():
    if THREAD and THREAD.is_alive():
        try:QUEUE.put_nowait(None)
        except queue.Full:return
        THREAD.join(timeout=2)
