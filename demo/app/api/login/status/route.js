import { cookies } from "next/headers";

export async function GET() {
  try {
    const cookieStore = cookies();
    const userCookie = cookieStore.get("demo_user");
    
    if (!userCookie) {
      return Response.json({ user: null, authenticated: false });
    }
    
    const user = JSON.parse(userCookie.value);
    return Response.json({ 
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
        roles: user.roles,
        avatar: user.avatar,
        puesto: user.puesto,
      }, 
      authenticated: true 
    });
  } catch {
    return Response.json({ user: null, authenticated: false });
  }
}