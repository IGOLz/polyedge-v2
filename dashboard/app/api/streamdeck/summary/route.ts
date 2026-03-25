export const dynamic = "force-dynamic";
export const revalidate = 0;

import { NextResponse } from "next/server";

import { NO_STORE_HEADERS, authorizeStreamDeckRequest } from "@/lib/streamdeck-auth";
import { getStreamDeckSummary } from "@/lib/streamdeck-summary";

function unauthorized(message: string, status = 401) {
  return NextResponse.json({ error: message }, { status, headers: NO_STORE_HEADERS });
}

export async function GET(request: Request) {
  const auth = authorizeStreamDeckRequest(request.headers);
  if (!auth.ok) {
    return unauthorized(auth.error, auth.status);
  }

  const summary = await getStreamDeckSummary();
  return NextResponse.json(summary, {
    headers: NO_STORE_HEADERS,
  });
}
