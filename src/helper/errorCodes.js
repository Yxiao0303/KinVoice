/**
 * KinVoice 错误码表（完整版 v2）
 * 
 * 结构：{ 错误码: { message: '用户提示', detail: '详细说明', level: '严重度' } }
 * level: toast（轻提示，自动消失）| warn（警告）| error（错误，持续2s）| fatal（致命，需刷新页面）
 * 
 * 错误码分段：
 *   1xxx  网络层错误（快应用 @system.fetch 底层）
 *   2xxx  HTTP 状态码错误（后端返回 4xx/5xx）
 *   3xxx  业务层错误（具体接口场景，后端 detail 映射 + 前端本地判断）
 *   4xxx  本地存储错误（@system.storage 读写）
 *   5xxx  前端校验错误（参数拦截）
 *   6xxx  数据异常错误（后端返回 2xx 但数据格式/字段异常）
 */

// ===================================================================
//  1xxx — 网络层错误（@system.fetch 底层）
// ===================================================================
const NETWORK_ERRORS = {
  // 客户端超时（20s 无响应）
  1001: { message: '网络请求超时，请检查网络后重试', detail: 'fetch timeout > 20s', level: 'error' },
  // 设备离线 / 飞行模式
  1002: { message: '当前网络不可用，请检查连接', detail: 'device offline / network unavailable', level: 'error' },
  // DNS 解析失败
  1003: { message: '服务器地址解析失败，请稍后重试', detail: 'DNS resolution failed', level: 'error' },
  // TCP 连接被拒绝（后端未启动或端口不对）
  1004: { message: '无法连接到服务器，请确认后端已启动', detail: 'connection refused (backend down)', level: 'error' },
  // SSL/TLS 握手失败
  1005: { message: '安全连接失败，请检查网络环境', detail: 'SSL/TLS certificate error', level: 'error' },
  // 用户主动取消请求
  1006: { message: '请求已取消', detail: 'request cancelled by user', level: 'toast' },
  // 未知网络错误
  1099: { message: '网络异常，请稍后重试', detail: 'unknown network error', level: 'error' },
}

// ===================================================================
//  2xxx — HTTP 状态码错误（后端返回 4xx/5xx）
// ===================================================================
const HTTP_ERRORS = {
  2001: { message: '请求参数有误，请重试', detail: '400 Bad Request - client sent invalid data', level: 'warn' },
  2002: { message: '身份验证失败', detail: '401 Unauthorized', level: 'error' },
  2003: { message: '没有权限执行此操作', detail: '403 Forbidden', level: 'error' },
  2004: { message: '请求的资源不存在', detail: '404 Not Found', level: 'toast' },
  2005: { message: '请求方式不正确', detail: '405 Method Not Allowed', level: 'error' },
  2006: { message: '服务器处理超时，请稍后重试', detail: '408 server timeout', level: 'error' },
  2007: { message: '上传内容过大，请精简后重试', detail: '413 Payload Too Large', level: 'warn' },
  2008: { message: '提交的数据格式不正确', detail: '422 validation error from backend', level: 'warn' },
  2009: { message: '请求太频繁，请稍等片刻再试', detail: '429 rate limited', level: 'warn' },
  2010: { message: '服务器内部错误，请稍后重试', detail: '500 Internal Server Error', level: 'error' },
  2011: { message: '服务器网关错误，请稍后重试', detail: '502 Bad Gateway', level: 'error' },
  2012: { message: '服务暂时不可用，请稍后重试', detail: '503 Service Unavailable', level: 'error' },
  2013: { message: '服务器响应超时，请稍后重试', detail: '504 Gateway Timeout', level: 'error' },
}

