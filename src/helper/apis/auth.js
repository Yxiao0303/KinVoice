/**
 * 用户认证 API
 */
import $ajax from '../ajax'
import config from './config'

const baseUrl = config.baseUrl

export default {
  /**
   * 注册新用户
   * @param {string} username - 用户名
   * @param {string} password - 密码
   * @param {string} nickname - 昵称
   * @returns {Promise<{user_id, nickname, message}>}
   */
  register(username, password, nickname) {
    return $ajax.post(`${baseUrl}/auth/register`, {
      username,
      password,
      nickname,
    })
  },

  /**
   * 用户登录
   * @param {string} username - 用户名
   * @param {string} password - 密码
   * @returns {Promise<{user_id, nickname, message}>}
   */
  login(username, password) {
    return $ajax.post(`${baseUrl}/auth/login`, {
      username,
      password,
    })
  },
}
