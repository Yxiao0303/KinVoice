import test from 'node:test';
import assert from 'node:assert/strict';
import {readTurnStream} from '../backend/app/ccare/web/stream.mjs';
import {technicalReport} from '../backend/app/ccare/web/report.mjs';
import {Conversation} from '../backend/app/ccare/web/session.mjs';

const final = {reply:'测试回复',mode:'remote',checks:['model_check_passed_unvalidated'],model_calls:3};
const start = {sequence:1,type:'start',protocol:'ccare-stream-v1'};
function response(events, step = 7) {
  const bytes = new TextEncoder().encode(events.map(e => typeof e === 'string' ? e : JSON.stringify(e)).join('\n')+'\n');
  let at = 0;
  return new Response(new ReadableStream({pull(controller){
    if(at === bytes.length) return controller.close();
    controller.enqueue(bytes.slice(at,at+step)); at = Math.min(bytes.length,at+step);
  }}), {headers:{'content-type':'application/x-ndjson'}});
}
test('split Unicode chunks produce only checked final result and live metadata', async () => {
  const progress=[];
  const r = await readTurnStream(response([start,{sequence:2,type:'stage',stage:'state',event:'started'},{sequence:3,type:'result',result:final}],1), e=>progress.push(e));
  assert.equal(r.reply,'测试回复'); assert.equal(progress.length,2); assert.ok(progress.every(e=>!e.result));
});
test('missing final record and malformed JSON cannot publish a candidate', async () => {
  await assert.rejects(readTurnStream(response([start])), /提前结束/);
  await assert.rejects(readTurnStream(response([start,'not-json'])), /不完整/);
});
test('duplicate, reordered, or appended final records are rejected', async () => {
  for(const events of [[start,{sequence:3,type:'result',result:final}], [start,{sequence:2,type:'result',result:final},{sequence:3,type:'heartbeat'}]])
    await assert.rejects(readTurnStream(response(events)), /顺序异常/);
});
test('unknown server error details are never reflected to user', async () => {
  await assert.rejects(readTurnStream(response([start,{sequence:2,type:'error',code:'secret-provider-body'}])), e=>e.message==='本轮处理未完成，请稍后重试。');
});
test('stream closes on session expiration and provides actionable code', async () => {
  await assert.rejects(readTurnStream(response([start,{sequence:2,type:'error',code:'session_expired'}])), e=>e.code==='session_expired');
});
test('read rejection prevents publishing even after partial progress', async () => {
  const r = new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(JSON.stringify(start)+'\n'));c.error(new DOMException('aborted','AbortError'));}}), {headers:{'content-type':'application/x-ndjson'}});
  await assert.rejects(readTurnStream(r), e=>e.name==='AbortError');
});
test('technical export omits dialogue and evidence and leaves incomplete usage unknown', () => {
  const secret='private-synthetic-text';
  const report=technicalReport([{role:'user',status:'paused',content:secret},{role:'assistant',content:secret,result:{...final,reply:secret,decision:{evidence:[{quote:secret}],allowed:['listen']},usage:[null],stages:[]}}]);
  assert.ok(!report.includes(secret)); assert.match(report,/未知或不完整/); assert.match(report,/暂停：1/);
});
test('context truncation removes whole pairs and does not send receipt metadata', () => {
  const c=new Conversation();
  for(let i=0;i<5;i++){const t=c.begin(String(i).padEnd(1900,'x'));c.finish(t,{reply:'r'.repeat(1900),privateReceipt:'not-context'});}
  const context=c.context(); assert.equal(context.length,8); assert.equal(context[0].role,'user');
  assert.ok(context.every((m,i)=>m.role===(i%2?'assistant':'user')));
  assert.ok(!JSON.stringify(context).includes('privateReceipt'));
});
