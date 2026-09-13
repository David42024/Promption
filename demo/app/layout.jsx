import "./globals.css";

export const metadata = {
  metadataBase: new URL("https://promption.dev"),
  title: {
    default: "Promption · Demo Shop — Seguridad contra Prompt Injection",
    template: "%s · Promption Demo",
  },
  description:
    "Tienda demo protegida por Prompt Injection Filter. Chatbot, login con roles y panel de administración que demuestran la protección multi-capa contra ataques de inyección de prompts en LLMs.",
  keywords: [
    "prompt injection",
    "seguridad LLM",
    "IA segura",
    "filter API",
    "machine learning",
    "chatbot seguro",
    "OWASP LLM",
  ],
  authors: [{ name: "Promption Team" }],
  openGraph: {
    type: "website",
    locale: "es_ES",
    url: "https://promption.dev",
    title: "Promption · Demo Shop",
    description:
      "Protección multi-capa contra Prompt Injection en aplicaciones LLM. Heurística + Machine Learning + Output Guard.",
    siteName: "Promption Demo",
  },
  twitter: {
    card: "summary_large_image",
    title: "Promption · Demo Shop",
    description:
      "Protección multi-capa contra Prompt Injection: heurística, ML y output guard en un solo Filter API.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0e1a" },
    { media: "(prefers-color-scheme: light)", color: "#0a0e1a" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body data-deployment-marker="promption-shop-2026-09-13">{children}</body>
    </html>
  );
}
