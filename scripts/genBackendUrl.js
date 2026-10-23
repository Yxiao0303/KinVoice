/**
 * 生成后端地址配置文件
 *
 * 读取根目录 frontend.env.json → 写入 src/helper/apis/.backend-url.js
 * 在 hap server / hap build 之前运行此脚本
 *
 * 用法：node scripts/genBackendUrl.js
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const ENV_FILE = path.join(ROOT, 'frontend.env.json')
const TARGET_FILE = path.join(ROOT, 'src', 'helper', 'apis', '.backend-url.js')
const DEFAULT_PORT = 8000

function main() {
  let host = 'localhost'
  let port = DEFAULT_PORT

  // 1. 尝试读取 frontend.env.json
  if (fs.existsSync(ENV_FILE)) {
    try {
      const raw = fs.readFileSync(ENV_FILE, 'utf-8')
      const config = JSON.parse(raw)
      if (config.backend) {
        host = config.backend.host || host
        port = config.backend.port || port
      }
      console.log(`[genBackendUrl] 从 frontend.env.json 读取: ${host}:${port}`)
    } catch (e) {
      console.warn(`[genBackendUrl] frontend.env.json 解析失败: ${e.message}，使用默认值`)
    }
  } else {
    console.warn(`[genBackendUrl] frontend.env.json 不存在，使用默认值 localhost:${port}`)
    console.warn(`[genBackendUrl] 提示：复制 frontend.env.example.json 为 frontend.env.json 并修改`)
  }

  const baseUrl = `http://${host}:${port}`
  const content = `/**
 * 自动生成的后端地址 — 由 scripts/genBackendUrl.js 生成
 * 请勿手动修改此文件
 * 修改根目录 frontend.env.json 后重新运行 node scripts/genBackendUrl.js
 */
export default '${baseUrl}'
`

  // 确保目录存在
  const dir = path.dirname(TARGET_FILE)
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }

  fs.writeFileSync(TARGET_FILE, content, 'utf-8')
  console.log(`[genBackendUrl] 已生成: ${TARGET_FILE}`)
  console.log(`[genBackendUrl] 后端地址: ${baseUrl}`)
}

main()
