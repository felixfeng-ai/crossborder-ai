import { describe, expect, it } from "vitest";

import {
  LEGAL_CENTER_PATH,
  LEGAL_DOCUMENTS,
  LEGAL_DOCUMENT_VERSIONS,
  getLegalDocument,
  legalDocumentPath,
  loginConsentCopy,
  registerConsentCopy,
  validateRegistrationConsent,
} from "./documents";
import {
  LEGAL_DOCUMENTS_CONTENT,
  getLegalDocumentContent,
} from "./document-content";

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
    expect(LEGAL_DOCUMENTS.every((document) => document.native)).toBe(true);
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
    expect(getLegalDocument("ai-disclosure").title).toBe("AI 使用说明");
    expect(() =>
      getLegalDocument("missing" as Parameters<typeof getLegalDocument>[0]),
    ).toThrow("未配置法务文档");
  });

  it("七份原生正文包含真实章节和版本", () => {
    expect(LEGAL_DOCUMENTS_CONTENT).toHaveLength(7);
    expect(
      LEGAL_DOCUMENTS_CONTENT.every(
        (document) =>
          document.sections.length >= 4 &&
          document.version.length > 0 &&
          document.effectiveDate.startsWith("2026-"),
      ),
    ).toBe(true);

    expect(
      JSON.stringify(getLegalDocumentContent("privacy")),
    ).toContain("Shopify");
    expect(
      JSON.stringify(getLegalDocumentContent("ai-disclosure")),
    ).toContain("人工复核");
  });

  it("注册前必须显式同意协议", () => {
    expect(validateRegistrationConsent(false)).toBe(
      "请先阅读并同意服务条款、隐私政策与 AI 使用说明",
    );
    expect(validateRegistrationConsent(true)).toBeNull();
  });

  it("账号页和登录页共用同一个法务中心路由", () => {
    expect(LEGAL_CENTER_PATH).toBe("/legal");
    expect(legalDocumentPath("terms")).toBe("/legal/terms");
  });
});
