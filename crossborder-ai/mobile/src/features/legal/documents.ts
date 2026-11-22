export type LegalDocumentId =
  | "terms"
  | "privacy"
  | "data-processing"
  | "ai-disclosure"
  | "security"
  | "report"
  | "contact";

export type LegalDocument = {
  id: LegalDocumentId;
  title: string;
  description: string;
  url: string;
  group: "agreements" | "support";
};

const legalBaseUrl = "https://veyaship.com";

/**
 * App 只维护文档入口和版本，不复制法律正文，避免网页与 App 出现双事实源。
 */
export const LEGAL_DOCUMENTS: LegalDocument[] = [
  {
    id: "terms",
    title: "服务条款",
    description: "账号、服务范围、平台责任与 AI 输出边界",
    url: `${legalBaseUrl}/terms`,
    group: "agreements",
  },
  {
    id: "privacy",
    title: "隐私政策",
    description: "账号、素材、店铺授权与第三方模型的数据处理",
    url: `${legalBaseUrl}/privacy`,
    group: "agreements",
  },
  {
    id: "data-processing",
    title: "数据处理与删除",
    description: "数据角色、保留期限、删除请求与安全事件",
    url: `${legalBaseUrl}/data-processing`,
    group: "agreements",
  },
  {
    id: "ai-disclosure",
    title: "AI 使用说明",
    description: "生成限制、人工复核、内容权利与 AI 标识",
    url: `${legalBaseUrl}/ai-disclosure`,
    group: "agreements",
  },
  {
    id: "security",
    title: "安全与事件响应",
    description: "访问控制、店铺 Token 和安全事件处理原则",
    url: `${legalBaseUrl}/security`,
    group: "support",
  },
  {
    id: "report",
    title: "侵权与违规举报",
    description: "提交知识产权、违法商品或有害 AI 内容问题",
    url: `${legalBaseUrl}/report`,
    group: "support",
  },
  {
    id: "contact",
    title: "联系我们",
    description: "账号、隐私、数据、安全与支持请求入口",
    url: `${legalBaseUrl}/contact`,
    group: "support",
  },
];

export const LEGAL_DOCUMENT_VERSIONS = {
  terms: "1.1",
  privacy: "1.3",
  dataProcessing: "1.2",
  aiDisclosure: "1.0",
} as const;

export const LEGAL_CENTER_PATH = "/legal" as const;

export const registerConsentCopy =
  "我已阅读并同意《服务条款》《隐私政策》与《AI 使用说明》";

export const registerConsentTitle = "我已阅读并同意以下协议";

export const registerConsentLinks =
  "服务条款 · 隐私政策 · AI 使用说明";

export const loginConsentCopy =
  "登录即代表同意《服务条款》《隐私政策》与《AI 使用说明》";

export function getLegalDocument(id: LegalDocumentId) {
  const document = LEGAL_DOCUMENTS.find((item) => item.id === id);
  if (!document) {
    throw new Error(`未配置法务文档：${id}`);
  }
  return document;
}

/**
 * 注册必须显式确认三项文档；登录继续使用提交动作作为同意行为。
 */
export function validateRegistrationConsent(accepted: boolean) {
  return accepted
    ? null
    : "请先阅读并同意服务条款、隐私政策与 AI 使用说明";
}
