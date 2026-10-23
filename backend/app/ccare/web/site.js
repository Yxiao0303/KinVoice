import { Conversation } from './session.mjs';
import { readTurnStream } from './stream.mjs';
import { technicalReport } from './report.mjs';

const $ = id => document.getElementById(id);
const conversation = new Conversation();
let token = '', mode = 'disabled', controller = null, register = false, requestTimeout = 55000, supportsProgress = false;
let selectedCase = null, wantsInspector = false, toastTimer, expiryTimer, authVersion = 0;
const liveStages = new Map();
const cases = {
  choice: {goal: 'clarify', text: '虚构案例：父母反对我选择设计专业，希望我换成他们认可的方向。我很难过，想先理清自己的想法。', caption: '案例 01：用户想理清思绪 → 选择澄清，不代替用户作决定。'},
  boundary: {goal: 'draft', text: '虚构案例：刚和妈妈吵完。虽然我点了准备表达，但现在不想和解，也不要给我建议，我只想有人听我说。', caption: '案例 02：界面选了准备表达，文字明确拒绝建议 → 保留倾听，尊重当下意愿。'},
  unsafe: {goal: 'draft', text: '虚构案例：爸爸以前打我。我现在在宿舍安全，想写一段话回他。', caption: '案例 03：出现家庭不安全线索 → 暂不进入沟通草稿，退回倾听。此规则尚待专业审阅。'},
};
const strategyNames = {listen:'倾听', clarify:'澄清事实与需求', ground:'短暂稳定', draft:'沟通草稿', safety:'安全模板'};
const reasonNames = {urgent_guard:'紧急线索优先',family_contact_restricted:'家庭不安全，限制沟通草稿',current_refusal:'本轮明确拒绝建议',current_listen_intent:'本轮明确希望被倾听',current_text_intent:'本轮文字明确了支持需求',user_selected_goal:'采用用户选择'};
const stageNames = {state:'状态估计',generate:'候选生成',rewrite:'重写',verify:'回应校验'};
const failureNames = {invalid_key:'模型密钥无效',insufficient_balance:'模型账户余额不足',rate_limited:'模型请求过于频繁',provider_timeout:'模型服务等待超时',turn_timeout:'本轮处理超时',connection_error:'无法连接模型服务',incomplete_output:'模型输出被截断或未正常结束',invalid_state_or_verdict:'状态证据或校验格式未通过',verification_rejected:'候选回应未通过检查',invalid_request:'服务商未接受请求参数'};
function status(text, error = false) { $('chat-status').textContent = text; $('chat-status').classList.toggle('error', error); }
function toast(text) { clearTimeout(toastTimer); $('toast').textContent = text; $('toast').hidden = false; toastTimer = setTimeout(() => $('toast').hidden = true, 4500); }
function count() { $('char-count').textContent = `${$('message').value.length} / 2000`; }
function setBusy() {
  const busy = conversation.pending !== null;
  $('send').disabled = busy; $('pause').disabled = !busy; $('thinking').hidden = !busy;
  $('message').disabled = busy; $('chat-form').setAttribute('aria-busy', String(busy));
}
async function api(path, data, method = 'POST', signal, onEvent) {
  const sentToken = token;
  const response = await fetch(path, {method, signal, cache:'no-store',
    headers:{'Content-Type':'application/json', ...(sentToken ? {Authorization:'Bearer '+sentToken} : {})},
    ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  if (response.ok && onEvent) {
    try { return await readTurnStream(response, onEvent); }
    catch (error) { if (error.code === 'session_expired' && sentToken === token) reset(); throw error; }
  }
  let result;
  try { result = await response.json(); } catch { throw new Error('服务返回格式异常，请稍后重试。'); }
  if (!response.ok) {
    if (response.status === 401 && sentToken && sentToken === token) reset();
    throw new Error(typeof result.detail === 'string' ? result.detail : '请求未完成，请重试。');
  }
  return result;
}
function renderMessages() {
  $('messages').replaceChildren();
  $('empty-chat').hidden = conversation.messages.length > 0;
  for (const message of conversation.messages) {
    const item = document.createElement('article'); item.className = 'message ' + message.role;
    const body = document.createElement('div');
    if (message.role === 'assistant') {
      const icon = document.createElement('img'); icon.src = '/assets/mark.svg'; icon.alt = ''; item.append(icon);
      const label = document.createElement('small'); label.className = 'message-label';
      label.textContent = message.mode === 'demo' ? 'KinVoice · 固定示例，无模型调用' : message.mode === 'remote' ? 'KinVoice · AI 生成，可能有误' : 'KinVoice · 固定退回模板，待专业审阅'; body.append(label);
    }
    const content = document.createElement('p'); content.className = 'message-content'; content.textContent = message.content; body.append(content);
    if (message.role === 'assistant' && message.strategy === 'draft' && ['remote','demo'].includes(message.mode)) {
      const editor = document.createElement('details'); editor.className = 'draft-editor';
      const summary = document.createElement('summary'); summary.textContent = '修改这段草稿';
      const input = document.createElement('textarea'); input.value = message.editedDraft ?? message.content; input.maxLength = 2000; input.setAttribute('aria-label','可修改的沟通草稿');
      input.addEventListener('input', () => message.editedDraft = input.value);
      const note = document.createElement('small'); note.textContent = '修改只留在本页，不会自动发送，也不会替换模型对话记录。';
      editor.append(summary,input,note); body.append(editor);
    }
    if (message.status === 'paused' || message.status === 'failed') {
      const meta = document.createElement('small'); meta.className = 'message-meta';
      meta.textContent = message.status === 'paused' ? '已暂停 · 本条不进入后续上下文' : '未完成 · 可重新输入后发送'; body.append(meta);
    }
    item.append(body); $('messages').append(item);
  }
  setBusy();
  $('conversation-area').scrollTop = $('conversation-area').scrollHeight;
}
function renderStages(stages) {
  $('trace-stages').replaceChildren();
  for (const stage of stages) {
    const item = document.createElement('li');
    const state = {running:'正在处理',completed:'调用完成',failed:'调用失败',cancelled:'已中断'}[stage.status] || '状态未知';
    item.textContent = `${stageNames[stage.stage] || stage.stage} · ${state}${Number.isInteger(stage.elapsed_ms) ? ' · '+stage.elapsed_ms+' ms' : ''}${stage.model ? ' · '+stage.model : ''}`;
    item.dataset.status = stage.status; $('trace-stages').append(item);
  }
}
function updateProgress(event) {
  if (event.type === 'stage') {
    liveStages.set(event.index, event); renderStages(liveStages.values());
    $('trace-calls').textContent = String(event.index);
    if (event.event === 'started') $('thinking-label').textContent = `正在${stageNames[event.stage] || '处理'} · 尚未发布回复`;
    $('trace-check').textContent = '处理中。候选文本通过本轮检查后才会显示。';
  } else if (event.type === 'policy') {
    $('trace-strategy').textContent = `当前策略：${strategyNames[event.strategy] || '待确认'}。` + (event.reasons || []).map(code => reasonNames[code] || code).join('；');
    $('trace-allowed').textContent = '本轮允许：' + (event.allowed || []).map(s => strategyNames[s] || s).join('、');
  }
}
function updateTrace(result = null) {
  $('case-caption').textContent = selectedCase ? cases[selectedCase].caption : '观察用户选择怎样影响回应策略。显示内容来自实际接口返回。';
  if (!result) {
    $('trace-state').textContent = '等待本轮输入'; $('trace-strategy').textContent = '结合用户选择，检查沟通边界';
    $('trace-source').textContent = '等待接口返回'; $('trace-check').textContent = '模型校验与专业审阅未完成'; $('trace-calls').textContent = '—';
    $('trace-allowed').textContent = '等待本轮决策'; $('trace-evidence').replaceChildren(); $('trace-stages').replaceChildren(); $('trace-cost').textContent = ''; return;
  }
  const state = result.state || {};
  $('trace-state').textContent = state.risk === 'urgent' ? '命中紧急线索。此判断不等于临床诊断。' : state.family_unsafe ? '检测到家庭不安全线索；无法据此还原完整关系。' : state.risk === 'ordinary' ? '模型估计为普通支持情境，仍可能误判。' : '风险状态仍为未知；未命中关键词不等于确认安全。';
  const decision = result.decision;
  $('trace-strategy').textContent = `${strategyNames[result.strategy] || result.strategy}。` + (result.mode === 'safe_fallback' ? `原定策略为${strategyNames[decision?.selected] || '未确定'}，本轮改用固定退回回应。` : (decision?.reasons || []).map(code => reasonNames[code] || code).join('；'));
  $('trace-source').textContent = result.mode === 'demo' ? '固定示例。没有执行大模型状态估计或生成。' : result.mode === 'remote' ? '外部模型生成；具体服务商见本次同意说明。' : '固定安全或服务退回模板。';
  $('trace-check').textContent = result.checks.includes('model_check_passed_unvalidated') ? '规则及模型检查通过；模型校验可靠性与专业审阅仍待验证。' : '本地线索检查已执行。本轮未通过模型校验流程；模板待专业审阅。';
  $('trace-calls').textContent = String(result.model_calls);
  $('trace-allowed').textContent = '本轮允许：' + (decision?.allowed || []).map(s => strategyNames[s] || s).join('、');
  $('trace-evidence').replaceChildren();
  for (const evidence of decision?.evidence || []) {
    const item = document.createElement('li'); item.textContent = `${evidence.source === 'current' ? '本轮' : '历史第 '+(evidence.turn+1)+' 条'}原话：${evidence.quote}`; $('trace-evidence').append(item);
  }
  if (!$('trace-evidence').children.length) { const item = document.createElement('li'); item.textContent = '没有定位到用于约束决策的原话证据。'; $('trace-evidence').append(item); }
  renderStages(result.stages || []);
  const completeUsage = (result.usage || []).every(u => Number.isInteger(u?.total_tokens));
  const totalTokens = completeUsage ? (result.usage || []).reduce((sum,u) => sum+u.total_tokens,0) : '未知（服务商未完整返回）';
  $('trace-cost').textContent = `后端耗时 ${result.elapsed_ms ?? '未知'} ms · 总 token ${totalTokens}${result.failure_code ? ' · '+(failureNames[result.failure_code] || '模型处理未完成') : ''}`;
}
function inspector(open) { wantsInspector = open; $('inspector').hidden = !open; $('chat-view').classList.toggle('with-inspector', open); $('toggle-inspector').setAttribute('aria-pressed', String(open)); }
function pause(silent = false) {
  const wasPending = conversation.pending !== null;
  if (controller) controller.abort(); controller = null; conversation.pause(); renderMessages();
  if (wasPending) {
    $('trace-check').textContent = supportsProgress ? '本页已停止接收。后端检测到断连后中止后续步骤；上游已接收的调用可能继续。' : '旧版服务只停止本页接收，后端仍可能继续。';
    $('trace-cost').textContent = '本轮未完成，总用量未知。';
    renderStages([...liveStages.values()].map(s => s.status === 'running' ? {...s,status:'cancelled'} : s));
  }
  if (!silent) status(supportsProgress ? '已暂停并关闭本轮连接。后端检测到断连后停止后续步骤，上游调用可能继续。' : '已暂停本页接收。旧版后端与上游调用可能继续。');
}
function clear() {
  pause(true); conversation.clear(); selectedCase = null; $('message').value = ''; count(); renderMessages(); updateTrace();
  status('本页对话已清空。不会恢复之前的回复。');
}
function reset() {
  clearTimeout(expiryTimer); clear(); token = ''; $('eligible').checked = false; $('consent').checked = false;
  $('info-dialog').close(); location.hash = 'home'; route();
}
function route() {
  const chat = location.hash === '#chat' && !!token;
  $('home-view').hidden = chat; $('chat-view').hidden = !chat;
  if (location.hash === '#chat' && !token) openAuth();
  if (chat) { inspector(wantsInspector); renderMessages(); }
}
function openAuth() { $('auth-status').textContent = ''; if (!$('auth-dialog').open) $('auth-dialog').showModal(); }
function enter() {
  if (!token) return openAuth();
  location.hash = 'chat'; route(); if (selectedCase) applyCase(selectedCase);
}
function applyCase(name) {
  selectedCase = name; const scenario = cases[name];
  document.querySelector(`input[name="goal"][value="${scenario.goal}"]`).checked = true;
  $('message').value = scenario.text; count(); updateTrace(conversation.lastResult);
  status(conversation.messages.length ? '案例已填入。独立演示新案例前，建议先清空旧对话。' : '虚构案例已填入。确认演示范围后，由你发送。');
}
document.querySelectorAll('[data-enter]').forEach(button => button.addEventListener('click', enter));
document.querySelectorAll('[data-scenario]').forEach(button => button.addEventListener('click', () => {
  if (conversation.pending !== null) return toast('先暂停当前回复，再切换情境。');
  selectedCase = button.dataset.scenario; wantsInspector = true; enter();
}));
$('open-presentation').addEventListener('click', () => { selectedCase = 'choice'; wantsInspector = true; enter(); });
document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => $(button.dataset.closeDialog).close()));
$('auth-dialog').addEventListener('close', () => { authVersion++; $('password').value = ''; });
$('auth-toggle').addEventListener('click', () => {
  register = !register; $('auth-title').textContent = register ? '留一点空间给自己。' : '欢迎回来。';
  $('auth-description').textContent = register ? '创建本地演示账号，开始体验。' : '登录本地账号，开始这一次对话。';
  $('auth-submit').textContent = register ? '创建账号并进入 ↗' : '登录并进入 ↗';
  $('auth-switch-text').textContent = register ? '已经有账号？' : '还没有本地账号？';
  $('auth-toggle').textContent = register ? '去登录' : '创建账号'; $('auth-status').textContent = '';
  $('password').autocomplete = register ? 'new-password' : 'current-password';
});
$('show-password').addEventListener('click', () => {
  const show = $('password').type === 'password'; $('password').type = show ? 'text' : 'password';
  $('show-password').textContent = show ? '隐藏' : '显示'; $('show-password').setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
});
$('auth-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!$('auth-form').reportValidity()) return;
  const version = ++authVersion; const username = $('username').value;
  $('auth-submit').disabled = true; $('auth-toggle').disabled = true; $('auth-status').textContent = '正在连接本地账号…';
  try {
    const result = await api('/auth/' + (register ? 'register' : 'login'), {username, password:$('password').value});
    if (version !== authVersion) return;
    token = result.access_token; $('account-name').textContent = username; $('auth-dialog').close();
    expiryTimer = setTimeout(() => { reset(); toast('登录已到期，请重新登录。'); }, result.expires_in * 1000);
    enter(); toast('已进入。对话只在当前页面保留。');
  } catch (error) { if (version === authVersion) $('auth-status').textContent = error.message; }
  finally { $('auth-submit').disabled = false; $('auth-toggle').disabled = false; }
});
$('chat-form').addEventListener('submit', async event => {
  event.preventDefault(); if (conversation.pending !== null) return;
  if (!$('eligible').checked) { status('请先确认本次使用虚构大学生情境进行演示。', true); $('eligible').focus(); return; }
  const message = $('message').value.trim(); if (!message) return;
  if (mode === 'remote' && !$('consent').checked) { status('请先阅读服务商隐私说明，并选择是否同意本轮外部处理。', true); return; }
  const history = conversation.context(), requestGoal = document.querySelector('input[name="goal"]:checked').value;
  const ticket = conversation.begin(message); const requestController = new AbortController(); controller = requestController;
  const timer = setTimeout(() => requestController.abort(), requestTimeout);
  $('message').value = ''; count(); $('thinking-label').textContent = mode === 'demo' ? '固定示例 · 1 秒演示节奏' : '正在等待回应';
  liveStages.clear(); updateTrace();
  renderMessages(); status(mode === 'demo' ? '本地固定示例，未调用模型。可点击暂停演示回复。' : '正在回应，你可以随时暂停。');
  try {
    const result = await api(supportsProgress ? '/support/stream' : '/support/turn', {message, history, goal:requestGoal, eligible:true, external_consent:$('consent').checked}, 'POST', requestController.signal, supportsProgress ? event => {
      if (!requestController.signal.aborted && conversation.pending === ticket) updateProgress(event);
    } : undefined);
    // Explicitly disclosed pacing for presentations, not simulated model latency.
    if (mode === 'demo') await new Promise(resolve => setTimeout(resolve, 1000));
    if (requestController.signal.aborted || !conversation.finish(ticket, {...result, requestGoal})) return;
    renderMessages(); updateTrace({...result, requestGoal}); status(result.failure_code ? (failureNames[result.failure_code] || '本次模型处理未完成')+'，已显示固定退回回应。' : '你可以继续说，或在这里停下。', !!result.failure_code);
  } catch (error) {
    if (conversation.fail(ticket)) {
      renderMessages(); $('trace-check').textContent = '本轮未完成，未发布候选回复。'; $('trace-cost').textContent = '本轮总用量未知。';
      renderStages([...liveStages.values()].map(s => s.status === 'running' ? {...s,status:'failed'} : s));
      status(error.name === 'AbortError' ? '等待超时，未显示回复。可以稍后重试。' : error.message, true);
    }
  } finally { clearTimeout(timer); if (controller === requestController) controller = null; setBusy(); }
});
$('message').addEventListener('input', count);
$('message').addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !event.isComposing) $('chat-form').requestSubmit(); });
$('pause').addEventListener('click', () => pause());
$('clear').addEventListener('click', clear); $('new-chat').addEventListener('click', clear);
$('toggle-inspector').addEventListener('click', () => inspector(!wantsInspector)); $('close-inspector').addEventListener('click', () => inspector(false));
for (const id of ['show-info', 'mobile-info']) $(id).addEventListener('click', () => $('info-dialog').showModal());
async function logout() { pause(true); try { await api('/auth/logout'); reset(); toast('已退出，本页对话已清空。'); } catch (error) { toast('退出未完成：'+error.message); } }
$('logout').addEventListener('click', logout); $('mobile-logout').addEventListener('click', logout);
$('delete-account').addEventListener('click', async () => {
  if (!confirm('删除本地演示账号并清空本页对话？已导出的文件不会删除。')) return;
  pause(true); try { await api('/account', undefined, 'DELETE'); reset(); toast('本地演示账号已删除。'); } catch (error) { toast(error.message); }
});
function exportConversation() {
  if (!conversation.messages.length) return toast('当前没有可导出的对话。');
  if (!confirm('导出文件可能包含敏感内容，请妥善保存。继续导出？')) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify({type:'local-demonstration', messages:conversation.messages}, null, 2)], {type:'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = 'kinvoice-conversation.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('export').addEventListener('click', exportConversation); $('mobile-export').addEventListener('click', exportConversation);
const reportButton = document.createElement('button');
reportButton.className = 'button outline full'; reportButton.id = 'export-technical'; reportButton.textContent = '导出技术记录（不含对话）';
$('inspector').append(reportButton);
reportButton.addEventListener('click', () => {
  if (!conversation.messages.length) return toast('完成一次演示后，可导出技术记录。');
  const url = URL.createObjectURL(new Blob([technicalReport(conversation.messages)], {type:'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = `kinvoice-technical-${new Date().toISOString().replace(/[:.]/g,'-')}.md`;
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('已导出工程记录，不包含对话原文和生成回复。');
});
$('consent').addEventListener('change', () => { if (!$('consent').checked) { pause(true); status('已撤回后续外发同意。服务商已收到的数据按其隐私政策处理。'); } });
window.addEventListener('hashchange', route);
window.addEventListener('pagehide', () => { pause(true); conversation.clear(); token = ''; renderMessages(); });
window.addEventListener('pageshow', event => { if (event.persisted) reset(); });
api('/ping', undefined, 'GET').then(config => {
  mode = config.mode;
  supportsProgress = config.progress_stream === 'ccare-stream-v1';
  $('technology-status').textContent = mode === 'remote' ? '当前已配置模型模式；实际调用与检查结果见每轮技术面板。专业审阅待完成。' : '当前：本地规则与固定示例可演示；真实模型和专业评审待接入。';
  requestTimeout = Math.min(105000, Math.max(15000, (config.turn_timeout_seconds || 45)*1000+10000));
  $('home-mode').textContent = mode === 'demo' ? '本地固定示例 · 未调用大模型 · 专业审阅待完成' : mode === 'remote' ? '外部模型已配置 · 明确同意后发送 · 专业审阅待完成' : '模型未启用 · 可浏览网站与账号流程';
  $('chat-mode').textContent = mode === 'demo' ? '演示模式' : mode === 'remote' ? config.model || '模型模式' : '未接入模型';
  $('session-mode').textContent = mode === 'demo' ? '固定示例演示，没有模型调用。请勿输入真实咨询信息。' : '仅供内部评审。请使用虚构情境，不提供诊断或紧急救援。';
  $('remote-notice').hidden = mode !== 'remote'; $('provider').textContent = config.provider;
  if (config.provider_privacy_url && /^https:\/\//.test(config.provider_privacy_url)) $('privacy-link').href = config.provider_privacy_url;
}).catch(() => { $('home-mode').textContent = '本地服务未连接，请启动后端后刷新。'; $('chat-mode').textContent = '服务未连接'; });
route();
