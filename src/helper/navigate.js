import router from '@system.router'

let __routerLock = false
let __lockTimer = null
const LOCK_DELAY = 300
// 安全兜底：即使出现异常，最多 2 秒后也自动释放锁
const LOCK_MAX_DURATION = 2000

/**
 * 获取/释放路由锁，防止快速连续点击导致框架导航异常。
 * 每次调用时重新计时，旧定时器会被清除防止累积。
 */
function acquireLock(actionFn) {
  if (__routerLock) return
  __routerLock = true

  // 清除上一次的释放定时器（防止定时器累积）
  if (__lockTimer) {
    clearTimeout(__lockTimer)
    __lockTimer = null
  }

  actionFn()

  // LOCK_DELAY 后释放锁
  __lockTimer = setTimeout(() => {
    __routerLock = false
    __lockTimer = null
  }, LOCK_DELAY)

  // 安全兜底：最多 LOCK_MAX_DURATION 后强制释放锁
  setTimeout(() => {
    if (__routerLock) {
      __routerLock = false
      __lockTimer = null
    }
  }, LOCK_MAX_DURATION)
}

/**
 * 安全的路由 replace，防止快速连续点击导致框架导航异常
 */
export function safeReplace(uri) {
  acquireLock(() => router.replace({ uri: uri }))
}

/**
 * 安全的路由 push，防止快速连续点击导致框架导航异常
 */
export function safePush(uri) {
  acquireLock(() => router.push({ uri: uri }))
}

/**
 * 安全的路由 back，防止快速连续点击返回导致框架导航异常
 */
export function safeBack() {
  acquireLock(() => router.back())
}
