import type {
  PushRequest,
  PopResponse,
  AcknowledgeRequest,
  DeadLetterRequest,
  DeadLetterResponse,
  ApiError,
  RegisterSinkRequest,
  RegisterSinkResponse,
} from '../types/queue';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002';

export class QueueApiError extends Error {
  constructor(public status: number | string, public data: unknown) {
    super('Queue API Error');
    this.name = 'QueueApiError';
  }
}

export const queueApi = {
  async push(queueId: string, request: PushRequest): Promise<void> {
    const response = await fetch(`${API_BASE}/queue/${queueId}/push`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new QueueApiError(response.status, data);
    }
  },

  async pop(queueId: string, count: number = 1): Promise<PopResponse | null> {
    const response = await fetch(`${API_BASE}/queue/${queueId}/pop`, {
      method: 'POST',
      headers: {
        'count': count.toString(),
      },
    });

    if (response.status === 204) {
      return null;
    }

    if (!response.ok) {
      const data = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new QueueApiError(response.status, data);
    }

    return response.json();
  },

  async popWithAck(queueId: string, count: number = 1, ttlSeconds: number = 30, allowCompeting: boolean = false): Promise<PopResponse | null> {
    const response = await fetch(`${API_BASE}/queue/${queueId}/pop`, {
      method: 'POST',
      headers: {
        'require_ack': 'true',
        'ttl_seconds': ttlSeconds.toString(),
        'allow_competing_consumers': allowCompeting.toString(),
        'count': count.toString(),
      },
    });

    if (response.status === 204) {
      return null;
    }

    if (!response.ok) {
      const data = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new QueueApiError(response.status, data);
    }

    return response.json();
  },

  async acknowledge(queueId: string, request: AcknowledgeRequest): Promise<void> {
    const response = await fetch(`${API_BASE}/queue/${queueId}/acknowledge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new QueueApiError(response.status, data);
    }
  },

  async deadLetter(queueId: string, request: DeadLetterRequest): Promise<DeadLetterResponse> {
    const response = await fetch(`${API_BASE}/queue/${queueId}/deadletter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new QueueApiError(response.status, data);
    }

    return response.json();
  },

  async registerSink(queueId: string, request: RegisterSinkRequest): Promise<RegisterSinkResponse> {
    const response = await fetch(`${API_BASE}/queue/${queueId}/sink/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new QueueApiError(response.status, data);
    }

    return response.json();
  },

  async unregisterSink(queueId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/queue/${queueId}/sink/unregister`, {
      method: 'POST',
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new QueueApiError(response.status, data);
    }
  },
};

export const createApiError = (status: number | string, data: unknown): ApiError => ({
  status,
  data,
});
