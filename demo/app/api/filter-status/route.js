const CHAT_API_URL = (process.env.NEXT_PUBLIC_CHAT_API_URL || "http://localhost:8001").replace(/\/$/, "");

function headers() {
  return process.env.CHAT_SERVICE_TOKEN
    ? { "X-Chat-Service-Token": process.env.CHAT_SERVICE_TOKEN }
    : {};
}

export async function GET() {
  try {
    const response = await fetch(`${CHAT_API_URL}/api/v1/security/state`, {
      headers: headers(),
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Chat Service ${response.status}`);
    const state = await response.json();
    return Response.json({
      filterEnabled: state.filter_enabled,
      outputGuardEnabled: state.output_guard_enabled,
    });
  } catch {
    return Response.json(
      { filterEnabled: true, outputGuardEnabled: true, unavailable: true },
      { status: 503 }
    );
  }
}
