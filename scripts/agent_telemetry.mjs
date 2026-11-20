import fs from 'node:fs';
import dotenv from 'dotenv';
import {createInstance} from '@amplitude/analytics-node';
import {Statsig,StatsigUser} from '@statsig/statsig-node-core';
dotenv.config({quiet:true});
const input=JSON.parse(fs.readFileSync(0,'utf8'));
if(input.action==='evaluate'){
 const local=process.env.STATSIG_MODE!=='cloud';
 if(!local&&!process.env.STATSIG_SERVER_SECRET)throw Error('Statsig key missing');
 const sdk=new Statsig(local?'secret-local-development':process.env.STATSIG_SERVER_SECRET,{disableNetwork:local,disableAllLogging:local,environment:local?'development':'production'});
 const init=await sdk.initialize();if(!local&&!init.isSuccess)throw Error('Statsig initialization failed');
 const user=new StatsigUser({userID:input.user_id});
 const controls=input.controls;
 const names={agent_enabled:'shopping_agent_enabled',web_enabled:'web_research_enabled',proactive_enabled:'proactive_recommendations'};
 if(local){for(const [key,name] of Object.entries(names))sdk.overrideGate(name,controls[key]);sdk.overrideExperiment('shopping_recommendation_strategy',{strategy:controls.strategy});}
 const gates={};for(const [key,name] of Object.entries(names)){const gate=sdk.getFeatureGate(user,name);gates[key]={name,value:gate.value,rule_id:gate.ruleID};}
 const experiment=sdk.getExperiment(user,'shopping_recommendation_strategy');
 const candidate=experiment.get('strategy','evidence_first');
 const output={mode:local?'offline-overrides':'cloud',strategy:['evidence_first','budget_first'].includes(candidate)?candidate:'evidence_first',experiment:'shopping_recommendation_strategy',group:experiment.groupName||null,rule_id:experiment.ruleID,gates};
 await sdk.shutdown();console.log(JSON.stringify(output));
}else if(input.action==='events'){
 const local=process.env.AMPLITUDE_MODE!=='cloud';
 if(!local&&!process.env.AMPLITUDE_API_KEY)throw Error('Amplitude key missing');
 const sdk=createInstance();fs.mkdirSync('.local',{recursive:true});
 const transport={async send(_url,payload){for(const event of payload.events)fs.appendFileSync('.local/agent-amplitude-events.jsonl',JSON.stringify({mode:'local-sdk-transport',event})+'\n',{mode:0o600});return {status:'success',statusCode:200,body:{eventsIngested:payload.events.length,payloadSizeBytes:0,serverUploadTime:Date.now()}};}};
 await sdk.init(local?'local-development-placeholder':process.env.AMPLITUDE_API_KEY,{...(local?{transportProvider:transport}:{}),flushQueueSize:1,flushIntervalMillis:100,logLevel:0}).promise;
 for(const event of input.events){const result=await sdk.track(event).promise;if(result.code!==200)throw Error('Event delivery failed');}
 await sdk.flush().promise;
 const localStatsig=process.env.STATSIG_MODE!=='cloud';
 if(!localStatsig&&!process.env.STATSIG_SERVER_SECRET)throw Error('Statsig key missing');
 const statsig=new Statsig(localStatsig?'secret-local-development':process.env.STATSIG_SERVER_SECRET,{disableNetwork:localStatsig,disableAllLogging:localStatsig,environment:localStatsig?'development':'production'});
 const init=await statsig.initialize();if(!localStatsig&&!init.isSuccess)throw Error('Statsig initialization failed');
 for(const event of input.events){
  const name=event.event_type.toLowerCase().replaceAll(' ','_');
  const metadata={...event.event_properties,event_id:event.insert_id};
  statsig.logEvent(new StatsigUser({userID:event.user_id}),name,event.event_properties.latency_ms??null,metadata);
  if(localStatsig)fs.appendFileSync('.local/agent-statsig-events.jsonl',JSON.stringify({mode:'offline-sdk-log',event:name,metadata})+'\n',{mode:0o600});
 }
 const flushed=await statsig.flushEvents();await statsig.shutdown();if(!localStatsig&&!flushed.isSuccess)throw Error('Statsig event delivery failed');
 console.log(JSON.stringify({mode:local?'local-file-transport':'cloud',statsig:localStatsig?'offline-sdk-log':'cloud',count:input.events.length}));
}else throw Error('Unknown action');
