import { useState } from "react";
import { MagnifyingGlass, ArrowLeft, ArrowRight, Buildings, Tag } from "@phosphor-icons/react";
import { api, type PartnerWithPrice, type Service, type SearchItem } from "../api";
import { Badge, Button, Card, EmptyState, Input, LoadingBlock, PageHeader, SkeletonRow } from "./ui";
import { formatKzt } from "../format";

export function SearchView() {
  const [q, setQ] = useState("");
  const [services, setServices] = useState<Service[]>([]);
  const [items, setItems] = useState<SearchItem[]>([]);
  const [selected, setSelected] = useState<Service | null>(null);
  const [partnersList, setPartnersList] = useState<PartnerWithPrice[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [detailLoading, setDetailLoading] = useState(false);

  const doSearch = async () => {
    if (!q.trim()) return;
    setStatus("loading");
    setSelected(null);
    setPartnersList([]);
    try {
      const r = await api.search(q);
      setServices(r.services);
      setItems(r.items ?? []);
      setStatus("done");
    } catch {
      setStatus("done");
      setServices([]);
      setItems([]);
    }
  };

  const openService = async (s: Service) => {
    setSelected(s);
    setDetailLoading(true);
    try {
      setPartnersList(await api.servicePartners(s.service_id));
    } finally {
      setDetailLoading(false);
    }
  };

  const nothing = status === "done" && services.length === 0 && items.length === 0;

  return (
    <div>
      <PageHeader
        title="Поиск услуги"
        description="Найдите услугу в прайсах клиник-партнёров и сравните цены."
      />

      {!selected && (
        <>
          <div className="mb-6 flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <MagnifyingGlass size={18} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Например: анализ крови, МРТ, консультация кардиолога…"
                onKeyDown={(e) => e.key === "Enter" && doSearch()}
                className="pl-10"
                aria-label="Поиск услуги или партнёра"
              />
            </div>
            <Button onClick={doSearch} size="lg" icon={<MagnifyingGlass size={18} />} disabled={!q.trim()}>
              Найти
            </Button>
          </div>

          {status === "idle" && (
            <EmptyState
              icon={<MagnifyingGlass size={24} />}
              title="Начните поиск"
              description="Введите название услуги — например «УЗИ» или «общий анализ крови» — чтобы увидеть клиники и цены."
            />
          )}

          {status === "loading" && (
            <div className="space-y-3">
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </div>
          )}

          {nothing && (
            <EmptyState
              icon={<MagnifyingGlass size={24} />}
              title="Ничего не найдено"
              description={`По запросу «${q}» ничего нет. Проверьте написание или попробуйте более общий термин.`}
            />
          )}

          {/* Реальные позиции прайсов — основная выдача, сразу с ценой */}
          {status === "done" && items.length > 0 && (
            <section className="mb-8">
              <div className="mb-3 flex items-center gap-2">
                <h3 className="text-sm font-semibold text-ink">Найдено в прайсах</h3>
                <Badge tone="primary">{items.length}</Badge>
              </div>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {items.map((it) => (
                  <Card key={it.item_id} padded={false} className="hover-lift flex flex-col gap-2 p-4">
                    <p className="font-semibold leading-snug text-ink">{it.service_name_raw}</p>
                    <div className="flex items-center gap-1.5 text-xs text-ink-muted">
                      <Buildings size={13} className="text-ink-faint" />
                      <span className="truncate">{it.partner_name}</span>
                      {it.city && (
                        <>
                          <span className="text-ink-faint">·</span>
                          <span>{it.city}</span>
                        </>
                      )}
                    </div>
                    <div className="mt-1 flex items-end justify-between gap-3 border-t border-line pt-2.5">
                      <div>
                        <p className="text-[11px] uppercase tracking-wide text-ink-faint">Резидент</p>
                        <p className="text-lg font-bold text-primary-300">{formatKzt(it.price_resident_kzt)}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-[11px] uppercase tracking-wide text-ink-faint">Нерезидент</p>
                        <p className="text-sm font-medium text-ink-muted">{formatKzt(it.price_nonresident_kzt)}</p>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          )}

          {/* Справочные услуги — клик ведёт к сравнению по всем партнёрам */}
          {status === "done" && services.length > 0 && (
            <section>
              <div className="mb-3 flex items-center gap-2">
                <h3 className="text-sm font-semibold text-ink">Услуги справочника</h3>
                <Badge tone="neutral">{services.length}</Badge>
              </div>
              <div className="space-y-2.5">
                {services.map((s) => (
                  <Card
                    key={s.service_id}
                    padded={false}
                    className="hover-lift group flex cursor-pointer items-center justify-between gap-4 p-4"
                  >
                    <button onClick={() => openService(s)} className="flex w-full cursor-pointer items-center justify-between gap-4 text-left">
                      <div>
                        <p className="font-semibold text-ink">{s.service_name}</p>
                        {s.category && (
                          <Badge tone="primary" className="mt-1.5">
                            <Tag size={12} /> {s.category}
                          </Badge>
                        )}
                      </div>
                      <span className="flex shrink-0 items-center gap-1 text-sm font-medium text-primary-300 opacity-80 group-hover:opacity-100">
                        Сравнить цены <ArrowRight size={16} />
                      </span>
                    </button>
                  </Card>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {selected && (
        <div className="animate-fade-in">
          <Button variant="ghost" size="sm" icon={<ArrowLeft size={16} />} onClick={() => setSelected(null)} className="mb-4 -ml-2">
            Назад к результатам
          </Button>
          <div className="mb-5">
            <h2 className="text-xl font-bold text-ink">{selected.service_name}</h2>
            {selected.category && (
              <Badge tone="primary" className="mt-2">
                <Tag size={12} /> {selected.category}
              </Badge>
            )}
          </div>

          {detailLoading ? (
            <LoadingBlock label="Загружаем партнёров…" />
          ) : partnersList.length === 0 ? (
            <EmptyState
              icon={<Buildings size={24} />}
              title="Нет партнёров с этой услугой"
              description="Пока ни одна клиника не указала цену на эту услугу в обработанных прайс-листах."
            />
          ) : (
            <Card padded={false} className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-line bg-canvas text-left text-xs font-semibold uppercase tracking-wide text-ink-faint">
                      <th className="px-5 py-3">Партнёр</th>
                      <th className="px-5 py-3 text-right">Резидент</th>
                      <th className="px-5 py-3 text-right">Нерезидент</th>
                      <th className="px-5 py-3 text-right">Дата прайса</th>
                    </tr>
                  </thead>
                  <tbody>
                    {partnersList.map((p) => (
                      <tr key={p.item_id} className="border-b border-line last:border-0 hover:bg-white/[0.03]">
                        <td className="px-5 py-3.5">
                          <p className="font-medium text-ink">{p.partner.name}</p>
                          {p.partner.city && <p className="text-xs text-ink-faint">{p.partner.city}</p>}
                        </td>
                        <td className="px-5 py-3.5 text-right font-semibold text-ink">{formatKzt(p.price_resident_kzt)}</td>
                        <td className="px-5 py-3.5 text-right text-ink-muted">{formatKzt(p.price_nonresident_kzt)}</td>
                        <td className="px-5 py-3.5 text-right text-ink-faint">{p.effective_date || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
