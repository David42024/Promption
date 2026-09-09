"use client";
import { createContext, useContext, useState, useEffect } from "react";

const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const [msgs, setMsgs] = useState([]);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("demo_chat_msgs");
    if (saved) {
      try {
        setMsgs(JSON.parse(saved));
      } catch {}
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("demo_chat_msgs", JSON.stringify(msgs));
  }, [msgs]);

  return (
    <ChatContext.Provider value={{ msgs, setMsgs, isOpen, setIsOpen }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  return useContext(ChatContext);
}
