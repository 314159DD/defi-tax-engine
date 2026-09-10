/**
 * Next.js API route proxy for /api/chains/*
 *
 * Proxies chain API requests to the Railway backend so the frontend
 * can be deployed to Vercel without CORS issues.
 *
 * Examples:
 *   /api/chains/evm/ethereum/0x123...  →  BACKEND_URL/api/chains/evm/ethereum/0x123...
 *   /api/chains/bitcoin/bc1q...        →  BACKEND_URL/api/chains/bitcoin/bc1q...
 *   /api/chains/prices?ids=bitcoin     →  BACKEND_URL/api/chains/prices?ids=bitcoin
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || process.env.BACKEND_URL || 'http://localhost:8000';

async function proxyRequest(request: Request, params: Promise<{ path: string[] }>) {
  const { path } = await params;
  const pathStr = path.join('/');
  const url = new URL(request.url);
  const search = url.search; // preserve query params

  const backendUrl = `${BACKEND_URL}/api/chains/${pathStr}${search}`;

  // Forward the Authorization header
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  const auth = request.headers.get('Authorization');
  if (auth) {
    headers['Authorization'] = auth;
  }

  try {
    const resp = await fetch(backendUrl, {
      method: request.method,
      headers,
      // Don't forward body for GET/HEAD
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.text(),
    });

    const data = await resp.text();

    return new Response(data, {
      status: resp.status,
      headers: {
        'Content-Type': resp.headers.get('Content-Type') || 'application/json',
      },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: 'Failed to proxy request to backend', detail: String(error) }),
      { status: 502, headers: { 'Content-Type': 'application/json' } },
    );
  }
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context.params);
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context.params);
}
