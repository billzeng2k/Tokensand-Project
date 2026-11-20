import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
const sha = x=>crypto.createHash('sha256').update(x).digest('hex');
const root=fs.realpathSync('.'), stat=fs.statSync(root,{bigint:true});
const identity=sha(`firedrill.root-identity.v1\0${root}\0${stat.dev}:${stat.ino}`);
const descriptor={schema:'firedrill.local-descriptor.v1',source_roots:[{alias:'app',identity_sha256:identity}],services:[{alias:'agent',root_alias:'app',role:'agent',depends_on:[],configuration:[{name:'TOKENSAND_NO_DOTENV',phase:'runtime',secret:false,required:false},{name:'CALENDAR_INVOKE_URL',phase:'runtime',secret:false,required:true},{name:'SHOPPING_INVOKE_URL',phase:'runtime',secret:false,required:true}]}],entry_service:'agent',driver:{profile:'jsonl-process.v1',adapter_sha256:sha(fs.readFileSync('tokensand/bridge.py')),authentication:'anonymous',state_domains:['proc']},state_domains:[{alias:'proc',service_alias:'agent',kind:'process',location:'local',reset:'fresh-process',concurrency:'independent',hook_sha256:null}],dependencies:[{alias:'calendar',service_alias:'agent',protocol:'http',mode:'synthetic',operations:['events.get']},{alias:'shopping',service_alias:'agent',protocol:'http',mode:'synthetic',operations:['products.search','products.get','tasks.create','tasks.get']}]};
fs.mkdirSync('firedrill',{recursive:true});fs.writeFileSync('firedrill/descriptor-local.json',JSON.stringify(descriptor,null,2));
const digest=process.argv[2];
if(digest){
 if(!/^[a-f0-9]{64}$/.test(digest))throw Error('Pass the exact 64-character descriptor digest returned by register');
 const plan={version:1,descriptor_sha256:digest,roots:[{alias:'app',path:root,identity_sha256:identity}],services:[{alias:'agent',root_alias:'app',mode:'launch',command:{executable:path.join(root,'.venv/bin/python'),args:['-m','tokensand.bridge']},cwd:'.',env_passthrough:[],env_static:{TOKENSAND_NO_DOTENV:'1'},local_secret_env:[],readiness:{kind:'stdout',pattern:'READY'},readiness_timeout_ms:30000,stop_timeout_ms:5000,per_drill:true,port_env:null,dependency_env:[{alias:'calendar',name:'CALENDAR_INVOKE_URL',url:'invoke'},{alias:'shopping',name:'SHOPPING_INVOKE_URL',url:'invoke'}]}],driver:{profile:'jsonl-process.v1',service_alias:'agent'},state_hooks:[],max_parallel_drills:1};
 fs.writeFileSync('firedrill/plan-local.json',JSON.stringify(plan,null,2));
 console.log('Generated machine-local descriptor and plan. Neither file should be committed.');
}else console.log('Generated descriptor-local.json. Register it, then rerun with the returned digest to generate the plan.');
