const strategies = {listen:'倾听',clarify:'澄清',ground:'短暂稳定',draft:'沟通草稿',safety:'安全模板'};
const sources = {demo:'固定示例（无模型调用）',remote:'模型生成',safety_template:'固定安全模板',safe_fallback:'固定退回回应'};
const safe = value => String(value ?? '未知').replace(/[\r\n|]/g, ' ');
export function technicalReport(messages, now = new Date()) {
  const rows = messages.filter(m => m.role === 'assistant' && m.result);
  const incomplete = messages.filter(m => m.role === 'user' && m.status !== 'sent').length;
  const lines = ['# KinVoice 演示技术记录', '', `导出时间：${now.toISOString()}`, '',
    '本文件不包含对话原文、原话证据、生成回复、账号或密钥。仅用于复查工程行为，不能证明心理支持效果或安全可靠性。', '',
    `已收到结果：${rows.length} 轮。未完成或暂停：${incomplete} 轮。未完成轮次的服务商用量未知，不计为零。`, ''];
  rows.forEach((m, i) => {
    const r = m.result, usage = r.usage || [];
    const known = usage.length === r.model_calls && usage.every(u => Number.isInteger(u?.total_tokens) && u.total_tokens >= 0);
    lines.push(`## 第 ${i+1} 个已完成结果`, '',
      `来源：${sources[r.mode] || '未知'}。策略版本：${safe(r.policy_version)}。`,
      `用户选择：${strategies[r.requestGoal] || '未知'}；实际交付：${strategies[r.strategy] || '未知'}。`,
      `允许策略：${(r.decision?.allowed || []).map(s => strategies[s] || '未知').join('、')}。`,
      `调用次数：${safe(r.model_calls)}；已返回总 token：${known ? usage.reduce((n,u) => n+u.total_tokens,0) : '未知或不完整'}；后端耗时：${safe(r.elapsed_ms)} ms。`,
      `校验代码：${(r.checks || []).map(safe).join('、')}。失败代码：${safe(r.failure_code || '无')}。`, '',
      '| 步骤 | 状态 | 耗时 ms | 返回模型 |', '|---|---|---:|---|');
    for (const s of r.stages || []) lines.push(`| ${safe(s.stage)} | ${safe(s.status)} | ${safe(s.elapsed_ms)} | ${safe(s.model)} |`);
    if (!r.stages?.length) lines.push('| 未执行模型步骤 | — | — | — |');
    lines.push('', '“调用完成”只表示收到返回，不能代替回应校验或专业审阅。', '');
  });
  return lines.join('\n');
}
