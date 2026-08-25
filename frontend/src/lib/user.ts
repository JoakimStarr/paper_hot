// 本地身份（P1-10）：不引入账号体系，localStorage 生成 userId，
// 随所有请求头 x-user-id 传给后端做数据隔离。
const USER_ID_KEY = 'pp_user_id';

export function getUserId(): string {
  if (typeof window === 'undefined') return 'local';
  try {
    let id = localStorage.getItem(USER_ID_KEY);
    if (!id) {
      id = `u_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem(USER_ID_KEY, id);
    }
    return id;
  } catch {
    return 'local';
  }
}
