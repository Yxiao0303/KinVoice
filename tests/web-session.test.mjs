import test from 'node:test';
import assert from 'node:assert/strict';
import { Conversation } from '../backend/app/ccare/web/session.mjs';

test('a normal response becomes visible with its input and metadata', () => {
  const c = new Conversation(); const ticket = c.begin('hello');
  assert.equal(c.finish(ticket, {reply:'reply',mode:'demo',model_calls:0}), true);
  assert.equal(c.messages.length, 2); assert.equal(c.lastResult.model_calls, 0);
});
test('a late response cannot resurrect a cleared conversation', () => {
  const c = new Conversation(); const ticket = c.begin('private'); c.clear();
  assert.equal(c.finish(ticket, {reply:'late'}), false); assert.deepEqual(c.messages, []);
});
test('pause suppresses a late response and excludes the interrupted turn from context', () => {
  const c = new Conversation(); const ticket = c.begin('private'); c.pause();
  assert.equal(c.finish(ticket, {reply:'late'}), false); assert.deepEqual(c.context(), []);
  assert.equal(c.messages[0].status, 'paused');
});
test('a previous request cannot finish or fail a newer turn', () => {
  const c = new Conversation(); const old = c.begin('first'); c.pause(); const fresh = c.begin('second');
  assert.equal(c.finish(old, {reply:'old'}), false); assert.equal(c.fail(old), false);
  assert.equal(c.pending, fresh); assert.equal(c.finish(fresh, {reply:'new'}), true);
});
test('failures retain the user message without polluting the next context', () => {
  const c = new Conversation(); const ticket = c.begin('input'); c.fail(ticket);
  assert.equal(c.messages[0].status, 'failed'); assert.deepEqual(c.context(), []);
});
test('context keeps recent complete turns within both bounds', () => {
  const c = new Conversation();
  for(let i=0;i<20;i++){const t=c.begin(String(i).padEnd(1200,'a'));c.finish(t,{reply:String(i).padEnd(1200,'b')});}
  const context=c.context(); assert.ok(context.length<=20);
  assert.ok(context.reduce((n,m)=>n+m.content.length,0)<=16000);
  assert.ok(context.at(-1).content.startsWith('19'));
});
test('double send is rejected while a turn is pending', () => {
  const c=new Conversation();c.begin('one');assert.throws(()=>c.begin('two'));
});
