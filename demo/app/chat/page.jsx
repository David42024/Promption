import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { readSessionToken } from "../../lib/session.js";
import ChatClient from "./ChatClient";
import { ChatProvider } from "./ChatContext";

export default function ChatPage() {
  const user = readSessionToken(cookies().get("demo_user")?.value);
  if (!user) redirect("/login");
  return (
    <div className="fullscreen-chat">
      <ChatProvider userId={user.id}>
        <ChatClient user={user} />
      </ChatProvider>
    </div>
  );
}
