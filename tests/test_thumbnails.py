import pytest
from tokensand import observability as ledger,tenancy,thumbnails,local_browser

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(ledger,'DB',tmp_path/'traces.db');monkeypatch.setattr(tenancy,'LOCAL',tmp_path)

def seed():
    run=ledger.create_run('Carrier','live',event_id='e'*64)
    run.update(status='completed',result={'items':[{'name':'Gray','source_url':'https://www.amazon.com/dp/B000000001','image_url':'https://m.media-amazon.com/images/I/gray.jpg'},{'name':'Black','source_url':'https://www.amazon.com/dp/B000000002'}]});ledger.save(run)


def test_backfill_keeps_variants_separate_and_is_cached(monkeypatch):
    seed();reads=[]
    def read(url):
        reads.append(url);return {'image_url':'https://m.media-amazon.com/images/I/black.jpg'}
    monkeypatch.setattr(local_browser,'read',read)
    images=thumbnails.refresh('e'*64)
    assert reads==['https://www.amazon.com/dp/B000000002']
    assert images['B000000001']['image_url'].endswith('gray.jpg')
    assert images['B000000002']['image_url'].endswith('black.jpg')
    thumbnails.refresh('e'*64);assert len(reads)==1


def test_backfill_cannot_cross_accounts(monkeypatch):
    with tenancy.scope('a'*64):seed()
    monkeypatch.setattr(local_browser,'read',lambda url:pytest.fail('Must not read another account products'))
    with tenancy.scope('b'*64):assert thumbnails.refresh('e'*64)=={}


def test_failed_image_does_not_borrow_another_variant(monkeypatch):
    seed();monkeypatch.setattr(local_browser,'read',lambda url:{'image_url':'https://evil.example/black.jpg'})
    record=thumbnails.refresh('e'*64)['B000000002']
    assert record['status']=='unavailable' and 'image_url' not in record
