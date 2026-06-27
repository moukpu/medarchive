import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
  Trash,
} from "@phosphor-icons/react";
import { api, type DocumentStatus } from "../api";
import { Badge, PageHeader, Spinner } from "./ui";
import { Particles } from "./magicui/Particles";
import { MagicCard } from "./magicui/MagicCard";
import NumberTicker from "./magicui/NumberTicker";
import { ShimmerButton } from "./magicui/ShimmerButton";

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

function StatCard({ icon, label, value, tone = "default" }: { icon: React.ReactNode; label: string; value: number | string; tone?: "default" | "accent" }) {
  const numericValue = typeof value === 'number' ? value : Number(value) || 0;
  return (
    <MagicCard className="flex flex-col items-start gap-4 p-6 glass-panel hover-lift shadow-card" gradientColor={tone === "accent" ? "rgba(6, 182, 212, 0.15)" : "rgba(255, 255, 255, 0.03)"}>
      <div
        className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl shadow-sm ${
          tone === "accent" ? "bg-primary-50 text-primary-600 shadow-primary-500/10" : "bg-canvas text-ink-muted border border-line"
        }`}
      >
        {icon}
      </div>
      <div>
        <p className="text-4xl font-bold tracking-tighter text-ink">
          <NumberTicker value={numericValue} />
          {tone === "accent" && "%"}
        </p>
        <p className="text-sm font-medium text-ink-muted mt-1">{label}</p>
      </div>
    </MagicCard>
  );
}

export function DashboardView() {
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [batch, setBatch] = useState<DocumentStatus[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: d, refetch: load } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => api.dashboard()
  });

  const { data: allStatuses } = useQuery({
    queryKey: ['status'],
    queryFn: () => api.status(),
    refetchInterval: (query) => {
      const statuses = query.state.data;
      if (!statuses || !batch) return false;
      const ids = new Set(batch.map(x => x.doc_id));
      const mine = statuses.filter(x => ids.has(x.doc_id));
      if (mine.length === batch.length && mine.every(x => TERMINAL.has(x.parse_status))) {
        load();
        return false;
      }
      return 1500;
    },
    enabled: !!batch && batch.some(x => !TERMINAL.has(x.parse_status))
  });

  useEffect(() => {
    if (allStatuses && batch) {
      const ids = new Set(batch.map(x => x.doc_id));
      setBatch(allStatuses.filter(x => ids.has(x.doc_id)));
    }
  }, [allStatuses]);

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
      if (docIds.length) {
        setBatch(docIds.map(id => ({ doc_id: id, file_name: "Загрузка...", parse_status: "pending", parsed_at: "", file_format: "zip" })));
      } else {
        load();
      }
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
    <div className="relative w-full overflow-hidden pb-12">
      {/* Анимированный фон (Particles) */}
      <Particles
        className="absolute inset-0 -z-10"
        quantity={150}
        ease={80}
        color="#0ea5e9"
        refresh
      />

      <div className="relative z-10 px-0">
        <div className="flex items-center justify-between">
          <PageHeader title="MedArchive AI" description="Предиктивная аналитика и автоматизированная нормализация медицинских прайсов." />
          <button
            onClick={async () => {
              if (window.confirm("ВЫ УВЕРЕНЫ? Это удалит все документы, услуги, прайсы и партнеров из базы данных!")) {
                setUploading(true);
                try {
                  await api.clearDb();
                  window.alert("База данных успешно очищена.");
                  window.location.reload();
                } catch (e) {
                  window.alert("Ошибка очистки: " + e);
                } finally {
                  setUploading(false);
                }
              }
            }}
            disabled={uploading}
            className="flex items-center gap-2 rounded-xl bg-danger-50 px-4 py-2 text-sm font-medium text-danger-600 border border-danger-500/20 hover:bg-danger-100 transition-colors disabled:opacity-50"
          >
            <Trash size={18} />
            Очистить БД
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Главная колонка загрузки (Bento Grid - Main span 2) */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            <MagicCard
              className={`p-10 border-dashed transition-all duration-300 glass-panel shadow-sm ${dragOver ? "border-primary-400 bg-primary-900/20 scale-[1.02]" : "border-line-strong"}`}
              gradientColor="rgba(6, 182, 212, 0.05)"
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
              <div className="flex flex-col items-center gap-6 text-center">
                <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-canvas text-primary-600 shadow-[inset_0_1px_1px_rgba(0,0,0,0.05)] border border-line">
                  {uploading ? <Spinner size={40} className="animate-spin" /> : <FileArchive size={40} weight="duotone" />}
                </div>
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-ink mb-2">Нейросетевая обработка</h2>
                  <p className="text-base text-ink-muted max-w-md mx-auto">Перетащите ZIP-архив с прайс-листами (.pdf, .docx, .xlsx, .jpg) в эту область или выберите файл вручную.</p>
                </div>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => {
                    upload(e.target.files?.[0]);
                    e.target.value = ''; // Сбрасываем значение, чтобы можно было выбрать тот же файл снова
                  }}
                />
                
                <ShimmerButton 
                  className="mt-4 shadow-popover"
                  shimmerColor="var(--color-primary-300)"
                  shimmerSize="0.08em"
                  background="var(--color-surface)"
                  onClick={() => inputRef.current?.click()} 
                  disabled={uploading}
                >
                  <span className="flex items-center gap-2 whitespace-pre-wrap text-center text-sm font-medium leading-none tracking-tight text-white lg:text-lg">
                    {uploading ? "Загрузка..." : "Выбрать ZIP-файл"}
                  </span>
                </ShimmerButton>
                
                {msg && (
                  <p className={`flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full mt-4 ${error ? "bg-danger-50 text-danger-600 border border-danger-500/20" : "bg-primary-50 text-primary-700 border border-primary-500/20"}`}>
                    {error ? <WarningCircle size={16} /> : <CheckCircle size={16} weight="fill" />} {msg}
                  </p>
                )}
              </div>
            </MagicCard>

            {batch && batch.length > 0 && (
              <MagicCard className="p-6 glass-panel shadow-card" gradientColor="rgba(255, 255, 255, 0.03)">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="flex items-center gap-2 font-semibold text-ink">
                    {allDone ? (
                      <CheckCircle size={20} weight="fill" className="text-accent-600" />
                    ) : (
                      <SpinnerIcon size={20} className="animate-spin text-primary-600" />
                    )}
                    {allDone ? "Обработка завершена" : "Модели анализируют данные…"}
                  </h3>
                  <Badge tone={allDone ? "success" : "primary"}>
                    {doneCount} / {total}
                  </Badge>
                </div>
                <div className="mb-6 h-2 w-full overflow-hidden rounded-full bg-canvas shadow-inner border border-line">
                  <div
                    className={`h-full rounded-full transition-all duration-1000 ease-out ${allDone ? "bg-accent-500 shadow-[0_0_10px_rgba(16,185,129,0.3)]" : "bg-primary-500 shadow-[0_0_10px_rgba(6,182,212,0.3)]"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                  {batch.map((doc) => (
                    <div key={doc.doc_id} className="flex items-center justify-between gap-4 rounded-xl border border-line bg-canvas px-4 py-3 hover:bg-line/50 transition-colors">
                      <span className="flex min-w-0 items-center gap-3">
                        <StatusIcon s={doc.parse_status} />
                        <span className="truncate text-sm font-medium text-ink">{doc.file_name}</span>
                      </span>
                      <Badge tone={statusTone(doc.parse_status)}>{STATUS_LABEL[doc.parse_status] ?? doc.parse_status}</Badge>
                    </div>
                  ))}
                </div>
              </MagicCard>
            )}
          </div>

          {/* Боковая колонка со статистикой */}
          <div className="grid grid-cols-1 gap-6 content-start">
            <StatCard icon={<Files size={24} weight="duotone" />} label="Всего документов" value={d.documents_total} />
            <StatCard icon={<Gauge size={24} weight="duotone" />} label="Точность ИИ (%)" value={d.auto_match_rate} tone="accent" />
            <StatCard icon={<ListChecks size={24} weight="duotone" />} label="Извлеченных позиций" value={d.items_total} />
            <StatCard icon={<Hourglass size={24} weight="duotone" />} label="Ожидают проверки" value={d.items_unmatched} />
          </div>
        </div>
      </div>
    </div>
  );
}
