import crypto from "node:crypto";

export const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
  Pragma: "no-cache",
  Expires: "0",
} as const;

export type StreamDeckAuthResult =
  | { ok: true }
  | { ok: false; status: 401 | 503; error: string };

export function authorizeStreamDeckRequest(
  headers: Headers,
  expectedToken = process.env.STREAMDECK_READ_TOKEN
): StreamDeckAuthResult {
  if (!expectedToken) {
    return { ok: false, status: 503, error: "STREAMDECK_READ_TOKEN is not configured" };
  }

  const rawAuthorization = headers.get("authorization");
  if (!rawAuthorization) {
    return { ok: false, status: 401, error: "Missing Authorization header" };
  }

  const [scheme, providedToken] = rawAuthorization.trim().split(/\s+/, 2);
  if (scheme !== "Bearer" || !providedToken) {
    return { ok: false, status: 401, error: "Expected Bearer token" };
  }

  const expectedBuffer = Buffer.from(expectedToken);
  const providedBuffer = Buffer.from(providedToken);
  if (
    expectedBuffer.length !== providedBuffer.length ||
    !crypto.timingSafeEqual(expectedBuffer, providedBuffer)
  ) {
    return { ok: false, status: 401, error: "Invalid token" };
  }

  return { ok: true };
}
