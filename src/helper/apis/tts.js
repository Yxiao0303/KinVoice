/**
 * TTS 语音合成 API
 */

import $ajax from '../ajax'
import config from './config'

const BASE = config.baseUrl + '/tts'

// 生成临时文件路径
function getTempPath(fileName) {
  return 'internal://cache/' + fileName
}

export default {
  /** 获取音色列表 */
  getVoices() {
    return $ajax.get(BASE + '/voices')
  },

  /**
   * 文本合成语音，并直接播放
   * @param {string} text  - 文本内容
   * @param {string} voice - 音色标识
   */
  async play(text, voice = 'yunye') {
    // 1. 获取音频二进制数据
    const arrayBuffer = await $ajax.rawRequest({
      url: BASE + '?text=' + encodeURIComponent(text) + '&voice=' + encodeURIComponent(voice),
      method: 'POST',
      responseType: 'arraybuffer'
    })
    // 2. 写入临时文件
    const file = require('@system.file')
    const tempPath = getTempPath('tts_' + Date.now() + '.wav')
    await new Promise((resolve, reject) => {
      file.writeArrayBuffer({
        uri: tempPath,
        buffer: arrayBuffer,
        success: resolve,
        fail: reject
      })
    })
    // 3. 播放
    const audio = require('@system.audio')
    audio.play({ src: tempPath })
    // 播放完成后可删除临时文件（可选）
  }
}