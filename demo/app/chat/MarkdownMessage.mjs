"use client";

import React from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";

const remarkPlugins = [remarkGfm];
const rehypePlugins = [rehypeSanitize];

export function safeMarkdownUrl(value) {
  if (typeof value !== "string") return "";
  const url = value.trim();
  if (!url || /[\u0000-\u0020\u007f\\]/.test(url) || url.startsWith("//")) return "";
  if (url.startsWith("#") || url.startsWith("/")) return url;
  try {
    const parsed = new URL(url);
    return ["https:", "http:"].includes(parsed.protocol) && !parsed.username && !parsed.password ? url : "";
  } catch {
    return "";
  }
}

function SafeLink({ href, title, children }) {
  const url = safeMarkdownUrl(href);
  if (!url) return React.createElement("span", null, children);
  const external = /^https?:/i.test(url);
  return React.createElement("a", { href: url, title,
    ...(external ? { target: "_blank", rel: "noopener noreferrer", referrerPolicy: "no-referrer" } : {}) }, children);
}

function ImageLink({ src, alt }) {
  return React.createElement(SafeLink, { href: src }, `🖼️ ${alt || "Ver imagen"}`);
}

function ScrollableTable({ children }) {
  return React.createElement("div", { className: "chat-markdown-table", tabIndex: 0,
    role: "region", "aria-label": "Tabla del mensaje" }, React.createElement("table", null, children));
}

const components = { a: SafeLink, img: ImageLink, table: ScrollableTable };

export default function MarkdownMessage({ text }) {
  return React.createElement("div", { className: "chat-markdown" },
    React.createElement(Markdown, { remarkPlugins, rehypePlugins, components,
      skipHtml: true, urlTransform: safeMarkdownUrl }, typeof text === "string" ? text : ""));
}
