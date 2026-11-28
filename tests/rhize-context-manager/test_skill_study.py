"""Exercise the same hook entry points as Claude, with a private validation store."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "rhize-context-manager"
LIB = PLUGIN / "hooks/lib/skill-study.js"
REPORT = PLUGIN / "scripts/skill_study_report.py"
spec = importlib.util.spec_from_file_location("study_report", REPORT)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_native_hook_protocol(tmp_path):
    script = r"""
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const crypto = require('node:crypto'), mod = require(process.argv[1]);
const root = process.argv[2], mode = process.argv[3], hash = x => crypto.createHash('sha256').update(x).digest('hex');
process.env.RHIZE_SKILL_STUDY_ROOT = root;
process.env.CLAUDE_CONFIG_DIR = path.join(root, 'claude');
let sid;
do { sid = crypto.randomUUID(); } while ((parseInt(hash(mod.STUDY + ':' + sid).slice(0,2),16) < 128) !== (mode === 'control'));
const data = {session_id:sid,source:'startup',transcript_path:path.join(process.env.CLAUDE_CONFIG_DIR,'projects','one',sid + '.jsonl'),prompt:'sample'};
mod.privateDir(root);
const cfg = {study:mod.STUDY,population:'validation',enabled:true,start:'2020-01-01',end:'2099-01-01',
runtime:mod.fingerprints(),index:'2'.repeat(64),modelRevision:'a'.repeat(40),instrument:require(path.join(path.dirname(process.argv[1]),'laya-instrument')).instrumentSha256(),registryRevision:2,validationSession:sid};
mod.write(path.join(root,'config.json'),cfg);
mod.enroll({...data,source:'resume'});assert.equal(mod.startTurn(data),null);
mod.enroll({...data,thread_id:'codex'});assert.equal(mod.startTurn(data),null);
mod.enroll(data);
const state = {sessionId:sid,incumbentShown:'skill:x/a',incumbentMessage:'Use A',eligible:true,ts:'2026-11-28T01:00:00Z'};
const plan = {config:{mode:'shadow',registryRevision:2,endpoint:'http://127.0.0.1:8000',model:'typed-decisions'},shortlist:['skill:x/a','skill:x/b']};
const laya = {choice:'skill:x/b',status:'ok'}, rec = {indexSha256:cfg.index,layaRevision:cfg.modelRevision,instrumentSha256:cfg.instrument,promptHash:hash(data.prompt),laya,shortlist:plan.shortlist};
function turnWith(p=plan,r=rec,response=laya) {
 const t = mod.startTurn(data);
 const msg = mod.prepare(t,state,p,response,r,s=>s);
 mod.delivered(t,msg ? state.incumbentMessage + '\n' + msg : state.incumbentMessage);
 return [t,msg];
}
let [t,msg] = turnWith();
assert.equal(!!msg,mode==='live');
const reply = (token,choice,reason) => ({...data,last_assistant_message:'answer\nLaya '+token+' '+choice+' '+reason});
mod.stop(reply('0'.repeat(32),'neither','wrong_question'));
assert.equal(fs.existsSync(path.join(t.dir,t.token+'.feedback.json')),false);
if (mode==='live') {
 fs.mkdirSync(path.dirname(data.transcript_path),{recursive:true});
 fs.writeFileSync(data.transcript_path,[
   {type:'user',sessionId:sid,message:{content:'sample'}},
   {type:'attachment',sessionId:sid,attachment:{type:'hook_additional_context',hookEvent:'UserPromptSubmit',content:['Use A\n'+msg]}}
 ].map(JSON.stringify).join('\n')+'\n');
 mod.stop(reply(t.token,'neither','wrong_question'));
 mod.stop(reply(t.token,'neither','wrong_question'));
 mod.stop(reply(t.token,'challenge','missing_candidate'));
 assert.equal(JSON.parse(fs.readFileSync(path.join(t.dir,t.token+'.feedback.json'))).response,'neither');
 assert.ok(fs.existsSync(path.join(t.dir,t.token+'.conflict.json')));
}
if(mode === 'live') {
 fs.appendFileSync(data.transcript_path,JSON.stringify({type:'user',sessionId:sid,message:{content:'a later task'}})+'\n');
 mod.stop(reply(t.token,'follow','fit'));
 assert.ok(fs.existsSync(path.join(t.dir,t.token+'.unverified.json')));
}
const old=t.token;
[t,msg]=turnWith({...plan,config:{...plan.config,pinned:true}});assert.equal(msg,null);
mod.stop(reply(old,'follow','fit'));assert.equal(fs.existsSync(path.join(t.dir,t.token+'.feedback.json')),false);
[t,msg]=turnWith(plan,{...rec,indexSha256:'9'.repeat(64)});assert.equal(msg,null);
[t,msg]=turnWith(plan,{...rec,laya:{status:'timeout'}},{status:'timeout'});assert.equal(msg,null);
[t,msg]=turnWith();
mod.invoked({...data,tool_name:'Skill',tool_use_id:'id',tool_input:{skill:'x:b'}});
mod.stop({...data,last_assistant_message:'no response'});
const cfgFile=path.join(root,'config.json');
mod.write(cfgFile,{...cfg,enabled:false},true);
const retired=mod.startTurn(data);assert.ok(retired && !retired.cfg);
assert.equal(mod.prepare(retired,state,plan,laya,rec,s=>s),null);
console.log(t.dir);
"""
    for arm in ("control", "live"):
        root = tmp_path / arm
        out = subprocess.check_output(["node", "-e", script, str(LIB), str(root), arm], text=True).strip()
        stats = study.report(root)["arms"][arm]
        assert stats["assignedSessions"] == 1 and stats["eligibleTurns"] == 6
        assert stats["nativeSkillCalls"] == 1 and stats["outcomesJoined"] == 0
        assert stats["missingTaskOutcomes"] == 1 and stats["interruptionsPerReviewedCompletedTask"] is None
        assert stats["shownAlternatives"] == (2 if arm == "live" else 0)
        assert stats["feedback"] == stats["neither"] == stats["noResponse"] == int(arm == "live")
        session = Path(out)
        turn = study.first_eligible(sorted((study.load(p) for p in session.glob("*.turn.json")),
                                           key=lambda t: (t["at"], t["token"])))
        evidence = b"Independent fixture review."
        (session / "task-review.evidence").write_bytes(evidence)
        packet = {"schema": "claude-skill-task-review-v1", "session": session.name, "token": turn["token"],
                  "promptHash": turn["promptHash"], "basis": "independent_verifier",
                  "result": "accepted_without_rework", "irrelevantInterruptions": 1,
                  "evidenceSha256": hashlib.sha256(evidence).hexdigest()}
        (session / "task-review.json").write_text(json.dumps(packet))
        assert study.report(root)["arms"][arm]["acceptedWithoutRework"] == 1
        (session / "task-review.evidence").write_bytes(b"changed")
        with pytest.raises(ValueError, match="evidence"):
            study.report(root)
