/**
 * 封装了网络请求方法，集成错误码体系
 * - 自动解析 HTTP 状态码 → 业务错误码
 * - 统一错误格式：{ code, message, detail, level, raw }
 * - 支持 GET / POST / PUT / DELETE
 */
import $fetch from '@system.fetch'
import $utils from './utils'
import userIdentity from './userIdentity'
import { getErrorInfo, mapDetailToCode, httpStatusToCode, fetchErrorToCode } from './errorCodes'

const TIMEOUT = 20000

if (!Promise.prototype.finally) {
  Promise.prototype.finally = function(callback) {
    const P = this.constructor
    return this.then(
      value => P.resolve(callback()).then(() => value),
      reason =>
        P.resolve(callback()).then(() => {
          throw reason
        })
    )
  }
}

/**
 * 构造统一错误对象
 * @param {number} code     - 错误码
 * @param {*}      raw      - 原始数据（响应体 / Error 对象）
 * @param {string} extraMsg - 额外补充消息（后端 detail）
 * @returns {{ code: number, message: string, detail: string, level: string, raw: * }}
 */
function buildError(code, raw, extraMsg) {
  const info = getErrorInfo(code)
  return {
    code: code,
    message: extraMsg || info.message,
    detail: info.detail,
    level: info.level,
    raw: raw,
    isError: true,                  // 快速判断标记
  }
}

/**
 * 解析后端 JSON 响应，提取可能的错误信息
 * @param {object} responseData - 已 parse 的 JSON 对象
 * @param {number} statusCode   - HTTP 状态码
 * @returns {{ code: number, message: string, detail: string, level: string }|null}
 *         返回 null 表示成功（2xx），否则返回错误对象
 */
function parseBackendError(responseData, statusCode) {
  // 2xx 视为成功
  if (statusCode >= 200 && statusCode < 300) {
    return null
  }

  // 尝试从后端 detail 字段映射业务错误码
  const backendDetail = (responseData && responseData.detail) || ''
  const bizCode = mapDetailToCode(backendDetail)

  if (bizCode) {
    return buildError(bizCode, responseData, backendDetail)
  }

  // 兜底：HTTP 状态码 → 通用错误码
  return buildError(httpStatusToCode(statusCode), responseData, backendDetail)
}

/**
 * 调用快应用 fetch 接口做网络请求
 * 成功 → resolve(后端 JSON)
 * 失败 → reject({ code, message, detail, level, raw, isError })
 */
function fetchPromise(params) {
  return new Promise((resolve, reject) => {
    // 构建请求配置
    const fetchOptions = {
      url: params.url,
      method: params.method,
      header: params.header || {},
    }

    // 同步注入 X-User-Id Header（getUserId() 始终有值：eagerUuid 或 storage 恢复的 UUID）
    // 注意：首次启动时 eagerUuid 会立即被 initUserId() 持久化，二者等价；
    // 重新启动时 eagerUuid 是随机值，但 storage 恢复通常在首次 API 调用前就已完成。
    // 如需确保使用准确的 UUID，调用方应 await userIdentity.ready()
    const uid = userIdentity.getUserId()
    if (uid && !fetchOptions.header['X-User-Id']) {
      fetchOptions.header['X-User-Id'] = uid
    }

    // fire-and-forget：确保身份初始化运行（不阻塞当前请求）
    userIdentity.ready().catch(() => {})

    // POST/PUT 请求：手动 JSON.stringify 并设置 Content-Type
    // 快应用 @system.fetch 对 data 的自动处理行为不一致，
    // 有的版本会转成 form-urlencoded 导致 FastAPI 收到非 JSON body → 422
    if (params.data !== undefined && params.data !== null) {
      if (typeof params.data === 'string') {
        fetchOptions.data = params.data
      } else {
        fetchOptions.data = JSON.stringify(params.data)
        fetchOptions.header['Content-Type'] = 'application/json'
      }
    }

    $fetch
      .fetch(fetchOptions)
      .then(response => {
        // 快应用 @system.fetch 可能已自动解析 JSON，body 可能是对象或字符串
        let body = response.data

        if (typeof body === 'string') {
          try {
            body = JSON.parse(body)
          } catch (e) {
            // JSON 解析失败 → 视为成功（可能是二进制数据，如 TTS）
            console.log('[ajax] 响应非 JSON，可能是二进制数据')
            resolve(body)
            return
          }
        }

        // HTTP 状态码：优先用代理包装中的真实状态码，否则用 fetch 层 code
        let httpStatus = Number(response.code || 0)

        // 处理 Quick App Studio 代理包装：
        // /api/proxy/xxx 会返回 { code: 200, headers: {}, data: "原响应JSON字符串" }
        if (body && typeof body === 'object' &&
            typeof body.data === 'string' &&
            body.headers && typeof body.headers === 'object') {
          // 用代理包装中的真实 HTTP 状态码
          httpStatus = Number(body.code || httpStatus)
          try {
            console.log('[ajax] 检测到代理包装，解包 data 字段')
            body = JSON.parse(body.data)
            console.log('[ajax] 解包后:', JSON.stringify(body).substring(0, 120))
          } catch (e) {
            console.log('[ajax] 代理响应 data 字段非 JSON，保留外层:', e)
          }
        } else {
          console.log('[ajax] 非代理包装响应，直接返回')
        }

        // 检查后端是否返回了错误
        const err = parseBackendError(body, httpStatus)
        if (err) {
          reject(err)
        } else {
          resolve(body)
        }
      })
      .catch((error, code) => {
        // 快应用 fetch 层错误（网络层）
        const errCode = fetchErrorToCode(code)
        const err = buildError(errCode, error)
        console.log(`🐛 [${errCode}] ${err.message} | code=${code}`)
        reject(err)
      })
      .finally(() => {
        console.log(`✔️ ${params.method} @${params.url} 完成`)
      })
  })
}

