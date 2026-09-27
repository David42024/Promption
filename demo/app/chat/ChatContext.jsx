"use client";
import { createContext, useContext, useEffect, useState } from "react";

const ChatContext = createContext(null);

export function ChatProvider({ children, userId }) {
  const [msgs, setMsgs] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    setMsgs([]);
    setHistoryLoaded(false);
    fetch("/api/chat", { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() : { messages: [] })
      .then((data) => {
        if (active) setMsgs(Array.isArray(data.messages) ? data.messages : []);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setHistoryLoaded(true);
      });
    return () => { active = false; };
  }, [userId]);

  async function newConversation() {
    const response = await fetch("/api/chat", { method: "DELETE" });
    if (!response.ok) throw new Error("No se pudo iniciar otra conversación");
    setMsgs([]);
  }

  return (
    <ChatContext.Provider value={{ msgs, setMsgs, isOpen, setIsOpen, historyLoaded, newConversation }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  return useContext(ChatContext);
}
