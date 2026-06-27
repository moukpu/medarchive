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
  if (s === "done") return <CheckCircle size={15} weight="fill" className="text-accent-500" />;
  if (s === "processing") return <SpinnerIcon size={15} className="animate-spin text-primary-500" />;
  if (s === "needs_review") return <WarningCircle size={15} weight="fill" className="text-warning-500" />;
  if (s === "error") return <WarningCircle size={15} weight="fill" className="text-danger-500" />;
  return <Clock size={15} className="text-ink-faint" />;
}

function StatCard({ icon, label, value, tone = "default" }: { icon: React.ReactNode; label: string; value: number; tone?: "default" | "accent" }) {
  return (
    <MagicCard className="flex flex-col items-start gap-4 p-6 glass-panel hover-lift" gradientColor={tone === "accent" ? "rgba(6, 182, 212, 0.2)" : "rgba(255, 255, 255, 0.05)"}>
      <div
        className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl shadow-lg ${
          tone === "accent" ? "bg-primary-500 text-white shadow-primary-500/20" : "bg-white/10 text-white border border-white/10"
        }`}
      >
        {icon}
      </div>
      <div>
        <p className="text-4xl font-bold tracking-tighter text-white">
          <NumberTicker value={value} />
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
    <div className="relative min-h-screen w-full overflow-hidden pb-12">
      {/* Анимированный фон (Particles) */}
      <Particles
        className="absolute inset-0 -z-10 bg-canvas"
        quantity={150}
        ease={80}
        color="#06b6d4"
        refresh
      />

      <div className="relative z-10 px-4 md:px-8">
        <PageHeader title="MedArchive AI" description="Предиктивная аналитика и автоматизированная нормализация медицинских прайсов." />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Главная колонка загрузки (Bento Grid - Main span 2) */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            <MagicCard
              className={`p-10 border-dashed transition-all duration-300 ${dragOver ? "border-primary-400 bg-primary-900/20 scale-[1.02]" : "border-white/10"}`}
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
                <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-white/5 text-primary-400 shadow-[inset_0_1px_1px_rgba(255,255,255,0.1)]">
                  {uploading ? <Spinner size={40} className="animate-spin" /> : <FileArchive size={40} weight="duotone" />}
                </div>
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-white mb-2">Нейросетевая обработка</h2>
                  <p className="text-base text-ink-muted max-w-md mx-auto">Перетащите ZIP-архив с прайс-листами (.pdf, .docx, .xlsx, .jpg) в эту область или выберите файл вручную.</p>
                </div>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".zip"
                  className="hidden"
                  onChange={(e) => upload(e.target.files?.[0])}
                />
                
                <ShimmerButton 
                  className="mt-4 shadow-2xl"
                  onClick={() => inputRef.current?.click()} 
                  disabled={uploading}
                >
                  <span className="flex items-center gap-2 whitespace-pre-wrap text-center text-sm font-medium leading-none tracking-tight text-white dark:from-white dark:to-slate-900/10 lg:text-lg">
                    {uploading ? "Загрузка..." : "Выбрать ZIP-файл"}
                  </span>
                </ShimmerButton>
                
                {msg && (
                  <p className={`flex items-center gap-2 text-sm font-medium px-4 py-2 rounded-full mt-4 ${error ? "bg-danger-500/10 text-danger-400 border border-danger-500/20" : "bg-primary-500/10 text-primary-300 border border-primary-500/20"}`}>
                    {error ? <WarningCircle size={16} /> : <CheckCircle size={16} weight="fill" />} {msg}
                  </p>
                )}
              </div>
            </MagicCard>

            {batch && batch.length > 0 && (
              <MagicCard className="p-6">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="flex items-center gap-2 font-semibold text-white">
                    {allDone ? (
                      <CheckCircle size={20} weight="fill" className="text-accent-500" />
                    ) : (
                      <SpinnerIcon size={20} className="animate-spin text-primary-400" />
                    )}
                    {allDone ? "Обработка завершена" : "Модели анализируют данные…"}
                  </h3>
                  <Badge tone={allDone ? "success" : "primary"}>
                    {doneCount} / {total}
                  </Badge>
                </div>
                <div className="mb-6 h-2 w-full overflow-hidden rounded-full bg-white/5 shadow-inner">
                  <div
                    className={`h-full rounded-full transition-all duration-1000 ease-out ${allDone ? "bg-accent-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" : "bg-primary-500 shadow-[0_0_10px_rgba(6,182,212,0.5)]"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                  {batch.map((doc) => (
                    <div key={doc.doc_id} className="flex items-center justify-between gap-4 rounded-xl border border-white/5 bg-white/5 px-4 py-3 hover:bg-white/10 transition-colors">
                      <span className="flex min-w-0 items-center gap-3">
                        <StatusIcon s={doc.parse_status} />
                        <span className="truncate text-sm font-medium text-white">{doc.file_name}</span>
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
