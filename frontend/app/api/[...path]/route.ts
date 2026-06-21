const configuredApiBase = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';
const API_BASE_URL = configuredApiBase.includes('://')
  ? configuredApiBase
  : `http://${configuredApiBase}`;
const PROTECTED = new Set(['/predict', '/check', '/extract', '/schema']);
const ALLOWED = new Set([...PROTECTED, '/health']);

type Context = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: Request, { params }: Context) {
  const { path: parts } = await params;
  const path = `/${parts.join('/')}`;
  if (!ALLOWED.has(path)) {
    return Response.json({ detail: 'Not found' }, { status: 404 });
  }

  const incoming = new URL(request.url);
  const target = new URL(path, API_BASE_URL);
  target.search = incoming.search;

  const headers = new Headers();
  const contentType = request.headers.get('content-type');
  if (contentType) {
    headers.set('content-type', contentType);
  }
  if (PROTECTED.has(path) && process.env.CIVICFLOW_API_KEY) {
    headers.set('X-API-Key', process.env.CIVICFLOW_API_KEY);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: 'no-store',
  };
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get('content-type');
  const requestId = upstream.headers.get('x-request-id');
  if (upstreamContentType) {
    responseHeaders.set('content-type', upstreamContentType);
  }
  if (requestId) {
    responseHeaders.set('x-request-id', requestId);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}

export { proxy as GET, proxy as POST };