// ===================================================================
//  3xxx — 业务层错误（按接口分组）
// ===================================================================
const BUSINESS_ERRORS = {
  // ── 破冰转换 /convert ──
  // 输入为空（前端拦截 + 后端400校验）
  3001: { message: '请先输入想说的话', detail: 'convert: empty text / raw_text', level: 'toast' },
  // LLM 调用失败（网络/超时/API错误），后端已降级返回默认值
  3002: { message: 'AI 转换暂时不可用，已使用本地降级展示', detail: 'convert: LLM call failed, fallback shown', level: 'toast' },
  // LLM 未配置（API base_url 或 key 为空），httpx 抛协议异常
  3003: { message: 'AI 转换服务未配置，请检查 API 设置', detail: 'convert: LLM base_url or key not configured', level: 'error' },
  // 转换结果为空（LLM 返回了 200 但内容为空）
  3004: { message: '转换结果异常，已使用本地降级展示', detail: 'convert: LLM returned empty result', level: 'toast' },

  // ── 陪伴对话 /chat ──
  // 输入为空（前端拦截）
  3010: { message: '请输入要说的话', detail: 'chat: empty message', level: 'toast' },
  // LLM 调用失败（网络/超时/API错误）
  3011: { message: 'AI 暂时无法回复，已切换到本地应答模式', detail: 'chat: LLM call failed, fallback used', level: 'toast' },
  // LLM 未配置（API base_url 或 key 为空）
  3012: { message: '对话服务未配置，请检查 API 设置', detail: 'chat: LLM base_url or key not configured', level: 'error' },
  // conversation_id 不存在（xia 会话持久化模式）
  3013: { message: '会话不存在，请新建对话', detail: 'chat: conversation not found (404)', level: 'toast' },
  // 后端返回 200 但 reply 字段为空
  3014: { message: 'AI 回复异常，已切换到本地应答模式', detail: 'chat: response.reply is empty', level: 'toast' },
  // 消息保存到数据库失败（xia 持久化模式）
  3015: { message: '对话记录保存失败，但回复仍然有效', detail: 'chat: message DB save failed', level: 'toast' },

  // ── 对话总结 /chat/summarize ──
  // LLM 调用失败或网络错误
  3020: { message: '对话总结失败，将保留历史稍后重试', detail: 'summarize: LLM call or network failed', level: 'toast' },
  // 对话历史不足（少于2轮）
  3021: { message: '对话内容太少，请多聊几句后再总结', detail: 'summarize: not enough messages (< 2)', level: 'toast' },
  // LLM 返回空结果（无卡片可生成）
  3022: { message: '未从对话中提取到可记录的内容', detail: 'summarize: LLM returned no results', level: 'toast' },
  // 部分卡片创建失败（混合结果）
  3023: { message: '部分对话总结未保存成功', detail: 'summarize: partial card creation failed', level: 'toast' },

  // ── 经验卡片 /cards ──
  // 表单必填字段缺失（前端拦截）
  3030: { message: '请填写标题和内容', detail: 'cards: required fields (title/content) missing', level: 'toast' },
  // 卡片不存在（PUT/DELETE 时 id 找不到）
  3031: { message: '卡片不存在，可能已被删除', detail: 'cards: card not found (404)', level: 'toast' },
  // 创建失败 → 已降级保存本地
  3032: { message: '卡片已保存到本地（网络不可用）', detail: 'cards: create API failed, saved locally', level: 'toast' },
  // 更新失败 → 已降级更新本地
  3033: { message: '卡片已更新本地（网络不可用）', detail: 'cards: update API failed, updated locally', level: 'toast' },
  // 删除失败 → 已降级删除本地
  3034: { message: '卡片已从本地删除（网络不可用）', detail: 'cards: delete API failed, removed locally', level: 'toast' },
  // 同步失败 → 保持本地数据不变
  3035: { message: '同步未完成，将使用本地数据', detail: 'cards: sync API failed, local data unchanged', level: 'toast' },
  // 收藏非 AI 回复（后端 400 拦截）
  3036: { message: '只能收藏 AI 的回复', detail: 'cards: can only favorite assistant messages (400)', level: 'toast' },
  // 收藏时 message 不存在（后端 404）
  3037: { message: '该消息不存在，无法收藏', detail: 'cards: favorite message not found (404)', level: 'toast' },
  // 收藏时数据库写入失败
  3038: { message: '收藏失败，请稍后重试', detail: 'cards: favorite DB write failed', level: 'toast' },

  // ── 家庭成员档案 /profiles ──
  // 表单必填字段缺失（前端拦截）
  3040: { message: '请填写姓名和档案内容', detail: 'profiles: required fields (name) missing', level: 'toast' },
  // 档案不存在（PUT/DELETE 时 id 找不到）
  3041: { message: '档案不存在，可能已被删除', detail: 'profiles: profile not found (404)', level: 'toast' },
  // 创建/更新/删除 失败
  3042: { message: '档案操作失败，请重试', detail: 'profiles: operation API failed', level: 'error' },
  // 创建失败 → 降级本地
  3043: { message: '档案已保存到本地（网络不可用）', detail: 'profiles: create API failed, saved locally', level: 'toast' },
  // 同名档案已存在
  3044: { message: '该姓名的档案已存在', detail: 'profiles: duplicate profile name', level: 'warn' },

  // ── 通用业务错误 ──
  3099: { message: '服务异常，请稍后重试', detail: 'general business error', level: 'error' },
}

