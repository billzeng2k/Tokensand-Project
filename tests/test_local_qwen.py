import json
from unittest.mock import patch
import pytest
from scripts import try_local_qwen as qwen

@pytest.mark.parametrize('url',[
 'http://www.amazon.com/dp/B000000000',
 'https://www.amazon.com.evil.test/dp/B000000000',
 'https://localhost/private',
 'https://user@www.amazon.com/dp/B000000000',
 'https://www.amazon.com:8443/dp/B000000000',
])
def test_reader_rejects_untrusted_destinations(url):
    with pytest.raises(ValueError):qwen.read_amazon(url,[])

def test_blocked_search_stops_without_retrying_or_inventing_products(tmp_path,monkeypatch):
    monkeypatch.setattr(qwen,'ROOT',tmp_path)
    monkeypatch.setattr('sys.argv',['try_local_qwen.py'])
    result={'summary':'Amazon unavailable','reason':'No product evidence','should_recommend':False,'groups':[],'recipes':[],'missing_information':['What dish are you bringing?']}
    with patch.object(qwen,'model_call',side_effect=[{'queries':['food carrier','serving spoon']},result]),patch.object(qwen,'read_amazon',return_value=None) as reader:
        qwen.main()
    assert reader.call_count==1
    report=json.loads((tmp_path/'.local/qwen-potluck-test.json').read_text())
    assert report['status']=='blocked_by_amazon'
    assert report['result']['items']==[]
    assert report['api_cost_usd']==0

def test_empty_evidence_cannot_be_disguised_as_recipe_recommendation(tmp_path,monkeypatch):
    monkeypatch.setattr(qwen,'ROOT',tmp_path)
    monkeypatch.setattr('sys.argv',['try_local_qwen.py'])
    result={'summary':'Buy ingredients','reason':'Recipe','should_recommend':True,'groups':[],'recipes':[{'name':'Pie','reason':'Potluck','ingredients':['apples'],'steps':['Bake'],'ingredient_item_names':[]}],'missing_information':[]}
    with patch.object(qwen,'model_call',side_effect=[{'queries':['pie']},result]),patch.object(qwen,'read_amazon',return_value=None),pytest.raises(RuntimeError,match='without product evidence'):
        qwen.main()
