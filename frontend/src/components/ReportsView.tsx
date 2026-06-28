import { useEffect, useMemo, useState } from "react";
import {
  ChartLineUp,
  CheckCircle,
  WarningCircle,
  Clock,
  Buildings,
  Files,
  TrendUp,
} from "@phosphor-icons/react";
import { api, type Dashboard, type DocumentStatus, type Partner } from "../api";
import { Card, EmptyState, LoadingBlock, PageHeader, SectionTitle, StatusPill } from "./ui";

const STATUS_LABELS: Record<string, { label: string; tone: "success" | "warning" | "danger" | "primary" | "neutral" }> = {
  done: { label: "Готово", tone: "success" },
  processing: { label: "Обработка", tone: "primary" },
  pending: { label: "В очереди", tone: "neutral" },
  needs_review: { label: "На проверке", tone: "warning" },
  error: { label: "Ошибка", tone: "danger" },
};

export function ReportsView() {
  const [d, setD] = useState<Dashboard | null>(null);
  const [docs, setDocs] = useState<DocumentStatus[] | null>(null);
  const [partners, setPartners] = useState<Partner[] | null>(null);

  useEffect(() => {
    api.dashboard().then(setD).catch(() => setD(null));
    api.status().then(setDocs).catch(() => setDocs([]));
    api.partners().then(setPartners).catch(() => setPartners([]));
  }, []);

  const partnerCounts = useMemo(() => {
    if (!docs || !partners) return [];
    const ids = new Set(partners.map((p) => p.partner_id));
    const counts = new Map<string, number>();
    for (const doc of docs) {
      const anyDoc = doc as DocumentStatus & { partner_id?: string };
      if (anyDoc.partner_id && ids.has(anyDoc.partner_id)) {
        counts.set(anyDoc.partner_id, (counts.get(anyDoc.partner_id) ?? 0) + 1);
      }
    }
    return partners
      .map((p) => ({ partner: p, count: counts.get(p.partner_id) ?? 0 }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
  }, [docs, partners]);

  if (!d) {
    return (
      <>
        <PageHeader title="Отчёты" description="Аналитика обработки прайс-листов и качества автоматического сопоставления." />
        <LoadingBlock label="Считаем метрики…" />
      </>
    );
  }

  const statusEntries = Object.entries(d.documents_by_status ?? {});
  const totalDocs = statusEntries.reduce((sum, [, n]) => sum + n, 0) || 1;
  const matchRate = d.auto_match_rate ?? 0;
  const matchedShare = d.items_total > 0 ? Math.round((d.items_matched / d.items_total) * 100) : 0;
  const reviewShare = d.items_total > 0 ? Math.round((d.items_needs_review / d.items_total) * 100) : 0;
  const unmatchedShare = d.items_total > 0 ? Math.round((d.items_unmatched / d.items_total) * 100) : 0;

  return (
    <>
      <PageHeader
        title="Отчёты"
        description="Аналитика обработки прайс-листов и качества автоматического сопоставления."
      />

      <div className="mb-8 grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
        <KpiCard icon={<TrendUp size={20} weight="duotone" />} value={`${matchRate.toFixed(1)}%`} label="Автомэтчинг" hint="Доля позиций, привязанных к справочнику без ручной правки." accent />
        <KpiCard icon={<Files size={20} weight="duotone" />} value={d.documents_total.toLocaleString("ru-RU")} label="Документов всего" />
        <KpiCard icon={<CheckCircle size={20} weight="duotone" />} value={d.items_total.toLocaleString("ru-RU")} label="Позиций в архиве" />
        <KpiCard icon={<WarningCircle size={20} weight="duotone" />} value={(d.items_needs_review + d.items_unmatched).toLocaleString("ru-RU")} label="Ждут проверки" />
      </div>

      <Card className="mb-8">
        <SectionTitle action={<span className="text-xs font-semibold uppercase tracking-wider text-ink-faint">{d.items_total.toLocaleString("ru-RU")} позиций</span>}>
          Качество сопоставления
        </SectionTitle>

        <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-low">
          <span className="h-full bg-success-600 transition-all duration-700" style={{ width: `${matchedShare}%` }} aria-label={`Сопоставлено ${matchedShare}%`} />
          <span className="h-full bg-warning-600 transition-all duration-700" style={{ width: `${reviewShare}%` }} aria-label={`На проверке ${reviewShare}%`} />
          <span className="h-full bg-danger-600 transition-all duration-700" style={{ width: `${unmatchedShare}%` }} aria-label={`Не сопоставлено ${unmatchedShare}%`} />
        </div>

        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Legend dotClass="bg-success-600" label="Сопоставлено" count={d.items_matched} share={matchedShare} />
          <Legend dotClass="bg-warning-600" label="На проверке" count={d.items_needs_review} share={reviewShare} />
          <Legend dotClass="bg-danger-600" label="Не сопоставлено" count={d.items_unmatched} share={unmatchedShare} />
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <SectionTitle action={<ChartLineUp size={18} className="text-ink-faint" />}>Документы по статусам</SectionTitle>

          {statusEntries.length === 0 ? (
            <EmptyState icon={<Clock size={24} />} title="Нет данных" description="Загрузите архив прайс-листов на странице «Дашборд», чтобы появились метрики." />
          ) : (
            <ul className="space-y-3">
              {statusEntries.map(([status, count]) => {
                const cfg = STATUS_LABELS[status] ?? { label: status, tone: "neutral" as const };
                const pct = Math.round((count / totalDocs) * 100);
                return (
                  <li key={status} className="flex items-center gap-4">
                    <StatusPill tone={cfg.tone}>{cfg.label}</StatusPill>
                    <div className="flex-1">
                      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-low">
                        <span
                          className={`block h-full transition-all duration-700 ${
                            cfg.tone === "success"
                              ? "bg-success-600"
                              : cfg.tone === "warning"
                              ? "bg-warning-600"
                              : cfg.tone === "danger"
                              ? "bg-danger-600"
                              : cfg.tone === "primary"
                              ? "bg-primary-500"
                              : "bg-brand-blue-soft"
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                    <span className="w-16 text-right text-sm font-semibold text-ink-strong tabular-nums">{count}</span>
                    <span className="w-12 text-right text-xs text-ink-faint tabular-nums">{pct}%</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card>
          <SectionTitle action={<Buildings size={18} className="text-ink-faint" />}>Топ партнёров по документам</SectionTitle>

          {partnerCounts.length === 0 ? (
            <EmptyState icon={<Buildings size={24} />} title="Партнёров пока нет" description="Партнёры появятся после первой успешной обработки прайса." />
          ) : (
            <ul className="space-y-3">
              {partnerCounts.map(({ partner, count }, i) => {
                const max = partnerCounts[0].count || 1;
                const pct = Math.round((count / max) * 100);
                return (
                  <li key={partner.partner_id} className="flex items-center gap-4">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-low text-xs font-bold text-ink-muted">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-ink-strong">{partner.name}</p>
                      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-low">
                        <span className="block h-full bg-brand-red transition-all duration-700" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                    <span className="w-12 text-right text-sm font-semibold text-ink-strong tabular-nums">{count}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

function KpiCard({
  icon,
  value,
  label,
  hint,
  accent = false,
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <Card padded={false} className="flex items-start gap-4 p-5">
      <span
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${
          accent ? "bg-brand-red text-white" : "bg-surface-low text-brand-red"
        }`}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-bold leading-tight text-ink-strong tabular-nums">{value}</p>
        <p className="mt-0.5 text-xs font-semibold uppercase tracking-wider text-ink-faint">{label}</p>
        {hint && <p className="mt-2 text-[11px] leading-snug text-ink-faint">{hint}</p>}
      </div>
    </Card>
  );
}

function Legend({ dotClass, label, count, share }: { dotClass: string; label: string; count: number; share: number }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      <div className="flex-1 text-sm">
        <p className="font-semibold text-ink-strong">{label}</p>
        <p className="text-xs text-ink-faint tabular-nums">{count.toLocaleString("ru-RU")} · {share}%</p>
      </div>
    </div>
  );
}
