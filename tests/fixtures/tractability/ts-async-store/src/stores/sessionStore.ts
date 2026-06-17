import { create } from 'zustand'

interface SessionState {
  userId: string | null
  token: string | null
}

export const useSessionStore = create<SessionState>((set) => ({
  userId: null,
  token: null,

  async login(credentials: { email: string; password: string }) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    })
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('session')
        set({ userId: null, token: null })
        return
      }
      throw new Error('login failed')
    }
    const data = await res.json()
    localStorage.setItem('session', JSON.stringify(data))
    set({ userId: data.userId, token: data.token })
  },

  logout() {
    localStorage.removeItem('session')
    set({ userId: null, token: null })
  },
}))
