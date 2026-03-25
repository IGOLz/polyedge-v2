import test from "node:test";
import assert from "node:assert/strict";

import { authorizeStreamDeckRequest } from "../lib/streamdeck-auth";

test("rejects requests when token is not configured", () => {
  const result = authorizeStreamDeckRequest(new Headers(), undefined);

  assert.deepEqual(result, {
    ok: false,
    status: 503,
    error: "STREAMDECK_READ_TOKEN is not configured",
  });
});

test("rejects requests without authorization header", () => {
  const result = authorizeStreamDeckRequest(new Headers(), "secret");

  assert.deepEqual(result, {
    ok: false,
    status: 401,
    error: "Missing Authorization header",
  });
});

test("rejects malformed bearer headers", () => {
  const headers = new Headers({
    authorization: "Basic abc123",
  });

  const result = authorizeStreamDeckRequest(headers, "secret");
  assert.deepEqual(result, {
    ok: false,
    status: 401,
    error: "Expected Bearer token",
  });
});

test("rejects invalid tokens", () => {
  const headers = new Headers({
    authorization: "Bearer wrong-token",
  });

  const result = authorizeStreamDeckRequest(headers, "secret-token");
  assert.deepEqual(result, {
    ok: false,
    status: 401,
    error: "Invalid token",
  });
});

test("accepts valid bearer token", () => {
  const headers = new Headers({
    authorization: "Bearer secret-token",
  });

  const result = authorizeStreamDeckRequest(headers, "secret-token");
  assert.deepEqual(result, { ok: true });
});
