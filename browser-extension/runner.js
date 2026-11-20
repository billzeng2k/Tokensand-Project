const status=document.querySelector('#status');
let paused=false;
const productLinks=new Map();
document.querySelector('#toggle').onclick=()=>{paused=!paused;document.querySelector('#toggle').textContent=paused?'Resume':'Pause';};
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(path,data){
  const response=await fetch('http://127.0.0.1:8789'+path,{method:data?'POST':'GET',headers:{Authorization:'Bearer '+UPNEXT_BRIDGE_TOKEN,...(data?{'Content-Type':'application/json'}:{})},...(data?{body:JSON.stringify(data)}:{})});
  if(!response.ok)throw new Error('Local companion connection failed');return response.json();
}
async function loaded(id,search=false){
  for(let i=0;i<80;i++){
    const tab=await chrome.tabs.get(id);
    if(tab.status==='complete'&&tab.url?.startsWith('https://www.amazon.com/')&&(!search||new URL(tab.url).pathname==='/s'))return tab;
    await sleep(500);
  }
  throw new Error('Amazon page timed out');
}
async function read(job){
  const url=new URL(job.url);
  if(url.origin!=='https://www.amazon.com'||!(url.pathname==='/s'||/^\/dp\/[A-Z0-9]{10}$/.test(url.pathname)))throw new Error('Unsupported URL');
  const search=url.pathname==='/s';
  const tab=await chrome.tabs.create({url:search?'https://www.amazon.com/':(productLinks.get(job.url)||job.url),active:true});
  try{
    await loaded(tab.id);
    if(search){
      const [{result:submitted}]=await chrome.scripting.executeScript({target:{tabId:tab.id},args:[url.searchParams.get('k')],func:query=>{
        const input=document.querySelector('#twotabsearchtextbox');
        if(!input||!input.form)return false;
        input.value=query;input.dispatchEvent(new Event('input',{bubbles:true}));input.form.requestSubmit();return true;
      }});
      if(!submitted)return null;
      await loaded(tab.id,true);
    }
    const state=await chrome.tabs.get(tab.id);const actual=new URL(state.url);
    if(actual.origin!==url.origin||(!search&&!actual.pathname.includes(url.pathname)))return null;
    const [{result}]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>{
      const text=document.body.innerText;
      if(/enter the characters you see|robot check|sorry! something went wrong|verify that you are not a robot/i.test(text))return null;
      const products=[];const seen=new Set();
      for(const a of document.querySelectorAll('a[href]')){
        const asin=a.href.match(/https:\/\/www\.amazon\.com\/(?:[^?#]*\/)?(?:dp|gp\/product)\/([A-Z0-9]{10})(?:[/?#]|$)/)?.[1];
        if(asin&&!seen.has(asin)){seen.add(asin);products.push({url:'https://www.amazon.com/dp/'+asin,href:a.href});}
        if(products.length>=100)break;
      }
      const title=document.querySelector('#productTitle')?.innerText.trim();const start=title?text.indexOf(title):-1;
      return {text:(start>=0?text.slice(start):text).slice(0,50000),products};
    }});
    if(!result)return null;
    for(const p of result.products)productLinks.set(p.url,p.href);
    // Bound local link cache and never persist cookies, browsing history or account data.
    while(productLinks.size>300)productLinks.delete(productLinks.keys().next().value);
    return {url:job.url,text:result.text,links:result.products.map(p=>p.url)};
  }finally{await chrome.tabs.remove(tab.id).catch(()=>{});}
}
(async()=>{
  while(true){
    try{
      if(paused){status.textContent='Paused';await sleep(1000);continue;}
      const job=await api('/next');
      if(job){
        status.textContent='Reading Amazon for UpNext…';let result=null;
        try{result=await read(job);}catch(error){result={url:job.url,text:'',links:[],error:String(error.message).slice(0,200)};status.textContent='Amazon page was unavailable.';}
        await api('/result',{id:job.id,result});
      }
      status.textContent='Connected. Waiting for an UpNext request.';
    }catch{status.textContent='Start UpNext locally, then this companion will reconnect.';}
    await sleep(1000);
  }
})();
