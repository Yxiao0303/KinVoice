import $ajax from '../ajax'
import config from './config'

const BASE = config.baseUrl + '/replica'

export default {
  /** 获取推荐录音文本 */
  getSampleTexts() {
    return $ajax.get(BASE + '/sample-texts')
  },

  /** 查询音色生成状态 */
  getStatus(vcn) {
    return $ajax.get(BASE + '/status', { vcn })
  },

  /** 删除音色 */
  deleteVoice(vcn) {
    return $ajax.delete(BASE + '/' + vcn)
  },

  /** 重命名音色 */
  rename(vcn, newName) {
    return $ajax.put(BASE + '/rename', { vcn, new_name: newName })
  },

  /** 上传录音创建音色（暂存，待完整实现） */
  create(audioUri, text) {
    // 由于快应用文件上传比较复杂，此处预留接口
    // 实际使用时需要读取文件内容并构建 multipart/form-data
    // 如果环境不支持，可提示用户升级或改用其他方式
    return Promise.reject(new Error('文件上传暂未实现'))
  }
}