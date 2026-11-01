export class ApiFailure extends Error {
  constructor(message: string, public requestId?: string) {super(message);}
}

export async function request<T>(path: string, body?: unknown, signal?: AbortSignal, options?:{accessToken?:string; method?:'DELETE'}): Promise<T> {
  const headers:Record<string,string> = {};
  if (body !== undefined) headers['Content-Type']='application/json';
  if (options?.accessToken) headers.Authorization=`Bearer ${options.accessToken}`;
  const response = await fetch((import.meta.env.VITE_API_BASE_URL || "") + path, {
    method: options?.method ?? (body === undefined ? 'GET' : 'POST'),
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error: unknown = await response.json().catch(() => null);
    if (error && typeof error === 'object' && 'error' in error) {
      const detail = error.error as {message?: string; request_id?: string};
      throw new ApiFailure(detail.message || 'The request could not be completed.', detail.request_id);
    }
    throw new ApiFailure('The service could not be reached. Please try again.');
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.';
}
