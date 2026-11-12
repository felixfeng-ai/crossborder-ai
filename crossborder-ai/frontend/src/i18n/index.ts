import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import zh from './locales/zh.json'
import ja from './locales/ja.json'
import ko from './locales/ko.json'
import es from './locales/es.json'
import fr from './locales/fr.json'
import de from './locales/de.json'
import pt from './locales/pt.json'
import ru from './locales/ru.json'
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_DETECTION_ORDER,
  LANGUAGE_STORAGE_KEY,
} from './language'

const resources = {
  en: { translation: en },
  zh: { translation: zh },
  ja: { translation: ja },
  ko: { translation: ko },
  es: { translation: es },
  fr: { translation: fr },
  de: { translation: de },
  pt: { translation: pt },
  ru: { translation: ru },
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: DEFAULT_LANGUAGE,
    detection: {
      order: [...LANGUAGE_DETECTION_ORDER],
      caches: ['localStorage'],
      lookupLocalStorage: LANGUAGE_STORAGE_KEY,
    },
    interpolation: {
      escapeValue: false,
    },
  })

export default i18n
