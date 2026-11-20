from unittest.mock import Mock,patch
import pytest
from tokensand import local_qwen as qwen

@pytest.mark.parametrize('url',['http://www.amazon.com/dp/B000000000','https://www.amazon.com.evil.test/dp/B000000000','https://localhost/private','https://user@www.amazon.com/dp/B000000000','https://www.amazon.com:8443/dp/B000000000'])
def test_reader_rejects_untrusted_destinations(url):
    with pytest.raises(ValueError):qwen.read_amazon(url,[])

def test_blocked_search_stops_without_retrying_or_model_recommendations():
    call=Mock(return_value={'queries':['food carrier','serving spoon']})
    with patch.object(qwen,'read_amazon',return_value=None) as reader,pytest.raises(RuntimeError,match='amazon_evidence_unavailable'):
        qwen.research('Potluck',{},call,[])
    assert reader.call_count==1 and call.call_count==1

def test_private_identifier_query_never_leaves_machine():
    call=Mock(return_value={'queries':['gift for bill@example.com']})
    with patch.object(qwen,'read_amazon') as reader,pytest.raises(RuntimeError,match='unsafe_search_query'):
        qwen.research('Potluck',{},call,[])
    reader.assert_not_called()

def test_retrieved_products_bound_and_unsupported_numbers_removed():
    url='https://www.amazon.com/dp/B000000001'
    item={'name':'Carrier','source_url':url,'price_cents':1999,'rating':4.5,'review_count':123,'currency':'USD','reason':'Transport dish','uncertainties':[]}
    call=Mock(side_effect=[{'queries':['food carrier']},{'groups':[{'category':'Transport','reason':'Potluck','items':[item]}]}])
    reads=[('/dp/B000000001/ /dp/B000000001/ /dp/B000000002/ /dp/B000000003/ /dp/B000000004/','search'),('html','Carrier $19.99 4.5 out of 5 stars'),('html','Serving dish'),('html','Spoon')]
    with patch.object(qwen,'read_amazon',side_effect=reads) as reader:
        result,evidence=qwen.research('Potluck',{},call,[])
    assert reader.call_count==4 and len(evidence)==3
    assert result['groups'][0]['items'][0]['price_cents']==1999
    assert result['groups'][0]['items'][0]['rating']==4.5
    assert result['groups'][0]['items'][0]['review_count'] is None

def test_cloud_model_names_rejected():
    with pytest.raises(ValueError):qwen.model_call([],{},'qwen:cloud')
