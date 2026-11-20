import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import dotenv from 'dotenv';
import { createInstance } from '@amplitude/analytics-node';
import { Statsig, StatsigUser } from '@statsig/statsig-node-core';
dotenv.config({quiet:true});
const test = process.argv.includes('--test');
const localAmplitude = test || process.env.AMPLITUDE_MODE !== 'cloud';
const localStatsig = test || process.env.STATSIG_MODE !== 'cloud';
if (!localAmplitude && !process.env.AMPLITUDE_API_KEY) throw new Error('AMPLITUDE_API_KEY required for cloud mode');
if (!localStatsig && !process.env.STATSIG_SERVER_SECRET) throw new Error('STATSIG_SERVER_SECRET required for cloud mode');
const dir = path.resolve('.local'); fs.mkdirSync(dir, {recursive:true});
const captured = [];
const transport = {async send(_url, payload) {
  for (const event of payload.events) {
    captured.push(event);
    fs.appendFileSync(path.join(dir,'amplitude-events.jsonl'), JSON.stringify({mode:'local-sdk-transport',event})+'\n');
  }
  return {status:'success',statusCode:200,body:{eventsIngested:payload.events.length,payloadSizeBytes:0,serverUploadTime:Date.now()}};
}};
const amplitude = createInstance();
await amplitude.init(localAmplitude ? 'local-development-placeholder' : process.env.AMPLITUDE_API_KEY, {
  ...(localAmplitude?{transportProvider:transport}:{}), flushQueueSize:1, flushIntervalMillis:100, logLevel:0
}).promise;
const statsig = new Statsig(localStatsig?'secret-local-development':process.env.STATSIG_SERVER_SECRET, {disableNetwork:localStatsig,disableAllLogging:localStatsig,environment:'development'});
await statsig.initialize();
const user = new StatsigUser({userID:'demo-user'});
if (localStatsig) statsig.overrideGate('personalized_recommendations', true);
const enabled = statsig.checkGate(user,'personalized_recommendations');
if (test) {
  assert.equal(enabled,true);
  statsig.overrideGate('personalized_recommendations',false);
  assert.equal(statsig.checkGate(user,'personalized_recommendations'),false);
  statsig.overrideGate('personalized_recommendations',true);
}
let event = test ? {event_type:'Local SDK Smoke Test',user_id:'demo-user',event_properties:{synthetic:true}} : JSON.parse(fs.readFileSync(0,'utf8'));
event.event_properties = {...event.event_properties,personalized_recommendations:enabled};
const result = await amplitude.track(event).promise;
await amplitude.flush().promise;
await statsig.shutdown();
if (test) assert.equal(captured.length,1);
if (result.code !== 200) throw new Error(`Amplitude delivery failed: ${result.code}`);
console.log(JSON.stringify({amplitude:localAmplitude?'local-file-transport':'cloud',statsig:localStatsig?'offline-overrides':'cloud',personalized_recommendations:enabled,test_passed:test||undefined}));
