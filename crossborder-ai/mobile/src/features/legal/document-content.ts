import legalDocuments from "./legal-documents.json";
import type { LegalDocumentId } from "./documents";

export type LegalSectionContent = {
  id: string;
  title: string;
  paragraphs: string[];
  bullets?: string[];
};

export type LegalDocumentContent = {
  slug: LegalDocumentId;
  path: string;
  title: string;
  shortTitle: string;
  summary: string;
  version: string;
  effectiveDate: string;
  sections: LegalSectionContent[];
};

/**
 * 正文由 Web 法务源生成，App 只负责原生展示，避免两套页面各改一份。
 */
export const LEGAL_DOCUMENTS_CONTENT =
  legalDocuments as LegalDocumentContent[];

export const LEGAL_CONTACT_EMAIL = "admin@veyaship.com";

export function getLegalDocumentContent(id: LegalDocumentId) {
  const document = LEGAL_DOCUMENTS_CONTENT.find((item) => item.slug === id);
  if (!document) {
    throw new Error(`未配置法务正文：${id}`);
  }
  return document;
}

export function legalContactUrl(subject: string) {
  return `mailto:${LEGAL_CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}`;
}
