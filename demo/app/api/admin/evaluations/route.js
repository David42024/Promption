import { cookies } from "next/headers";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { isAdmin } from "../../../../lib/shop.js";
import { readSessionToken } from "../../../../lib/session.js";
import library from "../../../../../packages/ai-sdk/package.json";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const user = readSessionToken(cookies().get("demo_user")?.value);
  if (!user || !isAdmin(user)) return Response.json({ error: "Solo administración puede consultar evaluaciones" }, { status: 403 });
  try {
    const [raw, local] = await Promise.all([
      readFile(path.join(process.cwd(), "data/evaluation-latest.json"), "utf8"),
      readFile(path.join(process.cwd(), "data/detector-regression-latest.json"), "utf8").catch(error => {
        if (error.code === "ENOENT") return null;
        throw error;
      }),
    ]);
    const report = JSON.parse(raw);
    return Response.json({ ...report, local_regression: local ? JSON.parse(local) : null, installed_library_version: library.version }, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (error.code === "ENOENT") return Response.json({ error: "Todavía no hay una evaluación publicada" }, { status: 404 });
    return Response.json({ error: "No se pudo leer la evaluación" }, { status: 503 });
  }
}
