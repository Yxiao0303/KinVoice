/**
 * 底部导航栏 Tabbar — 数据配置
 *
 * 架构说明：
 *   重构后所有 Tab 合并到 pages/Main 单页容器中，通过切换
 *   activeTab 状态来控制 section 显隐（show 属性），不再使用
 *   router.replace 跳转，彻底消除页面重新加载问题。
 *
 *   四个旧页面（pages/Companion, BreakIce, Memory, Profile）
 *   保留作为兼容路由，如果外部直接访问会自动 redirect 到 Main。
 *
 * 用法：
 *   <!-- Main/index.ux 中直接使用 TABS -->
 *   <script>
 *     import { TABS } from '../../helper/tabbar'
 *     export default {
 *       private: { tabs: TABS, activeTab: 'companion' },
 *       onTabChange(key) {
 *         if (key === this.activeTab) return
 *         this.activeTab = key
 *       }
 *     }
 *   </script>
 */

/** 4 个 tab 的配置（顺序即展示顺序） */
export const TABS = [
  { key: 'companion', icon: '🏠', label: '陪伴' },
  { key: 'breakIce',  icon: '💬', label: '聊天' },
  { key: 'memory',    icon: '📚', label: '传承' },
  { key: 'profile',   icon: '👤', label: '我的' },
]

/**
 * 【已废弃】旧架构中的页面跳转式 Tab 切换。
 * 新架构中 Main 页面直接通过状态切换 section，不再需要此函数。
 * 保留仅为向后兼容（旧页面如被外部链接直接打开时可调用）。
 *
 * @deprecated 请使用 Main 页面 onTabChange 替代
 */
export function onTabChange() {
  // 不再执行 router.replace，Tab 切换由 Main 页面单页管理
}
