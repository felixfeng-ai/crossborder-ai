import { LEGAL_DOCUMENTS_CONTENT } from "./document-content";

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
  version: string;
  effectiveDate: string;
  group: "agreements" | "support";
  native: true;
};

/**
 * 入口名称、版本和正文都来自同一份生成数据。
 */
const legalGroups: Record<
  LegalDocumentId,
  LegalDocument["group"]
> = {
  terms: "agreements",
  privacy: "agreements",
  "data-processing": "agreements",
  "ai-disclosure": "agreements",
  security: "support",
  report: "support",
  contact: "support",
};

export const LEGAL_DOCUMENTS: LegalDocument[] =
  LEGAL_DOCUMENTS_CONTENT.map((document) => ({
    id: document.slug,
    title: document.shortTitle,
    description: document.summary,
    version: document.version,
    effectiveDate: document.effectiveDate,
    group: legalGroups[document.slug],
    native: true,
  }));

export const LEGAL_DOCUMENT_VERSIONS = {
  terms: getLegalDocumentContentVersion("terms"),
  privacy: getLegalDocumentContentVersion("privacy"),
  dataProcessing: getLegalDocumentContentVersion("data-processing"),
  aiDisclosure: getLegalDocumentContentVersion("ai-disclosure"),
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

export function legalDocumentPath(id: LegalDocumentId) {
  return `/legal/${id}` as const;
}

function getLegalDocumentContentVersion(id: LegalDocumentId) {
  return (
    LEGAL_DOCUMENTS_CONTENT.find((document) => document.slug === id)
      ?.version ?? ""
  );
}

/**
 * 注册必须显式确认三项文档；登录继续使用提交动作作为同意行为。
 */
export function validateRegistrationConsent(accepted: boolean) {
  return accepted
    ? null
    : "请先阅读并同意服务条款、隐私政策与 AI 使用说明";
}
