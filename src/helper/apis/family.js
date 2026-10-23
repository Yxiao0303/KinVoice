/**
 * 家庭组 API
 *
 * 用户身份通过 X-User-Id Header 传递（由 ajax.js 自动注入）。
 */
import $ajax from '../ajax'
import config from './config'

const baseUrl = config.baseUrl

export default {
  /**
   * 注册用户（首次使用，设置昵称）
   * @param {string} nickname - 用户昵称
   * @returns {Promise<{user_id, nickname}>}
   */
  register(nickname) {
    return $ajax.post(`${baseUrl}/family/register-with-id`, {
      nickname,
    })
  },

  /**
   * 创建家庭组
   * @param {string} nickname - 创建者昵称
   * @returns {Promise<{family_id, password, user_id}>}
   */
  createGroup(nickname) {
    return $ajax.post(`${baseUrl}/family/create`, {
      nickname,
    })
  },

  /**
   * 加入家庭组
   * @param {string} familyId - 8位家庭组ID
   * @param {string} password - 6位数字密码
   * @param {string} nickname - 加入者昵称
   * @returns {Promise<{ok}>}
   */
  joinGroup(familyId, password, nickname) {
    return $ajax.post(`${baseUrl}/family/join`, {
      family_id: familyId,
      password,
      nickname,
    })
  },

  /**
   * 退出家庭组
   * @returns {Promise<{ok}>}
   */
  leaveGroup() {
    return $ajax.post(`${baseUrl}/family/leave`, {})
  },

  /**
   * 查询我的家庭组
   * @returns {Promise<{family_id, password, members: [{user_id, nickname, joined_at}]}>}
   */
  getMyGroup() {
    return $ajax.get(`${baseUrl}/family/my-group`)
  },
}
