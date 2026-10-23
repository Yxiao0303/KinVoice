/**
 * NVC（非暴力沟通）转换 API
 *
 * 将情绪化的言辞转化为揭示背后真实意图的温和表达，
 * 帮助家庭成员更好地沟通。
 */
import $ajax from '../ajax'
import config from './config'

const baseUrl = config.baseUrl

export default {
  /**
   * NVC 文本转换
   * @param {string} originalText - 原始输入文本
   * @returns {Promise<{original_text, converted_text, insight}>}
   */
  convert(originalText) {
    return $ajax.post(`${baseUrl}/nvc/convert`, {
      original_text: originalText,
    })
  },
}
