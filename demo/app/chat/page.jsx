import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import ChatClient from "./ChatClient";
import { ChatProvider } from "./ChatContext";

export default function ChatPage() {
  let user = null;
  try {
    user = JSON.parse(cookies().get("demo_user")?.value || "null");
  } catch {
    user = null;
  }
  if (!user) redirect("/login");
  return (
    <div className="fullscreen-chat">
      <ChatProvider>
        <ChatClient user={user} />
      </ChatProvider>
    </div>
  );
}
