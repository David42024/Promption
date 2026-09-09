import { getFilterState } from "../../../lib/filter-state.js";

export async function GET() {
  const s = getFilterState();
  return Response.json({
    filterEnabled: s.filterEnabled,
    outputGuardEnabled: s.outputGuardEnabled,
  });
}
