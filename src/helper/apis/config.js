/**
 * API 配置
 * 地址由 scripts/genBackendUrl.js 从根目录 frontend.env.json 自动生成
 * 不要手动修改，改 frontend.env.json 后运行 node scripts/genBackendUrl.js
 */
import baseUrl from './.backend-url'

export default {
  baseUrl,
}
