import $ajax from '../ajax'
import config from './config'

const baseUrl = config.baseUrl

export default {
  // ═══════════════════════════════════════════════════
  //  文件夹
  // ═══════════════════════════════════════════════════

  /** 获取文件夹列表（含笔记计数） */
  listFolders() {
    return $ajax.get(`${baseUrl}/folders`)
  },

  /** 创建文件夹 */
  createFolder(name) {
    return $ajax.post(`${baseUrl}/folders`, { name })
  },

  // ═══════════════════════════════════════════════════
  //  笔记
  // ═══════════════════════════════════════════════════

  /**
   * 获取笔记列表
   * @param {Object} [params] - { folder_id?, limit?, offset? }
   */
  list(params) {
    return $ajax.get(`${baseUrl}/cards`, {
      folder_id: params && params.folder_id,
      limit: params && params.limit ? params.limit : 200,
      offset: params && params.offset ? params.offset : 0,
    })
  },

  /**
   * 创建笔记
   * @param {Object} data - { title, content, author, folder_id }
   */
  create(data) {
    return $ajax.post(`${baseUrl}/cards`, data)
  },

  /**
   * 更新笔记
   * @param {number} cardId
   * @param {Object} data
   */
  update(cardId, data) {
    return $ajax.put(`${baseUrl}/cards/${cardId}`, data)
  },

  /**
   * 删除笔记
   * @param {number} cardId
   */
  remove(cardId) {
    return $ajax.delete(`${baseUrl}/cards/${cardId}`)
  },
}
