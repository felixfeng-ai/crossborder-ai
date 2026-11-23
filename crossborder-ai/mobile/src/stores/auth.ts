import { create } from "zustand";

import {
  deleteSecureItem,
  getSecureItem,
  setSecureItem,
} from "@/security/storage";
import {
  type AuthTokens,
  logoutAllSessions,
  logoutSession,
  refreshAuthSession,
} from "@/api/client";

const ACCESS_TOKEN_KEY = "veyaship.mobile.access_token";
const REFRESH_TOKEN_KEY = "veyaship.mobile.refresh_token";

type AuthState = {
  token: string | null;
  refreshToken: string | null;
  hydrated: boolean;
  hydrate: () => Promise<void>;
  setSession: (tokens: AuthTokens) => Promise<void>;
  refreshSession: () => Promise<string | null>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
};

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  refreshToken: null,
  hydrated: false,
  hydrate: async () => {
    try {
      const [token, refreshToken] = await Promise.all([
        getSecureItem(ACCESS_TOKEN_KEY),
        getSecureItem(REFRESH_TOKEN_KEY),
      ]);
      set({ token, refreshToken, hydrated: true });
    } catch {
      set({ token: null, refreshToken: null, hydrated: true });
    }
  },
  setSession: async (tokens) => {
    const writes: Promise<unknown>[] = [
      setSecureItem(ACCESS_TOKEN_KEY, tokens.access_token),
    ];
    if (tokens.refresh_token) {
      writes.push(setSecureItem(REFRESH_TOKEN_KEY, tokens.refresh_token));
    } else {
      // 旧版登录接口只返回 access token，清理历史 refresh token 防止误续期。
      writes.push(deleteSecureItem(REFRESH_TOKEN_KEY));
    }
    await Promise.all(writes);
    set({
      token: tokens.access_token,
      refreshToken: tokens.refresh_token ?? null,
      hydrated: true,
    });
  },
  refreshSession: async () => {
    const currentToken = useAuthStore.getState().token;
    const rawRefresh =
      useAuthStore.getState().refreshToken
      || (await getSecureItem(REFRESH_TOKEN_KEY));
    if (!rawRefresh) return null;
    try {
      const tokens = await refreshAuthSession(rawRefresh);
      await useAuthStore.getState().setSession(tokens);
      return tokens.access_token;
    } catch {
      if (useAuthStore.getState().token === currentToken) {
        await useAuthStore.getState().logout();
      }
      return null;
    }
  },
  logout: async () => {
    const token = useAuthStore.getState().token;
    if (token) {
      await logoutSession(token).catch(() => undefined);
    }
    await Promise.all([
      deleteSecureItem(ACCESS_TOKEN_KEY),
      deleteSecureItem(REFRESH_TOKEN_KEY),
    ]);
    set({ token: null, refreshToken: null, hydrated: true });
  },
  logoutAll: async () => {
    const token = useAuthStore.getState().token;
    if (token) {
      await logoutAllSessions(token).catch(() => undefined);
    }
    await Promise.all([
      deleteSecureItem(ACCESS_TOKEN_KEY),
      deleteSecureItem(REFRESH_TOKEN_KEY),
    ]);
    set({ token: null, refreshToken: null, hydrated: true });
  },
}));
