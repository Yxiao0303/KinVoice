/**
 * AI 档案编写 API
 *
 * user_id 由 ajax.js 自动通过 X-User-Id Header 注入，无需手动传递。
 */
import $ajax from '../ajax'
import config from './config'

const baseUrl = config.baseUrl

export default {
  /**
   * 从今日对话自动更新动态档案（Companion onHide 时调用）
   * @returns {Promise<{ok, profile_type, path, content_preview, messages_used}>}
   */
  updateDynamic() {
    return $ajax.post(`${baseUrl}/profile/ai/update-dynamic`, {})
  },

  /**
   * 更新固定档案（Profile 页面手动触发）
   * @returns {Promise<{ok, profile_type, path, content_preview, messages_used}>}
   */
  updateStable() {
    return $ajax.post(`${baseUrl}/profile/ai/update-stable`, {})
  },

  /**
   * 读取用户档案
   * @returns {Promise<{user_id, stable, dynamic}>}
   */
  read() {
    return $ajax.get(`${baseUrl}/profile/ai/read`)
  },
}