/**
 * 用户档案 API（每个用户只有一份自己的档案）
 *
 * 所有接口自动通过 X-User-Id Header 识别当前用户，
 * 用户只能操作自己的档案。
 */
import $ajax from '../ajax'
import config from './config'

const baseUrl = config.baseUrl

export default {
  /**
   * 获取当前用户的档案
   * @returns {Promise<{id, user_id, name, relation, birth_date, avatar_url, content_md, created_at, updated_at}>}
   *          不存在时 id=0
   */
  mine() {
    return $ajax.get(`${baseUrl}/profiles/mine`)
  },

  /**
   * 创建当前用户的档案
   * @param {Object} data - { name?, relation?, birth_date?, avatar_url?, content_md? }
   * @returns {Promise<{id, user_id, name, relation, ...}>}
   */
  create(data) {
    return $ajax.post(`${baseUrl}/profiles`, data)
  },

  /**
   * 更新当前用户的档案
   * @param {number} profileId
   * @param {Object} data - 要更新的字段（全可选）
   * @returns {Promise<{id, name, relation, ...}>}
   */
  update(profileId, data) {
    return $ajax.put(`${baseUrl}/profiles/${profileId}`, data)
  },

  /**
   * 删除当前用户的档案
   * @param {number} profileId
   * @returns {Promise}
   */
  remove(profileId) {
    return $ajax.delete(`${baseUrl}/profiles/${profileId}`)
  },
}
