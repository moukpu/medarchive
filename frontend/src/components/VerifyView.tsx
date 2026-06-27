import { useEffect, useState } from "react";
import {
  CheckCircle,
  ClipboardText,
  SealCheck,
  PencilSimple,
  FileText,
  WarningCircle,
  Buildings,
  CalendarBlank,
  X,
} from "@phosphor-icons/react";
import { api, type ReviewItem, type ItemContext, type Service } from "../api";
import { Badge, Button, Card, EmptyState, Input, PageHeader, SkeletonRow, Spinner } from "./ui";
import { formatKzt, formatDate } from "../format";

const METHOD_LABEL: Record<string, string> = {
  exact: "точное", synonym: "синоним", fuzzy: "нечёткое", embedding: "семантика", manual: "вручную", none: "—",
};

function ReviewCard({ item, onResolved }: { item: ReviewItem; onResolved: (id: string) => void }) {
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [busy, setBusy] = useState(false);
  const [showCtx, setShowCtx] = useState(false);
  const [ctx, setCtx] = useState<ItemContext | null>(null);
  const [ctxLoading, setCtxLoading] = useState(false);

  const [serviceId, setServiceId] = useState<string | undefined>(item.service_id);
  const [resident, setResident] = useState(item.price_resident_kzt?.toString() ?? "");
  const [nonresident, setNonresident] = useState(item.price_nonresident_kzt?.toString() ?? "");
  const [note, setNote] = useState("");

  const toggleCtx = async () => {
    const next = !showCtx;
    setShowCtx(next);
    if (next && !ctx) {
      setCtxLoading(true);
      try {
        setCtx(await api.itemContext(item.item_id));
      } finally {
        setCtxLoading(false);
      }
    }
  };

  const approve = async () => {
    setBusy(true);
    try {
      await api.approveItem(item.item_id);
      onResolved(item.item_id);
    } finally {
      setBusy(false);
    }
  };

  const quickMatch = async (svc: Service) => {
    setBusy(true);
    try {
      await api.updateItem(item.item_id, { service_id: svc.service_id });
      onResolved(item.item_id);
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    setBusy(true);
    try {
      await api.updateItem(item.item_id, {
        service_id: serviceId,
        price_resident_kzt: resident === "" ? undefined : Number(resident),
        price_nonresident_kzt: nonresident === "" ? undefined : Number(nonresident),
        note: note || undefined,
      });
      onResolved(item.item_id);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="animate-fade-in">
      {/* Заголовок: сырое название + матч/score */}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <ClipboardText size={16} className="shrink-0 text-ink-faint" />
            <p className="font-semibold text-ink">{item.service_name_raw}</p>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
            {item.partner_name && (
              <span className="inline-flex items-center gap-1"><Buildings size={12} /> {item.partner_name}</span>
            )}
            {item.effective_date && (
              <span className="inline-flex items-center gap-1"><CalendarBlank size={12} /> {formatDate(item.effective_date)}</span>
            )}
            {item.file_name && (
              <span className="inline-flex items-center gap-1 truncate"><FileText size={12} /> {item.file_name}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {item.service_name ? (
            <Badge tone="success"><CheckCircle size={12} weight="fill" /> {item.service_name}</Badge>
          ) : (
            <Badge tone="warning"><WarningCircle size={12} /> не сопоставлено</Badge>
          )}
          <span className="text-[11px] text-ink-faint">
            score: {item.match_score != null ? item.match_score.toFixed(2) : "—"} · {METHOD_LABEL[item.match_method] ?? item.match_method}
          </span>
        </div>
      </div>

      {/* Причины ревью */}
      {item.reasons.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {item.reasons.map((r, i) => (
            <Badge key={i} tone="danger"><WarningCircle size={12} /> {r}</Badge>
          ))}
        </div>
      )}

      {/* Текущие цены */}
      <div className="mt-3 flex gap-5 text-sm">
        <span className="text-ink-muted">Резидент: <b className="text-ink">{formatKzt(item.price_resident_kzt)}</b></span>
        <span className="text-ink-muted">Нерезидент: <b className="text-ink">{formatKzt(item.price_nonresident_kzt)}</b></span>
      </div>

      {/* Быстрые предложения для несопоставленных */}
      {mode === "view" && item.suggestions.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-xs font-medium text-ink-faint">Предложения справочника:</p>
          <div className="flex flex-wrap gap-2">
            {item.suggestions.map((s) => (
              <button
                key={s.service_id}
                onClick={() => quickMatch(s)}
                disabled={busy}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-primary-200 bg-primary-50 px-3 py-1.5 text-sm font-medium text-primary-700 transition-colors duration-150 hover:bg-primary-100 disabled:cursor-wait disabled:opacity-60"
              >
                <CheckCircle size={15} weight="fill" /> {s.service_name}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Редактор */}
      {mode === "edit" && (
        <div className="mt-4 space-y-3 rounded-lg border border-line bg-canvas/50 p-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">Услуга справочника</label>
            <select
              value={serviceId ?? ""}
              onChange={(e) => setServiceId(e.target.value || undefined)}
              className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary-400 focus:outline-none"
            >
              <option value="">— оставить как есть —</option>
              {item.suggestions.map((s) => (
                <option key={s.service_id} value={s.service_id}>{s.service_name}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-ink-muted">Цена резидента (₸)</label>
              <Input type="number" value={resident} onChange={(e) => setResident(e.target.value)} placeholder="—" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-ink-muted">Цена нерезидента (₸)</label>
              <Input type="number" value={nonresident} onChange={(e) => setNonresident(e.target.value)} placeholder="—" />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">Заметка (необязательно)</label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Комментарий к проверке" />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={saveEdit} disabled={busy} icon={busy ? <Spinner size={14} /> : <CheckCircle size={15} />}>
              Сохранить и утвердить
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setMode("view")} disabled={busy} icon={<X size={15} />}>
              Отмена
            </Button>
          </div>
        </div>
      )}

      {/* Контекст из файла */}
      {showCtx && (
        <div className="mt-4 rounded-lg border border-line bg-canvas/50 p-4 text-sm">
          {ctxLoading ? (
            <span className="flex items-center gap-2 text-ink-muted"><Spinner size={14} /> Загружаем исходник…</span>
          ) : ctx ? (
            <div className="space-y-2">
              <p className="text-xs text-ink-faint">Фрагмент исходного документа{ctx.file_name ? ` · ${ctx.file_name}` : ""}:</p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-surface p-3 text-xs text-ink">{ctx.raw_snippet || "Фрагмент не найден."}</pre>
              {ctx.parse_log && (
                <details className="text-xs text-ink-muted">
                  <summary className="cursor-pointer">Лог обработки</summary>
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-surface p-3">{ctx.parse_log}</pre>
                </details>
              )}
            </div>
          ) : (
            <span className="text-ink-faint">Контекст недоступен.</span>
          )}
        </div>
      )}

      {/* Действия */}
      {mode === "view" && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
          <Button size="sm" onClick={approve} disabled={busy} icon={busy ? <Spinner size={14} /> : <SealCheck size={15} />}>
            Утвердить
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setMode("edit")} disabled={busy} icon={<PencilSimple size={15} />}>
            Редактировать
          </Button>
          <Button size="sm" variant="ghost" onClick={toggleCtx} disabled={busy} icon={<FileText size={15} />}>
            {showCtx ? "Скрыть исходник" : "Показать в файле"}
          </Button>
        </div>
      )}
    </Card>
  );
}

export function VerifyView() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);

  const load = () => api.review().then(setItems).catch(() => setItems([]));
  useEffect(() => {
    load();
  }, []);

  const onResolved = (id: string) => setItems((prev) => (prev ?? []).filter((i) => i.item_id !== id));

  return (
    <div>
      <PageHeader
        title="Очередь верификации"
        description="Позиции, требующие проверки: не сопоставленные со справочником и помеченные при валидации (аномалии цен)."
        action={items && items.length > 0 ? <Badge tone="warning">{items.length} в очереди</Badge> : undefined}
      />

      {items === null ? (
        <div className="space-y-3">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<SealCheck size={24} />}
          title="Очередь пуста"
          description="Все позиции проверены и сопоставлены со справочником услуг. Отличная работа!"
        />
      ) : (
        <div className="space-y-3">
          {items.map((it) => (
            <ReviewCard key={it.item_id} item={it} onResolved={onResolved} />
          ))}
        </div>
      )}
    </div>
  );
}
