import { useEffect, useMemo, useRef, useState } from "react";
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
  Trash,
  CloudArrowUp,
  ArrowRight,
  MagnifyingGlass,
  FilePdf,
  FileXls,
  FileDoc,
  FileImage,
  DotsThreeVertical,
} from "@phosphor-icons/react";
import { api, type DocumentStatus } from "../api";
import { Card, StatusPill, Spinner, Input, Button, ConfirmDialog } from "./ui";
import type { Tab } from "../types";
import { formatDate } from "../format";

const STATUS_LABEL: Record<string, string> = {
  pending: "В очереди",
  processing: "Обработка",
  done: "Готово",
  error: "Ошибка",
  needs_review: "На проверке",
};

const STATUS_TONE: Record<string, "success" | "primary" | "warning" | "danger" | "neutral"> = {
  done: "success",
  processing: "primary",
  needs_review: "warning",
  error: "danger",
  pending: "neutral",
};

const TERMINAL = new Set(["done", "error", "needs_review"]);

type DocFilter = "all" | "done" | "needs_review" | "error";

const FILTER_LABEL: Record<DocFilter, string> = {
  all: "Все",
  done: "Готовые",
  needs_review: "На проверке",
  error: "Ошибки",
};

function FileIcon({ format }: { format?: string }) {
  const f = (format ?? "").toLowerCase();
  if (f.includes("pdf")) return <FilePdf size={18} weight="duotone" className="text-danger-600" />;
  if (f.includes("xls") || f.includes("csv")) return <FileXls size={18} weight="duotone" className="text-success-600" />;
  if (f.includes("doc")) return <FileDoc size={18} weight="duotone" className="text-primary-500" />;
  if (f.includes("jpg") || f.includes("png") || f.includes("image")) return <FileImage size={18} weight="duotone" className="text-warning-600" />;
  return <FileArchive size={18} weight="duotone" className="text-ink-muted" />;
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("") || "—";
}

