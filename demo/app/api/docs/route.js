/** La fuente de conocimientos de Shop se consulta exclusivamente mediante MCP. */
export async function GET() {
  return Response.json(
    { error: "La consulta directa de documentos está desactivada. Consulta la información desde el chat.", code: "DOCUMENT_VIEWER_DISABLED" },
    { status: 410, headers: { "Cache-Control": "no-store" } }
  );
}
