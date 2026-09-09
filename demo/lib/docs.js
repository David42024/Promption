import fs from "node:fs";
import path from "node:path";

const DOCS_DIR = path.join(process.cwd(), "data", "docs");

function aclToTier(acl = []) {
  if (acl.includes("admin") && acl.length === 1) return "confidencial";
  if (acl.includes("admin") || acl.includes("ventas")) return "interno";
  return "publico";
}

function parse(raw) {
  const m = raw.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  let meta = {};
  let body = raw;
  if (m) {
    body = m[2].trim();
    for (const line of m[1].split("\n")) {
      const i = line.indexOf(":");
      if (i > 0) {
        const k = line.slice(0, i).trim();
        let v = line.slice(i + 1).trim();
        try {
          v = JSON.parse(v);
        } catch {
          v = v.replace(/^"|"$/g, "");
        }
        meta[k] = v;
      }
    }
  }
  return { meta, body };
}

export function listDocs() {
  if (!fs.existsSync(DOCS_DIR)) return [];
  return fs
    .readdirSync(DOCS_DIR)
    .filter((f) => f.endsWith(".md"))
    .map((f) => {
      const { meta, body } = parse(fs.readFileSync(path.join(DOCS_DIR, f), "utf-8"));
      const acl = meta.acl || [];
      const tier = meta.tier || aclToTier(acl);
      return { id: meta.id || f.replace(/\.md$/, ""), title: meta.title || f, acl, tier, body };
    });
}

export function canAccess(doc, roles = []) {
  if (!doc.acl || doc.acl.length === 0) return true;
  return doc.acl.some((r) => roles.includes(r));
}

export function visibleDocs(roles = []) {
  return listDocs()
    .filter((d) => canAccess(d, roles))
    .map(({ body, ...rest }) => rest);
}

export function getDoc(id, roles = []) {
  const doc = listDocs().find((d) => d.id === id);
  if (!doc) return { status: 404 };
  if (!canAccess(doc, roles)) return { status: 403, id, title: doc.title, tier: doc.tier };
  return { status: 200, doc };
}
