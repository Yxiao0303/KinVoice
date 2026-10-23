/**
 * 用户身份管理 —— 设备 UUID + 昵称
 *
 * 设计：
 * - 每个设备生成唯一 UUID 存 localStorage，作为 user_id
 * - 昵称由用户首次输入，后端注册后缓存到 localStorage
 * - 所有 API 请求通过 Header X-User-Id 传递用户身份
 *
 * 使用方式：
 *   import userIdentity from '../../helper/userIdentity'
 *   const userId = userIdentity.getUserId()
 *   const nickname = userIdentity.getNickname()
 */

import storage from '@system.storage'

const KEYS = {
  USER_ID: 'kinvoice_user_id',
  NICKNAME: 'kinvoice_nickname',
  IS_LOGGED_IN: 'kinvoice_logged_in',
}

/**
 * 生成 UUID v4（简化版，快应用兼容）
 */
function generateUUID() {
  const hex = '0123456789abcdef'
  let uuid = ''
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) {
      uuid += '-'
    } else if (i === 14) {
      uuid += '4'
    } else if (i === 19) {
      uuid += hex[(Math.random() * 4) | 8]
    } else {
      uuid += hex[(Math.random() * 16) | 0]
    }
  }
  return uuid
}

/** 模块加载时立即生成 UUID，确保 getUserId() 永远不返回 null */
const eagerUuid = generateUUID()

const userIdentity = {
  /** 预填充缓存，防止 init() 完成前 getUserId() 返回 null */
  _cachedUserId: eagerUuid,
  _cachedNickname: '',
  _cachedIsLoggedIn: false,  // 只有通过 authAPI 登录/注册成功后才为 true
  _initPromise: null,
  _initResolvers: [],
  _userIdPromise: null,    // 防止 initUserId() 重复调用
  _nicknamePromise: null,  // 防止 initNickname() 重复调用
  _loginPromise: null,     // 防止 initLogin() 重复调用

  /**
   * 等待身份初始化完成（UUID 从 storage 恢复）。
   * 可在任何需要正确 user_id 的地方 await userIdentity.ready()。
   * 多次调用安全，已完成时立即 resolve。
   * @returns {Promise<void>}
   */
  ready() {
    if (this._initResolvers === null) {
      // 已初始化完成
      return Promise.resolve()
    }
    return new Promise(resolve => {
      this._initResolvers.push(resolve)
    })
  },

  /**
   * 初始化：从 storage 恢复 user_id + nickname。
   * 由 app.ux onCreate() 调用（storage API 必须在此之后才能使用）。
   * 如果 storage 中有已存在的 UUID 则覆盖缓存，否则持久化当前 UUID。
   * @returns {Promise<void>}
   */
  init() {
    if (this._initPromise) return this._initPromise
    this._initPromise = this.initUserId()
      .then(() => this.initNickname())
      .then(() => this.initLogin())
      .then(() => {
        // 通知所有等待者
        const resolvers = this._initResolvers
        this._initResolvers = null  // null 表示已完成
        resolvers.forEach(r => r())
      })
    return this._initPromise
  },

  /**
   * 从本地存储恢复 user_id（如果不存在则持久化 eagerUuid）。
   * 带缓存守卫：多次调用返回同一个 Promise，避免重复 storage 操作。
   * @returns {Promise<string>} user_id
   */
  initUserId() {
    if (this._userIdPromise) return this._userIdPromise
    this._userIdPromise = new Promise((resolve) => {
      storage.get({
        key: KEYS.USER_ID,
        success: (data) => {
          // storage 中已有 UUID → 覆盖模块加载时生成的临时 UUID
          if (data && data.length > 0) {
            this._cachedUserId = data
          } else {
            // 空值 → 持久化 eagerUuid
            this._cachedUserId = eagerUuid
            storage.set({ key: KEYS.USER_ID, value: eagerUuid })
          }
          resolve(this._cachedUserId)
        },
        fail: () => {
          // 首次打开或 storage 不可用 → 持久化 eagerUuid
          this._cachedUserId = eagerUuid
          storage.set({
            key: KEYS.USER_ID,
            value: eagerUuid,
            success: () => resolve(eagerUuid),
            fail: () => resolve(eagerUuid),
          })
        },
      })
    })
    return this._userIdPromise
  },

  /**
   * 从本地存储读取 nickname 并缓存。
   * 带缓存守卫：多次调用返回同一个 Promise，避免重复 storage 操作。
   * @returns {Promise<string>}
   */
  initNickname() {
    if (this._nicknamePromise) return this._nicknamePromise
    this._nicknamePromise = new Promise((resolve) => {
      storage.get({
        key: KEYS.NICKNAME,
        success: (data) => {
          this._cachedNickname = data || ''
          resolve(this._cachedNickname)
        },
        fail: () => {
          this._cachedNickname = ''
          resolve('')
        },
      })
    })
    return this._nicknamePromise
  },

  /**
   * 从本地存储读取 login 标记并缓存。
   * 带缓存守卫：多次调用返回同一个 Promise。
   * @returns {Promise<boolean>}
   */
  initLogin() {
    if (this._loginPromise) return this._loginPromise
    this._loginPromise = new Promise((resolve) => {
      storage.get({
        key: KEYS.IS_LOGGED_IN,
        success: (data) => {
          this._cachedIsLoggedIn = data === '1' || data === 1 || data === true
          resolve(this._cachedIsLoggedIn)
        },
        fail: () => {
          this._cachedIsLoggedIn = false
          resolve(false)
        },
      })
    })
    return this._loginPromise
  },

  /** 获取登录状态（同步） */
  isLoggedIn() {
    return this._cachedIsLoggedIn
  },

  /** 标记已登录（通过 auth 接口成功后调用） */
  markLoggedIn() {
    this._cachedIsLoggedIn = true
    storage.set({ key: KEYS.IS_LOGGED_IN, value: '1' })
  },

  /** 标记已登出（退出登录时调用） */
  markLoggedOut() {
    this._cachedIsLoggedIn = false
    storage.set({ key: KEYS.IS_LOGGED_IN, value: '0' })
  },

  /** 获取当前 user_id（同步，模块加载后始终有值） */
  getUserId() {
    return this._cachedUserId || eagerUuid
  },

  /** 获取昵称（同步） */
  getNickname() {
    if (this._cachedNickname) return this._cachedNickname
    return ''
  },

  /** 设置 user_id（登录/注册后服务端返回的 UUID 覆盖设备 UUID） */
  setUserId(userId) {
    if (userId) {
      this._cachedUserId = userId
      storage.set({ key: KEYS.USER_ID, value: userId })
    }
  },

  /** 设置昵称（同时更新缓存 + 持久化到本地存储） */
  setNickname(nickname) {
    this._cachedNickname = nickname || ''
    storage.set({ key: KEYS.NICKNAME, value: this._cachedNickname })
  },

  /**
   * 检查是否已注册（有昵称即为已注册）
   * @returns {Promise<boolean>}
   */
  isRegistered() {
    return new Promise((resolve) => {
      storage.get({
        key: KEYS.NICKNAME,
        success: (data) => {
          resolve(!!data)
        },
        fail: () => resolve(false),
      })
    })
  },
}

// ── 注意：身份初始化由 app.ux onCreate() 触发 ──
// 不能在此处调用 userIdentity.init()，因为模块加载时 storage API 尚未就绪，
// 会抛出「请在 onCreate() 之后调用」的错误。

export default userIdentity
