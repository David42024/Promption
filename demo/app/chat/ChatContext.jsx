"use client";
import { createContext, useContext, useState } from "react";

const ChatContext = createContext(null);

export function ChatProvider({ children, userId }) {
  const [msgs, setMsgs] = useState([]);
  const [isOpen, setIsOpen] = useState(false);

  return (
    <ChatContext.Provider value={{ msgs, setMsgs, isOpen, setIsOpen }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  return useContext(ChatContext);
}
