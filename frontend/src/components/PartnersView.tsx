import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft, Buildings, MapPin, Phone, EnvelopeSimple, WarningCircle,
  CalendarBlank, CaretDown, Archive, CheckCircle, CaretRight,
} from "@phosphor-icons/react";
import { api, type Partner, type ServiceWithPrice } from "../api";
import { Badge, Button, Card, EmptyState, PageHeader, SkeletonRow } from "./ui";
import { formatKzt, formatDate } from "../format";

interface ClinicGroup {
  name: string;
  partners: Partner[];
}

function normalizeClinicName(name: string): string {
  return name
    .replace(/\b(20\d{2})\b/g, "")
    .replace(/\b(прайс|price|год|year|лист|list)\b/gi, "")
    .replace(/[_\-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function groupClinicsByName(partners: Partner[]): ClinicGroup[] {
  const map = new Map<string, Partner[]>();
  const displayNames = new Map<string, string>();
  for (const p of partners) {
    const key = normalizeClinicName(p.name);
    const arr = map.get(key);
    if (arr) arr.push(p);
    else {
      map.set(key, [p]);
      displayNames.set(key, p.name.replace(/\b(20\d{2})\b/g, "").replace(/\b(прайс|price|год|year|лист|list)\b/gi, "").replace(/\s+/g, " ").trim());
    }
  }
  return [...map.entries()].map(([key, partners]) => ({
    name: displayNames.get(key) || partners[0].name,
    partners,
  }));
}

interface DateGroup {
  key: string;
  date?: string;
  hasActive: boolean;
  matched: ServiceWithPrice[];
  unmatched: ServiceWithPrice[];
}

function groupByDate(services: ServiceWithPrice[]): DateGroup[] {
  const map = new Map<string, DateGroup>();
  for (const s of services) {
    const key = s.effective_date ?? "—";
    let g = map.get(key);
    if (!g) {
      g = { key, date: s.effective_date, hasActive: false, matched: [], unmatched: [] };
      map.set(key, g);
    }
    if (s.service_id) g.matched.push(s);
    else g.unmatched.push(s);
    if (s.is_active) g.hasActive = true;
  }
  return [...map.values()].sort((a, b) => {
    if (!a.date) return 1;
    if (!b.date) return -1;
    return a.date < b.date ? 1 : -1;
  });
}

function ServiceTable({ items, tone }: { items: ServiceWithPrice[]; tone?: "warning" }) {
  if (items.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-subtle bg-surface-low text-left text-xs font-semibold uppercase tracking-wide text-ink-faint">
            <th className="px-5 py-3">Услуга</th>
            <th className="px-5 py-3 text-right">Резидент</th>
            <th className="px-5 py-3 text-right">Нерезидент</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.item_id} className="border-b border-border-subtle last:border-b-0 hover:bg-surface-low/60">
              <td className="px-5 py-3.5">
                <span className="font-medium text-ink">{s.service_name || s.service_name_raw}</span>
                {tone === "warning" && (
                  <Badge tone="warning" className="ml-2">
                    <WarningCircle size={12} /> не сопоставлено
                  </Badge>
                )}
              </td>
              <td className="px-5 py-3.5 text-right font-semibold text-ink">{formatKzt(s.price_resident_kzt)}</td>
              <td className="px-5 py-3.5 text-right text-ink-muted">{formatKzt(s.price_nonresident_kzt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DateSection({ group, defaultOpen }: { group: DateGroup; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const total = group.matched.length + group.unmatched.length;

  return (
    <Card padded={false} className="overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left hover:bg-surface-low/60"
      >
        <span className="flex items-center gap-2.5">
          <CalendarBlank size={18} className="text-brand-red" />
          <span className="font-semibold text-ink">{formatDate(group.date)}</span>
          {!group.hasActive && (
            <Badge tone="neutral"><Archive size={12} /> архив</Badge>
          )}
          <span className="text-xs text-ink-faint">· {total} поз.</span>
          {group.unmatched.length > 0 && (
            <Badge tone="warning">{group.unmatched.length} без сопоставления</Badge>
          )}
        </span>
        <CaretDown size={16} className={`shrink-0 text-ink-faint transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="border-t border-border-subtle">
          {group.matched.length > 0 && (
            <div>
              <div className="flex items-center gap-2 bg-green-50/50 px-5 py-2 text-xs font-semibold text-green-700">
                <CheckCircle size={14} weight="fill" /> Нормализованные ({group.matched.length})
              </div>
              <ServiceTable items={group.matched} />
            </div>
          )}
          {group.unmatched.length > 0 && (
            <div>
              <div className="flex items-center gap-2 bg-amber-50/50 px-5 py-2 text-xs font-semibold text-amber-700">
                <WarningCircle size={14} /> Требуют верификации ({group.unmatched.length})
              </div>
              <ServiceTable items={group.unmatched} tone="warning" />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function PartnerDetail({ partner, onBack }: { partner: Partner; onBack: () => void }) {
  const [services, setServices] = useState<ServiceWithPrice[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.partnerServices(partner.partner_id, true)
      .then(setServices)
      .finally(() => setLoading(false));
  }, [partner.partner_id]);

  const groups = useMemo(() => groupByDate(services), [services]);

  return (
    <div className="animate-fade-in">
      <Button variant="ghost" size="sm" icon={<ArrowLeft size={16} />} onClick={onBack} className="mb-4 -ml-2">
        Назад к партнёрам
      </Button>

      <Card className="mb-6">
        <div className="flex items-start gap-4">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-surface-low text-brand-red">
            <Buildings size={22} />
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-ink">{partner.name}</h2>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-ink-muted">
              {partner.city && (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin size={15} /> {[partner.city, partner.address].filter(Boolean).join(", ")}
                </span>
              )}
              {partner.contact_phone && (
                <span className="inline-flex items-center gap-1.5">
                  <Phone size={15} /> {partner.contact_phone}
                </span>
              )}
              {partner.contact_email && (
                <span className="inline-flex items-center gap-1.5">
                  <EnvelopeSimple size={15} /> {partner.contact_email}
                </span>
              )}
            </div>
          </div>
        </div>
      </Card>

      {loading ? (
        <div className="space-y-3">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : groups.length === 0 ? (
        <EmptyState title="Прайс-лист пуст" description="Для этого партнёра пока не загружено ни одной позиции." />
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-ink-muted">Прайс-листы по датам — новейшие сверху, архивные версии помечены.</p>
          {groups.map((g, i) => (
            <DateSection key={g.key} group={g} defaultOpen={i === 0} />
          ))}
        </div>
      )}
    </div>
  );
}

function ClinicCard({ group, onSelectPartner }: { group: ClinicGroup; onSelectPartner: (p: Partner) => void }) {
  const [expanded, setExpanded] = useState(false);
  const single = group.partners.length === 1;

  if (single) {
    const p = group.partners[0];
    return (
      <Card padded={false} className="cursor-pointer p-4 hover:border-brand-red">
        <button onClick={() => onSelectPartner(p)} className="flex w-full cursor-pointer items-start gap-3 text-left">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-low text-brand-red">
            <Buildings size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold text-ink">{p.name}</p>
            {p.city && (
              <p className="mt-0.5 flex items-center gap-1 text-xs text-ink-muted">
                <MapPin size={13} /> {p.city}
              </p>
            )}
          </div>
        </button>
      </Card>
    );
  }

  return (
    <Card padded={false} className="overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full cursor-pointer items-center gap-3 p-4 text-left hover:bg-surface-low/60"
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-low text-brand-red">
          <Buildings size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate font-semibold text-ink">{group.name}</p>
            <Badge tone="neutral">{group.partners.length} прайса</Badge>
          </div>
          {group.partners[0].city && (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-ink-muted">
              <MapPin size={13} /> {group.partners[0].city}
            </p>
          )}
        </div>
        <CaretDown size={16} className={`shrink-0 text-ink-faint transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
      </button>
      {expanded && (
        <div className="border-t border-border-subtle">
          {group.partners.map((p) => (
            <button
              key={p.partner_id}
              onClick={() => onSelectPartner(p)}
              className="flex w-full cursor-pointer items-center gap-3 border-b border-border-subtle px-6 py-3 text-left last:border-b-0 hover:bg-surface-low/60"
            >
              <CalendarBlank size={16} className="shrink-0 text-ink-faint" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{p.name}</p>
                {p.city && (
                  <p className="text-xs text-ink-faint">{[p.city, p.address].filter(Boolean).join(", ")}</p>
                )}
              </div>
              <CaretRight size={14} className="shrink-0 text-ink-faint" />
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}

export function PartnersView() {
  const [partners, setPartners] = useState<Partner[] | null>(null);
  const [selected, setSelected] = useState<Partner | null>(null);

  useEffect(() => {
    api.partners().then(setPartners).catch(() => setPartners([]));
  }, []);

  const clinicGroups = useMemo(() => {
    if (!partners) return [];
    return groupClinicsByName(partners);
  }, [partners]);

  if (selected) {
    return <PartnerDetail partner={selected} onBack={() => setSelected(null)} />;
  }

  return (
    <div>
      <PageHeader title="Партнёры" description="Клиники, чьи прайс-листы загружены и обработаны в системе." />
      {partners === null ? (
        <div className="space-y-3">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : clinicGroups.length === 0 ? (
        <EmptyState
          icon={<Buildings size={24} />}
          title="Партнёров пока нет"
          description="Загрузите ZIP-архив с прайс-листами на странице «Дашборд», чтобы он появился здесь."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {clinicGroups.map((g) => (
            <ClinicCard key={g.name} group={g} onSelectPartner={setSelected} />
          ))}
        </div>
      )}
    </div>
  );
}
