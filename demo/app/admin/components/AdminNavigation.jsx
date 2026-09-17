"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";


const ITEMS = [
  { href: "/admin", label: "Operaciones y auditoría", icon: "🛡️" },
  { href: "/admin/estadisticas", label: "Estadísticas", icon: "📊" },
];


export default function AdminNavigation() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Módulos de administración"
      style={{
        display: "flex",
        gap: 10,
        flexWrap: "wrap",
        padding: 8,
        marginBottom: 24,
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        background: "rgba(15, 23, 42, 0.48)",
      }}
    >
      {ITEMS.map(item => {
        const active = item.href === "/admin"
          ? pathname === item.href
          : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "10px 16px",
              borderRadius: "var(--radius-md)",
              textDecoration: "none",
              fontWeight: 700,
              color: active ? "white" : "var(--text-secondary)",
              background: active
                ? "linear-gradient(135deg, #6366f1, #4f46e5)"
                : "transparent",
              boxShadow: active ? "0 8px 24px rgba(99, 102, 241, 0.24)" : "none",
            }}
          >
            <span aria-hidden="true">{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
