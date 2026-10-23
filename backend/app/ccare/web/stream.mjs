// Only stage metadata streams live. A reply is returned after the final checked result.
const messages = {
  session_expired: '登录已失效，请重新登录。',
  model_unavailable: '模型未启用或尚未同意外部处理。',
  processing_failed: '本轮处理未完成，请稍后重试。',
};
export async function readTurnStream(response, onEvent = () => {}) {
  if (!response.body || !response.headers.get('content-type')?.includes('application/x-ndjson'))
    throw new Error('服务返回格式异常，请刷新页面后重试。');
  const reader = response.body.getReader(), decoder = new TextDecoder('utf-8', {fatal:true});
  let buffer = '', bytes = 0, sequence = 0, result = null;
  function consume(line) {
    if (!line.trim()) return;
    let event;
    try { event = JSON.parse(line); } catch { throw new Error('进度记录不完整，请稍后重试。'); }
    if (!event || result || event.sequence !== ++sequence) throw new Error('进度顺序异常，本轮回复未显示。');
    if (sequence === 1 && (event.type !== 'start' || event.protocol !== 'ccare-stream-v1'))
      throw new Error('进度协议不匹配，请刷新页面。');
    if (event.type === 'error') {
      const error = new Error(messages[event.code] || messages.processing_failed); error.code = event.code; throw error;
    }
    if (event.type === 'result') {
      const r = event.result;
      if (!r || typeof r.reply !== 'string' || !['demo','remote','safety_template','safe_fallback'].includes(r.mode)
          || !Array.isArray(r.checks) || !Number.isInteger(r.model_calls))
        throw new Error('回应格式异常，本轮回复未显示。');
      result = r;
    } else if (['start','heartbeat','stage','policy'].includes(event.type)) {
      onEvent(event);
    } else throw new Error('未知进度记录，本轮回复未显示。');
  }
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > 524288) throw new Error('服务返回过大，本轮回复未显示。');
      buffer += decoder.decode(value, {stream:true});
      let newline;
      while ((newline = buffer.indexOf('\n')) !== -1) {
        consume(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1);
      }
      if (buffer.length > 131072) throw new Error('进度记录过大，本轮回复未显示。');
    }
    buffer += decoder.decode();
    if (buffer.trim()) consume(buffer);
    if (!result) throw new Error('连接提前结束，尚未收到通过检查的回应。');
    return result;
  } finally {
    try { await reader.cancel(); } catch { /* A disconnected stream is already cancelled. */ }
    reader.releaseLock();
  }
}