export function DashboardView({ onNavigate }: { onNavigate?: (t: Tab) => void }) {
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [batch, setBatch] = useState<DocumentStatus[] | null>(null);
  const [filter, setFilter] = useState<DocFilter>("all");
  const [search, setSearch] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: d, refetch: load } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.dashboard(),
  });

  const { data: allStatuses, refetch: loadStatuses } = useQuery({
    queryKey: ["status"],
    queryFn: () => api.status(),
    refetchInterval: (query) => {
      const statuses = query.state.data;
      if (!statuses || !batch) return false;
      const ids = new Set(batch.map((x) => x.doc_id));
      const mine = statuses.filter((x) => ids.has(x.doc_id));
      if (mine.length === batch.length && mine.every((x) => TERMINAL.has(x.parse_status))) {
        load();
        return false;
      }
      return 1500;
    },
  });

  useEffect(() => {
    if (allStatuses && batch) {
      const ids = new Set(batch.map((x) => x.doc_id));
      setBatch(allStatuses.filter((x) => ids.has(x.doc_id)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allStatuses]);

  const docs = allStatuses ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return docs
      .filter((doc) => {
        if (filter !== "all" && doc.parse_status !== filter) return false;
        if (!q) return true;
        const anyDoc = doc as DocumentStatus & { partner_name?: string };
        return (
          doc.file_name?.toLowerCase().includes(q) ||
          (anyDoc.partner_name ?? "").toLowerCase().includes(q)
        );
      })
      .slice(0, 20);
  }, [docs, filter, search]);

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
        setBatch(docIds.map((id) => ({ doc_id: id, file_name: "Загрузка...", parse_status: "pending", parsed_at: "", file_format: "zip" })));
      } else {
        load();
      }
    } catch {
      setError(true);
      setMsg("Не удалось загрузить файл. Допустимые форматы: ZIP, PDF, XLSX, DOCX.");
    } finally {
      setUploading(false);
    }
  };

  const onClearDb = async () => {
    setConfirmClear(false);
    setUploading(true);
    setError(false);
    try {
      await api.clearDb();
      setMsg("База данных очищена.");
      setBatch(null);
      load();
      loadStatuses();
    } catch (e) {
      setError(true);
      setMsg("Ошибка очистки: " + e);
    } finally {
      setUploading(false);
    }
  };

  const doneCount = batch ? batch.filter((x) => TERMINAL.has(x.parse_status)).length : 0;
  const total = batch?.length ?? 0;
  const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0;
  const allDone = total > 0 && doneCount === total;

  return (
    <div className="space-y-10">
      <section className="relative overflow-hidden rounded-2xl bg-brand-blue text-white card-elev-2">
        <span className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand-red/30 blur-3xl" aria-hidden="true" />
        <span className="pointer-events-none absolute -bottom-20 -left-10 h-56 w-56 rounded-full bg-primary-500/20 blur-3xl" aria-hidden="true" />

        <div className="relative grid gap-8 p-8 md:grid-cols-2 md:p-12">
          <div className="flex flex-col gap-5">
            <span className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-primary-200">
              MedArchive · Кейс 2
            </span>
            <h1 className="text-3xl font-bold leading-tight tracking-tight md:text-[40px] md:leading-[1.1]">
              Прайс-листы клиник — в один клик
            </h1>
            <p className="max-w-lg text-base leading-relaxed text-white/70 md:text-lg">
              Интеллектуальная архивация и распознавание. Загружайте PDF, Excel, Word или JPG — система структурирует данные для быстрого поиска и сравнения.
            </p>
            <div className="mt-2 flex flex-wrap gap-3">
              <Button onClick={() => inputRef.current?.click()} icon={<UploadSimple size={18} weight="bold" />} disabled={uploading}>
                {uploading ? "Загрузка…" : "Загрузить архив"}
              </Button>
              <Button variant="ghost" onClick={() => onNavigate?.("search")} className="text-white hover:bg-white/10 hover:text-white" icon={<ArrowRight size={18} />}>
                Перейти к поиску
              </Button>
            </div>
          </div>

          <div className="flex items-stretch justify-end">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                upload(e.dataTransfer.files?.[0]);
              }}
              onClick={() => inputRef.current?.click()}
              className={`group flex w-full max-w-md cursor-pointer flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed bg-surface-white p-8 text-center transition-all ${
                dragOver ? "border-brand-red bg-danger-50" : "border-border-strong hover:border-brand-red"
              }`}
            >
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-surface-low text-brand-red transition-colors group-hover:bg-brand-red group-hover:text-white">
                {uploading ? <Spinner size={28} /> : <CloudArrowUp size={32} weight="duotone" />}
              </div>
              <div>
                <p className="text-sm font-semibold text-ink-strong">Перетащите файлы сюда</p>
                <p className="mt-1 text-xs text-ink-faint">PDF, Excel, Word — отдельно или в ZIP (до 50 МБ)</p>
              </div>
              <div className="relative my-1 w-full">
                <span className="block h-px w-full bg-border-subtle" />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-surface-white px-2 text-[10px] font-semibold uppercase tracking-widest text-ink-faint">или</span>
              </div>
              <Button onClick={(e) => { e.stopPropagation(); inputRef.current?.click(); }} disabled={uploading} className="w-full">
                Выбрать файл
              </Button>
              <input
                ref={inputRef}
                type="file"
                accept=".zip,.pdf,.xlsx,.xls,.docx"
                className="hidden"
                onChange={(e) => {
                  upload(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </div>
          </div>
        </div>

        {msg && (
          <div className={`relative mx-8 mb-8 flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium ${
            error
              ? "border-danger-50 bg-danger-50/40 text-danger-700"
              : "border-success-50 bg-success-50/60 text-success-700"
          }`}>
            {error ? <WarningCircle size={16} weight="fill" /> : <CheckCircle size={16} weight="fill" />}
            {msg}
          </div>
        )}
      </section>

      {batch && batch.length > 0 && (
        <Card>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3 className="flex items-center gap-2 text-base font-semibold text-ink-strong">
              {allDone ? (
                <CheckCircle size={20} weight="fill" className="text-success-600" />
              ) : (
                <SpinnerIcon size={20} className="animate-spin text-brand-red" />
              )}
              {allDone ? "Обработка завершена" : "Модели анализируют данные…"}
            </h3>
            <span className="text-sm font-semibold tabular-nums text-ink-muted">
              {doneCount} / {total}
            </span>
          </div>
          <div className="mb-5 h-2 w-full overflow-hidden rounded-full bg-surface-low">
            <div
              className={`h-full rounded-full transition-all duration-700 ${allDone ? "bg-success-600" : "bg-brand-red"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <ul className="space-y-2">
            {batch.map((doc) => (
              <li key={doc.doc_id} className="flex items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface-low/60 px-4 py-2.5">
                <span className="flex min-w-0 items-center gap-3">
                  <FileIcon format={doc.file_format} />
                  <span className="truncate text-sm font-medium text-ink-strong">{doc.file_name}</span>
                </span>
                <StatusPill tone={STATUS_TONE[doc.parse_status] ?? "neutral"}>
                  {STATUS_LABEL[doc.parse_status] ?? doc.parse_status}
                </StatusPill>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <section>
        <div className="grid grid-cols-2 gap-4 sm:gap-6 lg:grid-cols-4">
          <StatCard icon={<Files size={20} weight="duotone" />} value={d?.documents_total ?? 0} label="Документов всего" />
          <StatCard icon={<ListChecks size={20} weight="duotone" />} value={d?.items_total ?? 0} label="Позиций в архиве" />
          <StatCard icon={<Gauge size={20} weight="duotone" />} value={`${(d?.auto_match_rate ?? 0).toFixed(1)}%`} label="Автомэтчинг" />
          <StatCard icon={<Hourglass size={20} weight="duotone" />} value={(d?.items_needs_review ?? 0) + (d?.items_unmatched ?? 0)} label="Ждут проверки" />
        </div>
      </section>

      <section>
        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <h2 className="text-2xl font-bold tracking-tight text-ink-strong">Архив документов</h2>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="pill-tabs">
              {(Object.keys(FILTER_LABEL) as DocFilter[]).map((k) => (
                <button key={k} className="pill-tab" data-active={filter === k} onClick={() => setFilter(k)}>
                  {FILTER_LABEL[k]}
                </button>
              ))}
            </div>
            <div className="relative w-full sm:w-64">
              <MagnifyingGlass size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Поиск по клинике или файлу…"
                className="pl-9"
              />
            </div>
          </div>
        </div>

        <Card padded={false} className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-border-subtle bg-surface-low">
                  <Th>Клиника / партнёр</Th>
                  <Th>Файл</Th>
                  <Th>Загружен</Th>
                  <Th className="text-right">Формат</Th>
                  <Th>Статус</Th>
                  <Th className="text-right">Действия</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {!allStatuses ? (
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i}>
                      <Td colSpan={6}><div className="skeleton-shimmer h-5 w-full rounded" /></Td>
                    </tr>
                  ))
                ) : filtered.length === 0 ? (
                  <tr>
                    <Td colSpan={6} className="py-12 text-center text-sm text-ink-faint">
                      Документов по выбранному фильтру нет.
                    </Td>
                  </tr>
                ) : (
                  filtered.map((doc) => {
                    const anyDoc = doc as DocumentStatus & { partner_name?: string };
                    const partnerName = anyDoc.partner_name ?? "—";
                    return (
                      <tr key={doc.doc_id} className="group transition-colors hover:bg-surface-low/60">
                        <Td>
                          <div className="flex items-center gap-3">
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded border border-border-subtle bg-surface-low text-[11px] font-bold text-ink-muted">
                              {initials(partnerName)}
                            </span>
                            <span className="font-semibold text-ink-strong">{partnerName}</span>
                          </div>
                        </Td>
                        <Td>
                          <div className="flex items-center gap-2 text-ink-muted">
                            <FileIcon format={doc.file_format} />
                            <span className="max-w-[260px] truncate">{doc.file_name}</span>
                          </div>
                        </Td>
                        <Td className="text-ink-muted tabular-nums">{doc.parsed_at ? formatDate(doc.parsed_at) : "—"}</Td>
                        <Td className="text-right uppercase text-ink-muted tabular-nums">{doc.file_format || "—"}</Td>
                        <Td>
                          <StatusPill tone={STATUS_TONE[doc.parse_status] ?? "neutral"}>
                            {STATUS_LABEL[doc.parse_status] ?? doc.parse_status}
                          </StatusPill>
                        </Td>
                        <Td className="text-right">
                          <button className="rounded p-1 text-ink-faint opacity-0 transition-all hover:bg-surface-low hover:text-brand-blue group-hover:opacity-100" aria-label="Действия">
                            <DotsThreeVertical size={18} weight="bold" />
                          </button>
                        </Td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-border-subtle px-5 py-3 text-xs text-ink-faint">
            <span>Показано {filtered.length} из {docs.length}</span>
            <button
              onClick={() => setConfirmClear(true)}
              disabled={uploading}
              className="inline-flex items-center gap-1.5 rounded-md border border-border-subtle bg-surface-white px-3 py-1.5 text-xs font-semibold text-danger-700 transition-colors hover:bg-danger-50 disabled:opacity-50"
            >
              <Trash size={14} /> Очистить БД
            </button>
          </div>
        </Card>
      </section>

      <ConfirmDialog
        open={confirmClear}
        title="Очистить базу данных?"
        description="Будут удалены все документы, услуги, прайсы и партнёры. Действие необратимо."
        confirmLabel="Удалить всё"
        danger
        onConfirm={onClearDb}
        onCancel={() => setConfirmClear(false)}
      />
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  const display = typeof value === "number" ? value.toLocaleString("ru-RU") : value;
  return (
    <Card padded={false} className="flex items-center gap-4 p-5 hover-lift">
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-surface-low text-brand-red">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-bold leading-none text-ink-strong tabular-nums">{display}</p>
        <p className="mt-1.5 text-xs font-semibold uppercase tracking-wider text-ink-faint">{label}</p>
      </div>
    </Card>
  );
}

function Th({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <th className={`px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-ink-faint ${className}`}>
      {children}
    </th>
  );
}

function Td({ children, className = "", colSpan }: { children: React.ReactNode; className?: string; colSpan?: number }) {
  return (
    <td colSpan={colSpan} className={`px-5 py-3.5 align-middle ${className}`}>
      {children}
    </td>
  );
}
