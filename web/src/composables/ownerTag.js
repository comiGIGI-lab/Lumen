/**
 * ownerTag —— 当前登录账号的分档标签（纯函数，零依赖）。
 *
 * 个性化小状态（宠物、自习设置）都按账号分档存 localStorage：
 * `zjxt.<xxx>.<u:用户名 | anon>`。同一浏览器多账号不互相污染；
 * 未登录统一落在 anon 档。
 *
 * token 是 base64url("username|role|expire_ts".signature)，同步可解，
 * 不用等 /me 回来；解不动一律按 anon 处理（宁可靠 anon，不可抛异常）。
 */
export function ownerTag() {
  try {
    const raw = localStorage.getItem('zjxt.auth.token') || ''
    const b64 = raw.split('.')[0].replace(/-/g, '+').replace(/_/g, '/')
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
    const name = new TextDecoder().decode(bytes).split('|')[0].trim()
    return name ? 'u:' + name : 'anon'
  } catch (_) {
    return 'anon'
  }
}

/** 按账号分档的 localStorage key。 */
export function keyedStorage(baseKey) {
  return `${baseKey}.${ownerTag()}`
}