// ===================================================================
//  4xxx — 本地存储错误（@system.storage）
// ===================================================================
const STORAGE_ERRORS = {
  // storage.get() 失败
  4001: { message: '本地数据读取失败，将使用默认数据', detail: 'storage.get() failed', level: 'warn' },
  // storage.set() 失败
  4002: { message: '本地保存失败，请检查存储空间', detail: 'storage.set() failed', level: 'error' },
  // storage.delete() 失败
  4003: { message: '本地数据清理失败', detail: 'storage.delete() failed', level: 'warn' },
  // 存储空间不足（quota exceeded）
  4004: { message: '本地存储空间不足，请清理缓存', detail: 'storage quota exceeded', level: 'warn' },
  // JSON 解析失败（storage 里存的不是合法 JSON）
  4005: { message: '本地数据格式异常，已重置', detail: 'storage: JSON.parse() failed', level: 'warn' },
  // storage key 不存在（首次使用）
  4006: { message: '', detail: 'storage: key not found (first use)', level: 'toast' },
}

// ===================================================================
//  5xxx — 前端参数校验错误（拦截后不发送请求）
// ===================================================================
const VALIDATION_ERRORS = {
  // 通用空输入
  5001: { message: '输入内容不能为空', detail: 'validation: empty input', level: 'toast' },
  // 文本超长（>2000字）
  5002: { message: '输入内容过长，最多2000字', detail: 'validation: text exceeds 2000 chars', level: 'toast' },
  // 名称无效
  5003: { message: '请输入有效的名称', detail: 'validation: invalid name', level: 'toast' },
  // 分类未选择
  5004: { message: '请选择一个分类', detail: 'validation: category not selected', level: 'toast' },
  // URL 格式错误
  5005: { message: '服务器地址格式不正确，请检查配置', detail: 'validation: invalid baseUrl format', level: 'error' },
  // 必填字段缺失
  5006: { message: '请填写完整信息', detail: 'validation: required fields missing', level: 'toast' },
}

// ===================================================================
//  6xxx — 数据异常错误（后端 2xx 但数据异常）
// ===================================================================
const DATA_ERRORS = {
  // 响应体为空
  6001: { message: '服务器返回了空响应，请稍后重试', detail: 'response body is null/undefined', level: 'error' },
  // JSON 解析失败（response.data 不是合法 JSON）
  6002: { message: '服务器返回了异常数据，请稍后重试', detail: 'response JSON parse failed', level: 'error' },
  // 响应缺少关键字段
  6003: { message: '服务器返回数据不完整', detail: 'response missing required field', level: 'warn' },
  // 响应类型不匹配（期望对象/数组，实际不是）
  6004: { message: '服务器返回格式异常', detail: 'response type mismatch', level: 'error' },
}

