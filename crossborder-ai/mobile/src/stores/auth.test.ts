import { beforeEach, describe, expect, it, vi } from "vitest";

const secure = vi.hoisted(() => ({
  getSecureItem: vi.fn(),
  setSecureItem: vi.fn(),
  deleteSecureItem: vi.fn(),
}));

const authApi = vi.hoisted(() => ({
  logoutAllSessions: vi.fn(),
  logoutSession: vi.fn(),
  refreshAuthSession: vi.fn(),
}));

vi.mock("@/security/storage", () => secure);
vi.mock("@/api/client", () => authApi);

// Mock 必须先注册，才能在模块初始化时替换安全存储和认证 API。
// eslint-disable-next-line import/first
import { useAuthStore } from "./auth";

const firstTokens = {
  access_token: "access-1",
  refresh_token: "refresh-1",
  token_type: "bearer",
  expires_in: 900,
  session_id: "session-1",
};

describe("mobile auth session store", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      token: null,
      refreshToken: null,
      hydrated: false,
    });
    secure.getSecureItem.mockResolvedValue(null);
    secure.setSecureItem.mockResolvedValue(undefined);
    secure.deleteSecureItem.mockResolvedValue(undefined);
    authApi.refreshAuthSession.mockResolvedValue({
      ...firstTokens,
      access_token: "access-2",
      refresh_token: "refresh-2",
    });
    authApi.logoutSession.mockResolvedValue(undefined);
    authApi.logoutAllSessions.mockResolvedValue(undefined);
  });

  it("stores access and refresh tokens in secure storage", async () => {
    await useAuthStore.getState().setSession(firstTokens);

    expect(secure.setSecureItem).toHaveBeenCalledWith(
      "veyaship.mobile.access_token",
      "access-1",
    );
    expect(secure.setSecureItem).toHaveBeenCalledWith(
      "veyaship.mobile.refresh_token",
      "refresh-1",
    );
    expect(useAuthStore.getState()).toMatchObject({
      token: "access-1",
      refreshToken: "refresh-1",
      hydrated: true,
    });
  });

  it("rotates the refresh token and updates both secure values", async () => {
    await useAuthStore.getState().setSession(firstTokens);
    vi.clearAllMocks();

    const token = await useAuthStore.getState().refreshSession();

    expect(token).toBe("access-2");
    expect(authApi.refreshAuthSession).toHaveBeenCalledWith("refresh-1");
    expect(useAuthStore.getState().refreshToken).toBe("refresh-2");
  });

  it("revokes the backend session and clears both secure values", async () => {
    await useAuthStore.getState().setSession(firstTokens);
    vi.clearAllMocks();

    await useAuthStore.getState().logout();

    expect(authApi.logoutSession).toHaveBeenCalledWith("access-1");
    expect(secure.deleteSecureItem).toHaveBeenCalledWith(
      "veyaship.mobile.access_token",
    );
    expect(secure.deleteSecureItem).toHaveBeenCalledWith(
      "veyaship.mobile.refresh_token",
    );
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
  });
});
