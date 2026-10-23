/**
 * AI 陪伴对话 API —— xia 模式（会话持久化 + 历史管理）
 */
import $ajax from '../ajax'
import config from './config'

const baseUrl = config.baseUrl

export default {
  /**
   * 发送消息，获取 AI 回复
   * xia 模式：后端自动管理对话历史
   *
   * @param {Object} params
   * @param {string}  params.message         - 用户消息（必填）
   * @param {number?} params.conversation_id - 会话 ID，首次传 null，后续传上次返回的 id
   * @param {string?} params.family_id       - 家庭组 ID，用于检索家庭卡片和对话历史
   * @returns {Promise<{reply: string, conversation_id: number, message_id: number}>}
   */
  sendMessage(params) {
    return $ajax.post(`${baseUrl}/chat`, params)
  },

  /**
   * 获取所有会话列表（按创建时间倒序）
   * @returns {Promise<{conversations: Array<{id: number, title: string|null, created_at: string}>}>}
   */
  listConversations() {
    return $ajax.get(`${baseUrl}/chat/conversations`)
  },

  /**
   * 拉取某个会话的完整消息历史
   * @param {number} conversationId
   * @returns {Promise<{conversation_id: number, messages: Array<{id: number, role: string, content: string, created_at: string}>}>}
   */
  getHistory(conversationId) {
    return $ajax.get(`${baseUrl}/chat/history`, { conversation_id: conversationId })
  },

  /**
   * 删除会话及其所有消息（硬删除）
   * @param {number} conversationId
   * @returns {Promise<{ok: boolean, deleted_id: number}>}
   */
  deleteConversation(conversationId) {
    return $ajax.delete(`${baseUrl}/chat/conversations/${conversationId}`)
  },
}