/**
 * 处理网络请求，带超时保护
 *
 * 【重要】超时定时器在 fetch 完成后会被清除，防止定时器泄漏。
 * 在快应用资源受限环境中，未清理的定时器累积会导致定时器池耗尽，
 * 进而引发「点击无反应」的假死现象。
 *
 * @param {object} params  - { url, method, data }
 * @param {number} timeout - 超时时间 ms
 * @returns {Promise}
 */
function requestHandle(params, timeout = TIMEOUT) {
  try {
    let timerId = null

    const timeoutPromise = new Promise((resolve, reject) => {
      timerId = setTimeout(() => {
        timerId = null
        reject(buildError(1001, null, '请求超时（' + (timeout / 1000) + 's）'))
      }, timeout)
    })

    return Promise.race([
      fetchPromise(params),
      timeoutPromise,
    ]).finally(() => {
      // 无论 fetch 先完成还是超时先触发，都要清理定时器
      if (timerId) {
        clearTimeout(timerId)
        timerId = null
      }
    })
  } catch (error) {
    console.log('[ajax] requestHandle 异常:', error)
    return Promise.reject(buildError(1099, error))
  }
}

/**
 * 原始请求（支持自定义 responseType，用于下载二进制数据如 TTS 音频）
 * @param {object}  params       - { url, method, data, header, responseType }
 * @param {string}  responseType - 默认 'text'，可传 'arraybuffer' 等
 * @returns {Promise}
 */
function rawRequest({ url, method, data, header, responseType = 'text' }) {
  return new Promise((resolve, reject) => {
    const fetchOptions = { url, method, header: header || {} }
    const uid = userIdentity.getUserId()
    if (uid) {
      fetchOptions.header['X-User-Id'] = uid
    }
    if (data !== undefined && data !== null) {
      fetchOptions.data = typeof data === 'string' ? data : JSON.stringify(data)
      fetchOptions.header['Content-Type'] = 'application/json'
    }
    fetchOptions.responseType = responseType

    let timerId = null
    const timeoutPromise = new Promise((_, rej) => {
      timerId = setTimeout(() => {
        timerId = null
        rej(buildError(1001, null, '请求超时'))
      }, TIMEOUT)
    })

    const fetchTask = $fetch.fetch(fetchOptions)
      .then(response => {
        resolve(response.data)
      })
      .catch((err, code) => {
        reject({ error: err, code })
      })

    Promise.race([fetchTask, timeoutPromise])
      .catch(err => {
        if (err && err.isError) reject(err)
        else reject(buildError(1001, null))
      })
      .finally(() => {
        if (timerId) clearTimeout(timerId)
      })
  })
}

// ── 导出的 HTTP 方法 ──

export default {
  /** POST 请求 */
  post: function(url, params) {
    return requestHandle({
      method: 'post',
      url: url,
      data: params,
    })
  },

  /** GET 请求 */
  get: function(url, params) {
    return requestHandle({
      method: 'get',
      url: $utils.queryString(url, params),
    })
  },

  /** PUT 请求 */
  put: function(url, params) {
    return requestHandle({
      method: 'put',
      url: url,
      data: params,
    })
  },

  /** DELETE 请求 */
  delete: function(url, params) {
    return requestHandle({
      method: 'delete',
      url: url,
      data: params,
    })
  },

  /** 原始请求（支持自定义 responseType，如 TTS 二进制下载） */
  rawRequest,
}
