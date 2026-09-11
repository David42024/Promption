"use client";
import { createContext, useContext, useState, useEffect } from "react";

const ChatContext = createContext(null);

export function ChatProvider({ children, userId }) {
  const [msgs, setMsgs] = useState([]);
  const [isOpen, setIsOpen] = useState(false);

  const storageKey = userId ? `demo_chat_msgs_${userId}` : "demo_chat_msgs_guest";

  useEffect(() => {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        setMsgs(JSON.parse(saved));
      } catch {}
    }
  }, [storageKey]);

  useEffect(() => {
    localStorage.setItem(storageKey, JSON.stringify(msgs));
  }, [msgs, storageKey]);

  return (
    <ChatContext.Provider value={{ msgs, setMsgs, isOpen, setIsOpen }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  return useContext(ChatContext);
}
