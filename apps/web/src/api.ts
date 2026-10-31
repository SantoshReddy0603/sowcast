export class ApiFailure extends Error {
  constructor(message: string, public requestId?: string) {super(message);}
}

export async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch((import.meta.env.VITE_API_BASE_URL || "") + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : {'Content-Type': 'application/json'},
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
  return response.json() as Promise<T>;
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.';
}
