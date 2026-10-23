/**
 * 全局错误事件总线
 * 
 * 使用方式：
 *   global.$errorBus.emit({ code: 1001, message: 'xxx', detail: 'xxx', level: 'error' })
 * 
 * 组件中监听：
 *   this._onError = global.$errorBus.on((err) => { ... })
 *   onDestroy() { global.$errorBus.off(this._onError) }
 */
const listeners = []

export default {
  /** 订阅错误事件，返回取消函数 */
  on(fn) {
    if (typeof fn !== 'function') return null
    listeners.push(fn)
    return fn
  },

  /** 取消订阅 */
  off(fn) {
    const idx = listeners.indexOf(fn)
    if (idx > -1) listeners.splice(idx, 1)
  },

  /** 发布错误事件 */
  emit(err) {
    const payload = {
      code: err && err.code ? err.code : 1099,
      message: err && err.message ? err.message : '未知错误',
      detail: err && err.detail ? err.detail : '',
      level: err && err.level ? err.level : 'error',
      raw: err && err.raw ? err.raw : null,
      timestamp: Date.now(),
    }
    listeners.forEach(fn => {
      try { fn(payload) } catch (e) { /* 防止订阅者异常影响其他 */ }
    })
  },
}
