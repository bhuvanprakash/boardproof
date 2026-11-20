import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Context = { params: Promise<{ path: string[] }> };

function allowed(path: string[], method: string): boolean {
  const safe = (name: string) => !!name && ![".", ".."].includes(name) && !/[\\/]/.test(name);
  if (path.length === 1 && ["state", "previews", "datasheets"].includes(path[0])) return method === "GET";
  if (path.length === 1 && ["upload", "run"].includes(path[0])) return method === "POST";
  if (path.length === 2 && ["artifacts", "previews"].includes(path[0])) return method === "GET" && safe(path[1]);
  if (path.length === 2 && path[0] === "datasheets" && ["fetch", "verify", "verify-all"].includes(path[1])) {
    return method === "POST";
  }
  // /api/datasheets/pdf/{part} — part numbers are slugified upstream; guard anyway.
  return path.length === 3 && path[0] === "datasheets" && path[1] === "pdf"
    && method === "GET" && safe(path[2]);
}

async function proxy(request: NextRequest, context: Context) {
  const { path } = await context.params;
  if (!allowed(path, request.method)) return Response.json({ detail: "not found" }, { status: 404 });

  const origin = process.env.BOARDPROOF_API_URL ?? "http://127.0.0.1:8193";
  const url = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, origin);
  url.search = request.nextUrl.search;
  const headers = new Headers({ Accept: "application/json" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const token = process.env.BOARDPROOF_API_TOKEN;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let body: ArrayBuffer | undefined;
  if (request.method === "POST") {
    body = await request.arrayBuffer();
    if (body.byteLength > 12 * 1024 * 1024) {
      return Response.json({ detail: "request body too large" }, { status: 413 });
    }
  }

  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "content-disposition", "cache-control", "content-security-policy", "x-content-type-options"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json({ detail: "BoardProof API is unavailable" }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
