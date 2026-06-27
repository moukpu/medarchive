const BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}
async function patch<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export interface Service { service_id: string; service_name: string; category?: string; }
export interface Partner { partner_id: string; name: string; city?: string; contact_phone?: string; contact_email?: string; address?: string; }
export interface PartnerWithPrice { partner: Partner; price_resident_kzt?: number; price_nonresident_kzt?: number; effective_date?: string; item_id: string; }
export interface ServiceWithPrice { item_id: string; service_name_raw: string; service_id?: string; service_name?: string; price_resident_kzt?: number; price_nonresident_kzt?: number; effective_date?: string; is_active: boolean; }
export interface SearchItem {
  item_id: string; service_name_raw: string; service_id?: string;
  partner_id: string; partner_name: string; city?: string;
  price_resident_kzt?: number; price_nonresident_kzt?: number; effective_date?: string;
}
export interface Unmatched { item_id: string; service_name_raw: string; partner_id: string; match_score?: number; suggestions: Service[]; }
export interface Dashboard { documents_total: number; documents_by_status: Record<string, number>; items_total: number; items_matched: number; items_unmatched: number; items_needs_review: number; auto_match_rate: number; }
export interface DocumentStatus { doc_id: string; file_name: string; file_format: string; parse_status: string; effective_date?: string; parsed_at?: string; }
export interface ReviewItem {
  item_id: string; service_name_raw: string; partner_id: string; partner_name?: string;
  doc_id: string; file_name?: string; effective_date?: string;
  service_id?: string; service_name?: string;
  price_resident_kzt?: number; price_nonresident_kzt?: number;
  match_score?: number; match_method: string; is_verified: boolean;
  reasons: string[]; suggestions: Service[];
}
export interface ItemContext {
  item_id: string; service_name_raw: string; doc_id: string; file_name?: string;
  file_format?: string; effective_date?: string; parse_log?: string; raw_snippet?: string;
}
export interface ItemUpdate { service_id?: string; price_resident_kzt?: number; price_nonresident_kzt?: number; note?: string; }

export const api = {
  services: (category?: string) => get<Service[]>(`/services${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  servicePartners: (id: string) => get<PartnerWithPrice[]>(`/services/${id}/partners`),
  partners: () => get<Partner[]>(`/partners`),
  partnerServices: (id: string, includeInactive = false) =>
    get<ServiceWithPrice[]>(`/partners/${id}/services${includeInactive ? "?include_inactive=true" : ""}`),
  search: (q: string) => get<{ services: Service[]; partners: Partner[]; items: SearchItem[] }>(`/search?q=${encodeURIComponent(q)}`),
  unmatched: () => get<Unmatched[]>(`/unmatched`),
  match: (item_id: string, service_id: string, note?: string) => post(`/match`, { item_id, service_id, note }),
  review: () => get<ReviewItem[]>(`/review`),
  itemContext: (item_id: string) => get<ItemContext>(`/items/${item_id}/context`),
  approveItem: (item_id: string) => post<ReviewItem>(`/items/${item_id}/approve`),
  updateItem: (item_id: string, patchBody: ItemUpdate) => patch<ReviewItem>(`/items/${item_id}`, patchBody),
  status: () => get<DocumentStatus[]>(`/admin/status`),
  dashboard: () => get<Dashboard>(`/admin/dashboard`),
  uploadArchive: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(BASE + "/admin/upload", { method: "POST", body: fd });
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  },
  clearDb: () => post<{status: string}>(`/admin/clear-db`),
};
