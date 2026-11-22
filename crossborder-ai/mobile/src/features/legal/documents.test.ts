import { describe, expect, it } from "vitest";

import {
  LEGAL_CENTER_PATH,
  LEGAL_DOCUMENTS,
  LEGAL_DOCUMENT_VERSIONS,
  getLegalDocument,
  loginConsentCopy,
  registerConsentCopy,
  validateRegistrationConsent,
} from "./documents";

describe("移动端法律与隐私中心", () => {
  it("覆盖 App 发布所需的七份公开文档", () => {
    expect(LEGAL_DOCUMENTS.map((document) => document.id)).toEqual([
      "terms",
      "privacy",
      "data-processing",
      "ai-disclosure",
      "security",
      "report",
      "contact",
    ]);
    expect(
      LEGAL_DOCUMENTS.every((document) =>
        document.url.startsWith("https://veyaship.com/"),
      ),
    ).toBe(true);
  });

  it("锁定当前线上文档版本并单独覆盖 AI 内容规则", () => {
    expect(LEGAL_DOCUMENT_VERSIONS).toEqual({
      terms: "1.1",
      privacy: "1.3",
      dataProcessing: "1.2",
      aiDisclosure: "1.0",
    });
    expect(registerConsentCopy).toContain("AI 使用说明");
    expect(loginConsentCopy).toContain("AI 使用说明");
    expect(getLegalDocument("ai-disclosure").url).toBe(
      "https://veyaship.com/ai-disclosure",
    );
    expect(() =>
      getLegalDocument("missing" as Parameters<typeof getLegalDocument>[0]),
    ).toThrow("未配置法务文档");
  });

  it("注册前必须显式同意协议", () => {
    expect(validateRegistrationConsent(false)).toBe(
      "请先阅读并同意服务条款、隐私政策与 AI 使用说明",
    );
    expect(validateRegistrationConsent(true)).toBeNull();
  });

  it("账号页和登录页共用同一个法务中心路由", () => {
    expect(LEGAL_CENTER_PATH).toBe("/legal");
  });
});
