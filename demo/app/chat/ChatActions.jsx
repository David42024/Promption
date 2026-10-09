"use client";
import { useState } from "react";

function download(action) {
  const bytes = Uint8Array.from(atob(action.data), char => char.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: action.mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = action.name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ChatActions({ actions = [], onAnswer }) {
  const dialog = actions.find(action => action.type === "dialog");
  const files = actions.filter(action => action.type === "attachment");
  const [error, setError] = useState("");
  const [asking, setAsking] = useState(Boolean(dialog));
  const [answer, setAnswer] = useState("");
  const [confirmFile, setConfirmFile] = useState(null);

  async function receive(file) {
    try {
      download(file);
      setError("");
    } catch (cause) {
      setError(cause.message || "No se pudo descargar el archivo.");
    }
  }

  return <div className="chat-actions">
    {files.map((file, index) => <button key={index} type="button" className="chat-attachment"
      onClick={() => file.confirm ? setConfirmFile(file) : receive(file)}>
      📄 Descargar {file.name || file.title}
    </button>)}
    {error && <span role="alert">{error}</span>}
    {dialog && !asking && <button type="button" className="chat-attachment" onClick={() => setAsking(true)}>
      Responder pregunta
    </button>}
    {asking && dialog && <div className="chat-action-overlay" role="dialog" aria-modal="true" aria-label={dialog.question}>
      <form className="chat-action-modal" onSubmit={event => {
        event.preventDefault();
        if (answer.trim()) {
          setAsking(false);
          onAnswer(dialog.question, answer.trim());
        }
      }}>
        <h3>{dialog.question}</h3>
        <label>{dialog.field_label}<input autoFocus maxLength={1000} value={answer}
          onChange={event => setAnswer(event.target.value)} /></label>
        <div className="chat-action-buttons">
          <button type="button" onClick={() => setAsking(false)}>Cancelar</button>
          <button type="submit" disabled={!answer.trim()}>Enviar</button>
        </div>
      </form>
    </div>}
    {confirmFile && <div className="chat-action-overlay" role="dialog" aria-modal="true" aria-label="Confirmar descarga">
      <div className="chat-action-modal">
        <h3>Confirmar descarga sensible</h3>
        <p>Este archivo puede contener información confidencial autorizada para tu rol. ¿Quieres descargarlo en este dispositivo?</p>
        <div className="chat-action-buttons">
          <button type="button" onClick={() => setConfirmFile(null)}>Cancelar</button>
          <button type="button" onClick={() => { receive(confirmFile); setConfirmFile(null); }}>Descargar</button>
        </div>
      </div>
    </div>}
  </div>;
}
