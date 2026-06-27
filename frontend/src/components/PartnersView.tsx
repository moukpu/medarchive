import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Buildings, MapPin, Phone, EnvelopeSimple, WarningCircle, CalendarBlank, CaretDown, Archive } from "@phosphor-icons/react";
import { api, type Partner, type ServiceWithPrice } from "../api";
import { Badge, Button, Card, EmptyState, PageHeader, SkeletonRow } from "./ui";
import { formatKzt, formatDate } from "../format";

interface DateGroup {
  key: string;
  date?: string;
  hasActive: boolean;
  items: ServiceWithPrice[];
}

function groupByDate(services: ServiceWithPrice[]): DateGroup[] {
  const map = new Map<string, DateGroup>();
  for (const s of services) {
    const key = s.effective_date ?? "—";
    let g = map.get(key);
    if (!g) {
      g = { key, date: s.effective_date, hasActive: false, items: [] };
      map.set(key, g);
    }
    g.items.push(s);
    if (s.is_active) g.hasActive = true;
  }
  // новейшие даты сверху; «без даты» в конце
  return [...map.values()].sort((a, b) => {
    if (!a.date) return 1;
    if (!b.date) return -1;
    return a.date < b.date ? 1 : -1;
  });
}

function ServiceTable({ items }: { items: ServiceWithPrice[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line bg-canvas text-left text-xs font-semibold uppercase tracking-wide text-ink-faint">
            <th className="px-5 py-3">Услуга</th>
            <th className="px-5 py-3 text-right">Резидент</th>
            <th className="px-5 py-3 text-right">Нерезидент</th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.item_id} className="border-b border-line last:border-0 hover:bg-canvas/60">
              <td className="px-5 py-3.5">
                <span className="font-medium text-ink">{s.service_name || s.service_name_raw}</span>
                {!s.service_id && (
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
  return (
    <Card padded={false} className="overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-5 py-3.5 text-left hover:bg-canvas/60"
      >
        <span className="flex items-center gap-2.5">
          <CalendarBlank size={18} className="text-primary-600" />
          <span className="font-semibold text-ink">{formatDate(group.date)}</span>
          {!group.hasActive && (
            <Badge tone="neutral">
              <Archive size={12} /> архив
            </Badge>
          )}
          <span className="text-xs text-ink-faint">· {group.items.length} поз.</span>
        </span>
        <CaretDown size={16} className={`shrink-0 text-ink-faint transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="border-t border-line">
          <ServiceTable items={group.items} />
        </div>
      )}
    </Card>
  );
}

export function PartnersView() {
  const [partners, setPartners] = useState<Partner[] | null>(null);
  const [selected, setSelected] = useState<Partner | null>(null);
  const [services, setServices] = useState<ServiceWithPrice[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    api.partners().then(setPartners).catch(() => setPartners([]));
  }, []);

  const groups = useMemo(() => groupByDate(services), [services]);

  const open = async (p: Partner) => {
    setSelected(p);
    setDetailLoading(true);
    setServices([]);
    try {
      setServices(await api.partnerServices(p.partner_id, true));
    } finally {
      setDetailLoading(false);
    }
  };

  if (selected) {
    return (
      <div className="animate-fade-in">
        <Button variant="ghost" size="sm" icon={<ArrowLeft size={16} />} onClick={() => setSelected(null)} className="mb-4 -ml-2">
          Назад к партнёрам
        </Button>

        <Card className="mb-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary-500/15 text-primary-400 ring-1 ring-primary-500/20">
              <Buildings size={22} />
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-bold text-ink">{selected.name}</h2>
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5 text-sm text-ink-muted">
                {selected.city && (
                  <span className="inline-flex items-center gap-1.5">
                    <MapPin size={15} /> {[selected.city, selected.address].filter(Boolean).join(", ")}
                  </span>
                )}
                {selected.contact_phone && (
                  <span className="inline-flex items-center gap-1.5">
                    <Phone size={15} /> {selected.contact_phone}
                  </span>
                )}
                {selected.contact_email && (
                  <span className="inline-flex items-center gap-1.5">
                    <EnvelopeSimple size={15} /> {selected.contact_email}
                  </span>
                )}
              </div>
            </div>
          </div>
        </Card>

        {detailLoading ? (
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

  return (
    <div>
      <PageHeader title="Партнёры" description="Клиники, чьи прайс-листы загружены и обработаны в системе." />
      {partners === null ? (
        <div className="space-y-3">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : partners.length === 0 ? (
        <EmptyState
          icon={<Buildings size={24} />}
          title="Партнёров пока нет"
          description="Загрузите ZIP-архив с прайс-листами на странице «Дашборд», чтобы он появился здесь."
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {partners.map((p) => (
            <Card key={p.partner_id} padded={false} className="cursor-pointer p-4 hover:border-primary-500/40 hover:bg-white/[0.02]">
              <button onClick={() => open(p)} className="flex w-full cursor-pointer items-start gap-3 text-left">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-500/15 text-primary-400 ring-1 ring-primary-500/20">
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
          ))}
        </div>
      )}
    </div>
  );
}
