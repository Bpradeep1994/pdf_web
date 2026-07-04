import { create } from "zustand";
import { persist } from "zustand/middleware";
import Cookies from "js-cookie";
import { authApi } from "./api";

export interface User {
  id:            string;
  email:         string;
  full_name:     string | null;
  avatar_url:    string | null;
  role:          "free" | "pro" | "business" | "enterprise" | "admin";
  admin_level?:  "user" | "moderator" | "admin" | "superadmin";
  status?:       "active" | "suspended" | "banned";
  auth_provider: string;
  is_verified:   boolean;
  mfa_enabled:   boolean;
  created_at:    string;
}

/** Whether a user can access the admin panel (Moderator and up, or a legacy plan-admin). */
export const isStaff = (u: User | null): boolean =>
  !!u && (["moderator", "admin", "superadmin"].includes(u.admin_level ?? "") || u.role === "admin");

interface AuthState {
  user:        User | null;
  isLoading:   boolean;
  login:       (email: string, password: string) => Promise<void>;
  register:    (email: string, password: string, full_name: string) => Promise<void>;
  logout:      () => Promise<void>;
  fetchMe:     () => Promise<void>;
  setUser:     (user: User | null) => void;
}

function saveTokens(access_token: string, refresh_token: string) {
  Cookies.set("access_token",  access_token,  { expires: 1 / 48, secure: true, sameSite: "lax" });
  Cookies.set("refresh_token", refresh_token, { expires: 7,       secure: true, sameSite: "lax" });
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user:      null,
      isLoading: false,

      login: async (email, password) => {
        set({ isLoading: true });
        try {
          const { data } = await authApi.login({ email, password });
          saveTokens(data.access_token, data.refresh_token);
          await get().fetchMe();
        } finally {
          set({ isLoading: false });
        }
      },

      register: async (email, password, full_name) => {
        set({ isLoading: true });
        try {
          const { data } = await authApi.register({ email, password, full_name });
          saveTokens(data.access_token, data.refresh_token);
          await get().fetchMe();
        } finally {
          set({ isLoading: false });
        }
      },

      logout: async () => {
        const refreshToken = Cookies.get("refresh_token");
        if (refreshToken) {
          try { await authApi.logout(refreshToken); } catch {}
        }
        Cookies.remove("access_token");
        Cookies.remove("refresh_token");
        set({ user: null });
      },

      fetchMe: async () => {
        try {
          const { data } = await authApi.me();
          set({ user: data });
        } catch {
          set({ user: null });
        }
      },

      setUser: (user) => set({ user }),
    }),
    {
      name: "pdf-editor-auth",
      partialize: (state) => ({ user: state.user }),
    }
  )
);

export function isAuthenticated(): boolean {
  return !!Cookies.get("access_token");
}