// ===================================================================
//  后端 detail 消息 → 业务错误码 映射表
//  [{ pattern: 'detail子串', code: 业务码 }]
//  先精确匹配，再包含匹配
// ===================================================================
const DETAIL_TO_CODE = [
  // ═══ 精确匹配（优先级高） ═══
  { pattern: '卡片不存在', code: 3031 },
  { pattern: '档案不存在', code: 3041 },
  { pattern: '消息不存在', code: 3037 },
  { pattern: '只能收藏 AI 回复', code: 3036 },
  { pattern: '请提供 text 或 raw_text 字段', code: 3001 },

  // ═══ 包含匹配 ═══
  { pattern: 'Method Not Allowed', code: 2005 },
  { pattern: '服务器内部错误', code: 2010 },
  { pattern: 'UnsupportedProtocol', code: 3003 },       // httpx 抛：缺少 http://
  { pattern: 'InvalidAuthentication', code: 2002 },      // API key 无效
  { pattern: 'RateLimitError', code: 2009 },             // 频率限制
  { pattern: 'context_length_exceeded', code: 5002 },    // 内容超长
  { pattern: 'timed out', code: 2006 },                  // 后端 LLM 超时
]

// ===================================================================
//  合并全部
// ===================================================================
const ALL_ERRORS = Object.assign(
  {},
  NETWORK_ERRORS,
  HTTP_ERRORS,
  BUSINESS_ERRORS,
  STORAGE_ERRORS,
  VALIDATION_ERRORS,
  DATA_ERRORS
)

/**
 * 根据错误码获取错误描述
 * @param {number} code - 错误码
 * @returns {{ message: string, detail: string, level: string }}
 */
export function getErrorInfo(code) {
  return ALL_ERRORS[code] || {
    message: '未知错误（' + code + '），请稍后重试',
    detail: `unknown error code: ${code}`,
    level: 'error',
  }
}

/**
 * 根据后端返回的 detail 消息，映射到业务错误码
 * @param {string} detail - 后端返回的 detail 字段
 * @returns {number|null} 错误码 或 null
 */
export function mapDetailToCode(detail) {
  if (!detail) return null
  // 精确匹配
  for (const entry of DETAIL_TO_CODE) {
    if (detail === entry.pattern) return entry.code
  }
  // 包含匹配
  for (const entry of DETAIL_TO_CODE) {
    if (detail.includes(entry.pattern)) return entry.code
  }
  return null
}

/**
 * HTTP 状态码 → 前端错误码
 */
export function httpStatusToCode(statusCode) {
  const map = {
    400: 2001, 401: 2002, 403: 2003, 404: 2004,
    405: 2005, 408: 2006, 413: 2007, 422: 2008,
    429: 2009, 500: 2010, 502: 2011, 503: 2012, 504: 2013,
  }
  return map[statusCode] || 2010
}

/**
 * 快应用 @system.fetch 原生错误码 → 前端错误码
 */
export function fetchErrorToCode(fetchCode) {
  const map = {
    200: null, 201: 1004, 202: 1002, 203: 1003, 204: 1005, 300: 1001,
  }
  return map[fetchCode] || 1099
}

/**
 * 快速判断是否为网络层错误（1xxx）
 */
export function isNetworkError(code) {
  return code >= 1000 && code < 2000
}

/**
 * 快速判断是否为存储层错误（4xxx）
 */
export function isStorageError(code) {
  return code >= 4000 && code < 5000
}

/**
 * 打印错误码表（调试用）
 * 调用方式：console.table(getErrorCodeTable())
 */
export function getErrorCodeTable() {
  return Object.entries(ALL_ERRORS).map(([code, info]) => ({
    错误码: Number(code),
    用户提示: info.message,
    详细说明: info.detail,
    严重度: info.level,
  }))
}

export {
  NETWORK_ERRORS, HTTP_ERRORS, BUSINESS_ERRORS,
  STORAGE_ERRORS, VALIDATION_ERRORS, DATA_ERRORS, ALL_ERRORS,
}
export default ALL_ERRORS
