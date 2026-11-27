import { createContext, useContext, useState } from "react";
import translations from "./i18n.js";

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try { return localStorage.getItem("ff.lang") || "en"; } catch { return "en"; }
  });

  function toggle() {
    const next = lang === "en" ? "ta" : "en";
    setLang(next);
    try { localStorage.setItem("ff.lang", next); } catch {}
  }

  // t("key") returns the translated string, falling back to English
  function t(key) {
    return translations[lang]?.[key] ?? translations.en[key] ?? key;
  }

  return (
    <LanguageContext.Provider value={{ lang, toggle, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}

// Shorthand hook: const t = useT();  then t("save")
export function useT() {
  return useContext(LanguageContext).t;
}
