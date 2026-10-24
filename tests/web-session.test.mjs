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

test('review confirm correct revoke is idempotent and snapshot isolated', () => {
  const c=new Conversation(), t=c.begin('fictional private');
  const target={field:'emotion',value:'sad',revision:0,source_message_id:`u:${t}`,source_digest:'a'.repeat(64),source_text:'fictional private'};
  c.finish(t,{reply:'reply',review_targets:[target]});
  assert.equal(c.review(target,'confirm','sad',t),true);
  assert.equal(c.review(target,'confirm','sad',t),true);
  let entries=c.reviewsFor(c.context(),'next'); assert.equal(entries[0].revision,1);
  entries[0].value='unknown'; assert.equal(c.reviewsFor(c.context(),'next')[0].value,'sad');
  c.review(target,'correct','angry',t); assert.equal(c.reviewsFor(c.context(),'next')[0].revision,2);
  c.review(target,'revoke','angry',t); c.review(target,'revoke','unknown',t);
  assert.equal(c.reviewsFor(c.context(),'next')[0].revision,3);
});
test('pending paused stale and cleared results cannot overwrite review state', () => {
  const c=new Conversation(), t=c.begin('first');
  const target={field:'support_intent',value:'listen',source_message_id:`u:${t}`,source_digest:'b'.repeat(64),source_text:'first',revision:0};
  c.finish(t,{reply:'reply',review_targets:[target]}); c.review(target,'confirm','listen',t);
  const pending=c.begin('second'); assert.equal(c.review(target,'correct','draft',t),false);
  c.pause(); assert.equal(c.finish(pending,{reply:'late',review_targets:[target]}),false);
  assert.equal(c.review(target,'revoke','listen',t),false);
  assert.equal(c.reviewsFor(c.context(),'next')[0].action,'confirm');
  c.clear(); assert.deepEqual(c.reviewsFor([],'next'),[]);
  assert.equal(c.review(target,'confirm','listen',t),false);
  const other=new Conversation(); assert.deepEqual(other.reviewsFor([],'next'),[]);
});
test('identical words in a fresh message have a different review identity', () => {
  const c=new Conversation(), t=c.begin('same');
  const target={field:'emotion',value:'sad',source_message_id:`u:${t}`,source_digest:'c'.repeat(64),source_text:'same',revision:0};
  c.finish(t,{reply:'reply',review_targets:[target]}); c.review(target,'revoke','sad',t);
  const fresh=c.begin('same'); assert.notEqual(`u:${fresh}`,target.source_message_id);
  assert.equal(c.reviewsFor(c.context(),'same')[0].source_message_id,`u:${t}`);
  // Once the original source is outside retained history, its review is pruned.
  assert.deepEqual(c.reviewsFor([],'same'),[]);
});
