/**
 * 工具方法 —— 系统 API 封装
 * 通过 global.$utils 全局访问
 */
const prompt = require('@system.prompt')

/**
 * 拼接 url 和参数
 */
function queryString(url, query) {
  if (!query) return url
  let str = []
  for (let key in query) {
    if (query[key] !== undefined && query[key] !== null) {
      str.push(key + '=' + query[key])
    }
  }
  let paramStr = str.join('&')
  return paramStr ? `${url}?${paramStr}` : url
}

/**
 * 显示 toast 提示（短时间显示）
 */
function showToast(message = '', duration = 0) {
  if (!message) return
  prompt.showToast({
    message: message,
    duration: duration,
  })
}

// ===================================================================
//  错误处理工具（基于 errorCodes.js 体系）
// ===================================================================

/**
 * 处理 API 错误，自动显示对应 toast
 * @param {object} err     - ajax.js reject 的统一错误对象 { code, message, detail, level, isError }
 * @param {string} fallbackMsg - 如果 err 不是标准格式时的兜底消息
 * @returns {string} 显示给用户的消息
 */
export function handleApiError(err, fallbackMsg) {
  // 标准错误对象
  if (err && err.isError && err.code) {
    const duration = err.level === 'error' || err.level === 'fatal' ? 2000 : 0
    showToast(err.message, duration)
    return err.message
  }

  // 字符串错误
  if (typeof err === 'string') {
    showToast(err)
    return err
  }

  // Error 对象
  if (err instanceof Error) {
    const msg = fallbackMsg || err.message || '操作失败，请重试'
    showToast(msg)
    return msg
  }

  // 兜底
  const msg = fallbackMsg || '操作失败，请重试'
  showToast(msg)
  return msg
}

/**
 * 静默处理错误（只 log，不弹 toast）
 * 适用于离线降级场景
 * @param {object} err
 * @param {string} context - 上下文描述
 */
export function silentError(err, context) {
  if (err && err.code) {
    console.log(`[${context}] [${err.code}] ${err.message} | ${err.detail}`)
  } else {
    console.log(`[${context}] 错误:`, err)
  }
}

export default {
  queryString,
  showToast,
  handleApiError,
  silentError,
}
