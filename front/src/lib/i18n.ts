// Core UI dictionary (English + Hindi) for navigation, statuses, and primary actions.
// Rule text, Handbook clause references, and extracted document content are never translated.
// NOTE: Hindi strings are machine-drafted and marked for native-speaker review before the demo.
import { useSyncExternalStore } from "react";

export type Lang = "en" | "hi";

const KEY = "pramaan:lang";
const listeners = new Set<() => void>();

function readInitial(): Lang {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "hi" || v === "en") return v;
  } catch { /* storage blocked */ }
  return "en";
}

let currentLang: Lang = typeof window !== "undefined" ? readInitial() : "en";
if (typeof document !== "undefined") document.documentElement.lang = currentLang;

export function setLang(next: Lang) {
  if (next === currentLang) return;
  currentLang = next;
  try { localStorage.setItem(KEY, next); } catch { /* ignore */ }
  if (typeof document !== "undefined") document.documentElement.lang = next;
  listeners.forEach((l) => l());
}

export function useLang(): [Lang, (next: Lang) => void] {
  const lang = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    () => currentLang,
  );
  return [lang, setLang];
}

// Machine-drafted Hindi strings — review with a native Hindi speaker before judging day.
const HI: Record<string, string> = {
  "Applications": "आवेदन (Applications)",
  "Scrutiny queue": "जाँच सूची (Scrutiny queue)",
  "Rule pack": "नियम संग्रह (Rule pack)",
  "Audit trail": "ऑडिट रिकॉर्ड (Audit trail)",
  "Benchmark": "बेंचमार्क (Benchmark)",
  "Help": "सहायता (Help)",
  "Account": "खाता (Account)",
  "Notifications": "सूचनाएँ (Notifications)",
  "Registrations": "पंजीकरण (Registrations)",
  "Users": "उपयोगकर्ता (Users)",
  "System": "सिस्टम (System)",
  "Sign out": "साइन आउट",
  "Sign in": "साइन इन",
  "Draft": "प्रारूप (Draft)",
  "Checking documents": "दस्तावेज़ों की जाँच जारी",
  "Ready for scrutiny": "जाँच हेतु तैयार",
  "Deficiencies flagged": "कमियाँ चिह्नित",
  "Needs official review": "अधिकारी समीक्षा आवश्यक",
  "Verified at source": "स्रोत से सत्यापित",
  "Mismatch with source": "स्रोत से असंगति",
  "Authentic, expired": "प्रामाणिक, अवधि समाप्त",
  "Verification pending": "सत्यापन लंबित",
  "Source unavailable": "स्रोत अनुपलब्ध",
  "Manual check needed": "मैनुअल जाँच आवश्यक",
};

export function tr(text: string, lang: Lang = currentLang): string {
  return lang === "hi" ? (HI[text] ?? text) : text;
}
