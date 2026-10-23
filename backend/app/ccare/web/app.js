'use strict';
const $ = id => document.getElementById(id);
let token = '', history = [], controller = null, generation = 0, mode = 'disabled';
const status = text => { $('status').textContent = text; };
async function api(path, data, method = 'POST', signal) {
  const response = await fetch(path, {method, signal, cache: 'no-store',
    headers: {'Content-Type': 'application/json', ...(token ? {'Authorization': 'Bearer ' + token} : {})},
    ...(data === undefined ? {} : {body: JSON.stringify(data)})});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && token) reset();
    throw new Error(typeof result.detail === 'string' ? result.detail : '请求未完成');
  }
  return result;
}
function pause() { generation++; if (controller) controller.abort(); controller = null; $('send').disabled = false; }
function clear() { pause(); history = []; $('messages').replaceChildren(); $('message').value = ''; }
function reset() { clear(); token = ''; $('support').hidden = true; $('auth').hidden = false; $('consent').checked = false; $('eligible').checked = false; }
function add(role, text, label) {
  const item = document.createElement('div'); item.className = 'message ' + role;
  const heading = document.createElement('small'); heading.textContent = label || (role === 'user' ? '你' : 'KinVoice · AI');
  item.append(heading, document.createTextNode(text)); $('messages').append(item); item.scrollIntoView({block: 'nearest'});
}
async function authenticate(register = false) {
  if (!$('auth-form').reportValidity()) return;
  const buttons = $('auth-form').querySelectorAll('button'); buttons.forEach(b => { b.disabled = true; });
  try {
    const result = await api('/auth/' + (register ? 'register' : 'login'), {username: $('username').value, password: $('password').value});
    token = result.access_token; $('password').value = ''; $('auth').hidden = true; $('support').hidden = false; status('已进入。本次对话不会写入服务器数据库。');
  } catch (e) { status(e.message); }
  finally { buttons.forEach(b => { b.disabled = false; }); }
}
$('auth-form').addEventListener('submit', e => { e.preventDefault(); authenticate(); });
$('register').addEventListener('click', () => authenticate(true));
$('chat-form').addEventListener('submit', async e => {
  e.preventDefault();
  if (!$('eligible').checked) return status('请先确认内部评审范围。');
  const message = $('message').value.trim(); if (!message || controller) return;
  controller = new AbortController(); const signal = controller.signal, current = ++generation;
  const timer = setTimeout(() => controller && current === generation && controller.abort(), 55000);
  $('send').disabled = true; status('正在回应…');
  // Send the most recent bounded context; preserve the current message separately.
  let context = history.slice(-20);
  while (context.reduce((n, m) => n + m.content.length, 0) > 16000) context.shift();
  try {
    const result = await api('/support/turn', {message, history: context, goal: $('goal').value,
      eligible: true, external_consent: $('consent').checked}, 'POST', signal);
    if (current !== generation) return;
    if ($('messages').querySelector('.empty')) $('messages').replaceChildren();
    add('user', message); add('assistant', result.reply, result.mode === 'demo' ? '本地固定示例 · 无模型调用' : result.mode === 'remote' ? 'KinVoice · AI 生成，可能有误' : '安全模板 · 尚待专业审阅');
    history.push({role: 'user', content: message}, {role: 'assistant', content: result.reply});
    $('message').value = ''; status('你可以继续、修改草稿，或在这里停下。');
  } catch (error) { if (current === generation) status(error.name === 'AbortError' ? '已暂停接收回应。外部服务已收到的请求可能仍在处理。' : error.message); }
  finally { clearTimeout(timer); if (current === generation) {controller = null; $('send').disabled = false;} }
});
$('pause').addEventListener('click', () => { pause(); status('已暂停接收回应。外部服务已收到的请求可能仍在处理。'); });
$('clear').addEventListener('click', () => { clear(); status('本页对话已清空。外部服务已处理的数据按其隐私政策管理。'); });
$('logout').addEventListener('click', async () => { pause(); try { await api('/auth/logout'); reset(); status('已退出，本页对话已清空。'); } catch (e) { status('退出失败，请重试：' + e.message); } });
$('delete').addEventListener('click', async () => {
  if (!confirm('删除本地演示账号并清空本页对话？已自行导出的文件不会删除。')) return;
  pause(); try { await api('/account', undefined, 'DELETE'); reset(); status('本地演示账号已删除。'); } catch (e) { status(e.message); }
});
$('export').addEventListener('click', () => {
  if (!confirm('导出文件可能包含敏感内容，请自行妥善保存。继续导出？')) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify({type:'local-review-only', messages:history}, null, 2)], {type:'application/json'}));
  const link = document.createElement('a'); link.href = url; link.download = 'kinvoice-local-conversation.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('consent').addEventListener('change', () => { if (!$('consent').checked) {pause(); status('已停止接收本次回应。后续消息不会发送；已提交的数据按服务商政策处理。');} });
window.addEventListener('pagehide', clear);
api('/ping', undefined, 'GET').then(config => {
  mode = config.mode;
  $('mode').textContent = mode === 'demo' ? '本地演示：固定示例，没有调用 AI 模型' : mode === 'remote' ? '外部模型模式：仅在明确同意后发送' : '模型尚未启用：可以检查页面与账号流程';
  $('remote-notice').hidden = mode !== 'remote'; $('provider').textContent = '模型服务商：' + config.provider;
  if (config.provider_privacy_url) $('privacy').href = config.provider_privacy_url;
}).catch(() => status('本地服务无法连接。'));
