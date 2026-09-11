"use client";
import { useState, useEffect } from "react";
import Link from "next/link";

const UserIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

const LoginIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
    <polyline points="10 17 15 12 10 7" />
    <line x1="15" y1="12" x2="3" y2="12" />
  </svg>
);

const LogoutIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

const ShieldIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </svg>
);

export default function GlobalHeader() {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      try {
        const r = await fetch("/api/login/status");
        if (r.ok) {
          const data = await r.json();
          setCurrentUser(data.user);
        }
      } catch {
        setCurrentUser(null);
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/login", { method: "DELETE" });
      setCurrentUser(null);
      window.location.href = "/";
    } catch {
      console.error("Error al cerrar sesión");
    }
  };

  return (
    <header 
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        height: "64px",
        background: "rgba(10, 14, 26, 0.95)",
        backdropFilter: "blur(20px)",
        borderBottom: "1px solid var(--border)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 24px",
        boxShadow: "0 4px 20px rgba(0, 0, 0, 0.3)"
      }}
    >
      {/* Logo y branding */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Link 
          href="/"
          style={{ 
            display: "flex", 
            alignItems: "center", 
            gap: 10,
            textDecoration: "none",
            color: "inherit"
          }}
        >
          <span style={{ fontSize: "1.8rem" }}>🛡️</span>
          <div>
            <h1 style={{ 
              margin: 0, 
              fontSize: "1.1rem", 
              fontWeight: 700,
              color: "var(--text-primary)",
              letterSpacing: "0.02em"
            }}>
              Promption Shop
            </h1>
            <p style={{ 
              margin: "2px 0 0 0", 
              fontSize: "0.75rem", 
              color: "var(--text-muted)",
              fontWeight: 500
            }}>
              Demo Seguridad LLM
            </p>
          </div>
        </Link>
      </div>

      {/* Estado de autenticación */}
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        {/* Indicador de protección */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 16px",
          borderRadius: "var(--radius-full)",
          background: "rgba(16, 185, 129, 0.15)",
          border: "1px solid rgba(16, 185, 129, 0.3)",
          color: "var(--success-400)",
          fontSize: "0.8rem",
          fontWeight: 600
        }}>
          <ShieldIcon />
          <span>Protegido</span>
        </div>

        {/* Usuario autenticado */}
        {loading ? (
          <div style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "var(--border)",
            animation: "pulse 1.5s infinite"
          }} />
        ) : currentUser ? (
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 14px",
              borderRadius: "var(--radius-full)",
              background: "rgba(99, 102, 241, 0.15)",
              border: "1px solid rgba(99, 102, 241, 0.3)",
              color: "var(--brand-400)",
              fontSize: "0.85rem",
              fontWeight: 600
            }}>
              <span style={{ fontSize: "1.2rem" }}>{currentUser.avatar || "👤"}</span>
              <span>{currentUser.name}</span>
              {currentUser.roles && currentUser.roles.length > 0 && (
                <span style={{
                  padding: "2px 8px",
                  borderRadius: "var(--radius-sm)",
                  background: "rgba(99, 102, 241, 0.3)",
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em"
                }}>
                  {currentUser.roles[0]}
                </span>
              )}
            </div>
            
            <Link
              href="/chat"
              style={{
                padding: "8px 16px",
                borderRadius: "var(--radius-md)",
                background: "var(--brand-500)",
                color: "white",
                textDecoration: "none",
                fontSize: "0.85rem",
                fontWeight: 600,
                border: "none",
                cursor: "pointer"
              }}
            >
              Chat
            </Link>

            <button
              onClick={handleLogout}
              style={{
                padding: "8px",
                borderRadius: "var(--radius-md)",
                background: "transparent",
                border: "1px solid var(--border)",
                color: "var(--text-muted)",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center"
              }}
              title="Cerrar sesión"
            >
              <LogoutIcon />
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 14px",
              borderRadius: "var(--radius-full)",
              background: "rgba(148, 163, 184, 0.15)",
              border: "1px solid var(--border)",
              color: "var(--text-muted)",
              fontSize: "0.85rem",
              fontWeight: 500
            }}>
              <UserIcon />
              <span>No autenticado</span>
            </div>
            
            <Link
              href="/login"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 16px",
                borderRadius: "var(--radius-md)",
                background: "var(--brand-500)",
                color: "white",
                textDecoration: "none",
                fontSize: "0.85rem",
                fontWeight: 600
              }}
            >
              <LoginIcon />
              Iniciar sesión
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}