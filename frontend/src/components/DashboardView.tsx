import { useEffect, useRef, useState } from "react";
import {
  UploadSimple,
  FileArchive,
  Files,
  ListChecks,
  Gauge,
  Hourglass,
  CheckCircle,
  WarningCircle,
  Spinner as SpinnerIcon,
  Clock,
} from "@phosphor-icons/react";
import { api, type Dashboard, type DocumentStatus } from "../api";
import { Badge, Button, Card, PageHeader, Spinner } from "./ui";

const STATUS_LABEL: Record<string, string> = {
  pending: "В очереди",
  processing: "Обрабатывается",
  done: "Готово",
  error: "Ошибка",
  needs_review: "На проверке",
};

const TERMINAL = new Set(["done", "error", "needs_review"]);

function statusTone(s: string): "neutral" | "primary" | "success" | "warning" | "danger" {
  if (s === "done") return "success";
  if (s === "processing") return "primary";
  if (s === "needs_review") return "warning";
  if (s === "error") return "danger";
  return "neutral";
}

function StatusIcon({ s }: { s: string }) {
  if (s === "done") return <CheckCircle size={15} weight="fill" className="text-accent-600" />;
  if (s === "processing") return <SpinnerIcon size={15} className="animate-spin text-primary-600" />;
  if (s === "needs_review") return <WarningCircle size={15} weight="fill" className="text-warning-600" />;
  if (s === "error") return <WarningCircle size={15} weight="fill" className="text-danger-600" />;
  return <Clock size={15} className="text-ink-faint" />;
}

function StatCard({ icon, label, value, tone = "default" }: { icon: React.ReactNode; label: string; value: string | number; tone?: "default" | "accent" }) {
  return (
    <Card className="flex items-center gap-4">
      <div
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${
          tone === "accent" ? "bg-accent-50 text-accent-600" : "bg-primary-50 text-primary-600"
        }`}
      >
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold leading-tight text-ink">{value}</p>
        <p className="text-sm text-ink-muted">{label}</p>
      </div>
    </Card>
  );
}

export function DashboardView() {
  const [d, setD] = useState<Dashboard | null>(null);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [batch, setBatch] = useState<DocumentStatus[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<number | null>(null);

  const load = () => api.dashboard().then(setD).catch(() => {});
  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  const startPolling = (docIds: string[]) => {
    if (pollRef.current) window.clearInterval(pollRef.current);
    const ids = new Set(docIds);
    const tick = async () => {
      try {
        const all = await api.status();
        const mine = all.filter((x) => ids.has(x.doc_id));
        setBatch(mine);
        if (mine.length === docIds.length && mine.every((x) => TERMINAL.has(x.parse_status))) {
          if (pollRef.current) window.clearInterval(pollRef.current);
          pollRef.current = null;
          load();
        }
      } catch {
        /* временная сетевая ошибка — продолжаем поллинг */
      }
    };
    tick();
    pollRef.current = window.setInterval(tick, 1500);
  };

  const upload = async (f: File | undefined) => {
    if (!f) return;
    setUploading(true);
    setMsg(null);
    setError(false);
    setBatch(null);
    try {
      const r: any = await api.uploadArchive(f);
      const docIds: string[] = r.doc_ids ?? [];
      setMsg(`Поставлено документов в обработку: ${r.queued_documents ?? docIds.length}.`);
      if (docIds.length) startPolling(docIds);
      else load();
    } catch {
      setError(true);
      setMsg("Не удалось загрузить архив. Проверьте формат файла (.zip) и попробуйте снова.");
    } finally {
      setUploading(false);
    }
  };

  const doneCount = batch ? batch.filter((x) => TERMINAL.has(x.parse_status)).length : 0;
  const total = batch?.length ?? 0;
  const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0;
  const allDone = total > 0 && doneCount === total;

  if (!d) {
    return (
      <div className="flex items-center justify-center gap-2 py-20 text-sm text-ink-muted">
        <Spinner size={16} /> Загружаем метрики…
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Дашборд" description="Метрики качества обработки архива прайс-листов." />

      <Card
        className={`mb-6 border-dashed transition-colors duration-200 ${dragOver ? "border-primary-400 bg-primary-50/40" : ""}`}
        onDragOver={(e: React.DragEvent) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e: React.DragEvent) => {
          e.preventDefault();
          setDragOver(false);
          upload(e.dataTransfer.files?.[0]);
        }}
      >
        <div className="flex flex-col items-center gap-3 py-4 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-50 text-primary-600">
            {uploading ? <Spinner size={22} /> : <FileArchive size={22} />}
          </div>
          <div>
            <p className="font-semibold text-ink">Загрузка архива прайс-листов</p>
            <p className="text-sm text-ink-muted">Перетащите ZIP-файл сюда или выберите его вручную</p>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            className="hidden"
            onChange={(e) => upload(e.target.files?.[0])}
          />
          <Button variant="secondary" icon={<UploadSimple size={16} />} onClick={() => inputRef.current?.click()} disabled={uploading}>
            {uploading ? "Загружаем…" : "Выбрать ZIP-файл"}
          </Button>
          {msg && (
            <p className={`flex items-center gap-1.5 text-sm font-medium ${error ? "text-danger-600" : "text-primary-700"}`}>
              {error ? <WarningCircle size={15} /> : <CheckCircle size={15} />} {msg}
            </p>
          )}
        </div>
      </Card>

      {batch && batch.length > 0 && (
        <Card className="mb-6">
          <div className="mb-3 flex items-center justify-between">
            <p className="flex items-center gap-2 font-semibold text-ink">
              {allDone ? (
                <CheckCircle size={18} weight="fill" className="text-accent-600" />
              ) : (
                <SpinnerIcon size={18} className="animate-spin text-primary-600" />
              )}
              {allDone ? "Обработка завершена" : "Идёт обработка…"}
            </p>
            <span className="text-sm font-medium text-ink-muted">{doneCount} / {total}</span>
          </div>
          <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-canvas">
            <div
              className={`h-full rounded-full transition-all duration-500 ${allDone ? "bg-accent-500" : "bg-primary-500"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="space-y-1.5">
            {batch.map((doc) => (
              <div key={doc.doc_id} className="flex items-center justify-between gap-3 rounded-lg px-3 py-2 hover:bg-canvas/60">
                <span className="flex min-w-0 items-center gap-2">
                  <StatusIcon s={doc.parse_status} />
                  <span className="truncate text-sm text-ink">{doc.file_name}</span>
                </span>
                <Badge tone={statusTone(doc.parse_status)}>{STATUS_LABEL[doc.parse_status] ?? doc.parse_status}</Badge>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={<Files size={20} />} label="Документов" value={d.documents_total} />
        <StatCard icon={<ListChecks size={20} />} label="Позиций всего" value={d.items_total} />
        <StatCard icon={<Gauge size={20} />} label="Автонормализация" value={`${d.auto_match_rate}%`} tone="accent" />
        <StatCard icon={<Hourglass size={20} />} label="В очереди" value={d.items_unmatched} />
      </div>

      <Card className="mt-6">
        <p className="mb-4 font-semibold text-ink">Документы по статусам</p>
        <div className="space-y-3">
          {Object.entries(d.documents_by_status).map(([k, v]) => {
            const docPct = d.documents_total > 0 ? Math.round((v / d.documents_total) * 100) : 0;
            return (
              <div key={k}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-ink-muted">{STATUS_LABEL[k] ?? k}</span>
                  <span className="font-medium text-ink">{v}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-canvas">
                  <div className="h-full rounded-full bg-primary-500" style={{ width: `${docPct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
