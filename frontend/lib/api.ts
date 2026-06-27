import type {
  PermitData,
  PredictResponse,
  CheckResponse,
  ExtractResponse,
  HealthResponse,
  SchemaResponse,
} from '@/lib/types';

/** HTTP error with status code for caller branching */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const BASE = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    // Read body once; a second read throws "body already read"
    const text = await res.text();
    let detail = text;
    try {
      const body = JSON.parse(text);
      detail = body.detail ?? text;
    } catch {
      // Non-JSON error body; keep the raw text
    }
    throw new ApiError(detail || `${res.status} ${res.statusText}`, res.status);
  }
  return res.json() as Promise<T>;
}

export async function extractPermit(plans: File[]): Promise<ExtractResponse> {
  const form = new FormData();
  for (const file of plans) {
    form.append('plans', file);
  }
  const res = await fetch(`${BASE}/extract`, {
    method: 'POST',
    body: form,
    signal: AbortSignal.timeout(90_000),
  });
  return handleResponse<ExtractResponse>(res);
}

export async function predict(permit: PermitData): Promise<PredictResponse> {
  const res = await fetch(`${BASE}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(permit),
    signal: AbortSignal.timeout(30_000),
  });
  return handleResponse<PredictResponse>(res);
}

export async function checkPermit(
  permit: PermitData,
  plans?: File[],
): Promise<CheckResponse> {
  const form = new FormData();
  form.append('permit', JSON.stringify(permit));
  if (plans?.length) {
    for (const file of plans) {
      form.append('plans', file);
    }
  }
  const res = await fetch(`${BASE}/check`, {
    method: 'POST',
    body: form,
    signal: AbortSignal.timeout(90_000),
  });
  return handleResponse<CheckResponse>(res);
}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${BASE}/health`, { cache: 'no-store' });
  return handleResponse<HealthResponse>(res);
}

export async function getSchema(): Promise<SchemaResponse> {
  const res = await fetch(`${BASE}/schema`, { cache: 'no-store' });
  return handleResponse<SchemaResponse>(res);
}
