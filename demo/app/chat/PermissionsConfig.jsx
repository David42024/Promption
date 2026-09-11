"use client";
import { useState } from "react";
import { 
  DEFAULT_PERMISSIONS, 
  hasTierAccess, 
  canUseTool,
  getAccessibleTiers 
} from "../../lib/permissions-config";

const SettingsIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);

const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const XIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

export default function PermissionsConfig({ isOpen, onClose, currentRole }) {
  const [activeTab, setActiveTab] = useState("tiers");
  const [customConfig, setCustomConfig] = useState(DEFAULT_PERMISSIONS);

  if (!isOpen) return null;

  return (
    <div 
      className="config-modal-overlay"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 2000,
        backdropFilter: "blur(4px)"
      }}
      onClick={onClose}
    >
      <div 
        className="config-modal"
        style={{
          background: "var(--bg-card-solid)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-xl)",
          width: "90%",
          maxWidth: "800px",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 60px rgba(0, 0, 0, 0.6)"
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div 
          className="config-header"
          style={{
            padding: "20px 24px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center"
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: "1.2rem", fontWeight: 600 }}>
              ⚙️ Configuración de Permisos
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "0.85rem", color: "var(--text-muted)" }}>
              Sistema generalizable para cualquier negocio
            </p>
          </div>
          <button 
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: 8,
              borderRadius: "var(--radius-md)"
            }}
          >
            <CloseIcon />
          </button>
        </div>

        <div 
          className="config-tabs"
          style={{
            display: "flex",
            borderBottom: "1px solid var(--border)",
            padding: "0 24px"
          }}
        >
          {["tiers", "roles", "tools"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: "16px 20px",
                background: "transparent",
                border: "none",
                borderBottom: activeTab === tab ? "2px solid var(--brand-500)" : "2px solid transparent",
                color: activeTab === tab ? "var(--text-primary)" : "var(--text-muted)",
                cursor: "pointer",
                fontSize: "0.9rem",
                fontWeight: activeTab === tab ? 600 : 400,
                textTransform: "capitalize"
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        <div 
          className="config-content"
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "24px"
          }}
        >
          {activeTab === "tiers" && (
            <div className="tiers-config">
              <h4 style={{ margin: "0 0 16px 0", fontSize: "1rem" }}>Tiers de Información</h4>
              {Object.entries(customConfig.tiers).map(([key, tier]) => (
                <div 
                  key={key}
                  style={{
                    background: "rgba(99, 102, 241, 0.05)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    padding: "16px",
                    marginBottom: "12px"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                    <span style={{ fontSize: "1.5rem" }}>{tier.icon}</span>
                    <div>
                      <h5 style={{ margin: 0, fontSize: "1rem" }}>{tier.label}</h5>
                      <p style={{ margin: "4px 0 0 0", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                        {tier.description}
                      </p>
                    </div>
                  </div>
                  <div>
                    <p style={{ margin: "0 0 8px 0", fontSize: "0.85rem", fontWeight: 500 }}>
                      Roles con acceso:
                    </p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {Object.keys(customConfig.roles).map((role) => (
                        <span
                          key={role}
                          style={{
                            fontSize: "0.8rem",
                            padding: "4px 10px",
                            borderRadius: "var(--radius-sm)",
                            background: hasTierAccess(role, key) 
                              ? "rgba(16, 185, 129, 0.2)" 
                              : "rgba(239, 68, 68, 0.1)",
                            color: hasTierAccess(role, key) 
                              ? "var(--success-400)" 
                              : "var(--error-400)",
                            border: hasTierAccess(role, key) 
                              ? "1px solid rgba(16, 185, 129, 0.3)" 
                              : "1px solid rgba(239, 68, 68, 0.2)",
                            display: "flex",
                            alignItems: "center",
                            gap: 6
                          }}
                        >
                          {hasTierAccess(role, key) ? <CheckIcon /> : <XIcon />}
                          {customConfig.roles[role].label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === "roles" && (
            <div className="roles-config">
              <h4 style={{ margin: "0 0 16px 0", fontSize: "1rem" }}>Roles del Sistema</h4>
              {Object.entries(customConfig.roles).map(([key, role]) => (
                <div 
                  key={key}
                  style={{
                    background: "rgba(139, 92, 246, 0.05)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    padding: "16px",
                    marginBottom: "12px"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                    <span style={{ fontSize: "1.5rem" }}>{role.icon}</span>
                    <div>
                      <h5 style={{ margin: 0, fontSize: "1rem" }}>{role.label}</h5>
                      <p style={{ margin: "4px 0 0 0", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                        {role.description}
                      </p>
                    </div>
                  </div>
                  <div>
                    <p style={{ margin: "0 0 8px 0", fontSize: "0.85rem", fontWeight: 500 }}>
                      Tiers accesibles:
                    </p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {role.tierAccess.map((tier) => (
                        <span
                          key={tier}
                          style={{
                            fontSize: "0.8rem",
                            padding: "4px 10px",
                            borderRadius: "var(--radius-sm)",
                            background: "rgba(99, 102, 241, 0.2)",
                            color: "var(--brand-400)",
                            border: "1px solid rgba(99, 102, 241, 0.3)"
                          }}
                        >
                          {customConfig.tiers[tier]?.icon} {customConfig.tiers[tier]?.label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === "tools" && (
            <div className="tools-config">
              <h4 style={{ margin: "0 0 16px 0", fontSize: "1rem" }}>Herramientas MCP</h4>
              {Object.entries(customConfig.tools).map(([key, tool]) => (
                <div 
                  key={key}
                  style={{
                    background: "rgba(34, 211, 238, 0.05)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    padding: "16px",
                    marginBottom: "12px"
                  }}
                >
                  <div style={{ marginBottom: 8 }}>
                    <h5 style={{ margin: 0, fontSize: "0.95rem" }}>{tool.name}</h5>
                    <p style={{ margin: "4px 0 0 0", fontSize: "0.85rem", color: "var(--text-muted)" }}>
                      {tool.description}
                    </p>
                  </div>
                  <div>
                    <p style={{ margin: "0 0 8px 0", fontSize: "0.85rem", fontWeight: 500 }}>
                      Tier: {customConfig.tiers[tool.tier]?.icon} {customConfig.tiers[tool.tier]?.label}
                    </p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {Object.keys(customConfig.roles).map((role) => (
                        <span
                          key={role}
                          style={{
                            fontSize: "0.8rem",
                            padding: "4px 10px",
                            borderRadius: "var(--radius-sm)",
                            background: canUseTool(role, key) 
                              ? "rgba(16, 185, 129, 0.2)" 
                              : "rgba(239, 68, 68, 0.1)",
                            color: canUseTool(role, key) 
                              ? "var(--success-400)" 
                              : "var(--error-400)",
                            border: canUseTool(role, key) 
                              ? "1px solid rgba(16, 185, 129, 0.3)" 
                              : "1px solid rgba(239, 68, 68, 0.2)",
                            display: "flex",
                            alignItems: "center",
                            gap: 6
                          }}
                        >
                          {canUseTool(role, key) ? <CheckIcon /> : <XIcon />}
                          {customConfig.roles[role].label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div 
          className="config-footer"
          style={{
            padding: "16px 24px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center"
          }}
        >
          <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Esta configuración es generalizable para cualquier negocio
          </p>
          <button
            onClick={onClose}
            style={{
              padding: "10px 20px",
              background: "var(--brand-500)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: "0.9rem",
              fontWeight: 500
            }}
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
}