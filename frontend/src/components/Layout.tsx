import type { ReactNode } from "react";
import { useState } from "react";
import {
  MagnifyingGlass,
  Buildings,
  ClipboardText,
  ChartBar,
  List as ListIcon,
  X,
} from "@phosphor-icons/react";
import type { Tab } from "../types";

const NAV: { id: Tab; label: string; icon: typeof MagnifyingGlass; description: string }[] = [
  { id: "search", label: "Поиск услуги", icon: MagnifyingGlass, description: "Кто оказывает и по какой цене" },
  { id: "partners", label: "Партнёры", icon: Buildings, description: "Клиники и их прайс-листы" },
  { id: "verify", label: "Верификация", icon: ClipboardText, description: "Очередь несопоставленных позиций" },
  { id: "dashboard", label: "Дашборд", icon: ChartBar, description: "Качество обработки и загрузка архива" },
];

export function Layout({ tab, onTabChange, children }: { tab: Tab; onTabChange: (t: Tab) => void; children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const active = NAV.find((n) => n.id === tab)!;

  return (
    <div className="relative min-h-screen overflow-x-hidden lg:flex">
      <AmbientBackground />

      {/* Mobile top bar */}
      <header className="glass-panel relative z-30 flex items-center justify-between rounded-none border-0 border-b px-4 py-3 lg:hidden">
        <Brand compact />
        <button
          aria-label={mobileOpen ? "Закрыть меню" : "Открыть меню"}
          onClick={() => setMobileOpen((v) => !v)}
          className="relative z-10 flex h-11 w-11 cursor-pointer items-center justify-center rounded-lg text-ink-muted transition-transform duration-150 hover:bg-canvas active:scale-90"
        >
          {mobileOpen ? <X size={22} /> : <ListIcon size={22} />}
        </button>
      </header>

      {mobileOpen && (
        <div
          className="animate-fade-in fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`glass-panel fixed inset-y-0 left-0 z-50 w-72 shrink-0 rounded-none border-0 border-r transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] lg:static lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="relative z-10 flex h-full flex-col px-4 py-6">
          <div className="hidden px-2 lg:block">
            <Brand />
          </div>
          <button
            aria-label="Закрыть меню"
            onClick={() => setMobileOpen(false)}
            className="absolute right-3 top-3 flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-muted transition-transform duration-150 hover:bg-canvas active:scale-90 lg:hidden"
          >
            <X size={20} />
          </button>

          <nav className="mt-6 flex flex-1 flex-col gap-1" aria-label="Основная навигация">
            {NAV.map((item) => {
              const isActive = item.id === tab;
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    onTabChange(item.id);
                    setMobileOpen(false);
                  }}
                  aria-current={isActive ? "page" : undefined}
                  className={`group relative flex w-full cursor-pointer items-center gap-3 overflow-hidden rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-all duration-200 active:scale-[0.98] ${
                    isActive ? "text-primary-200" : "text-ink-muted hover:bg-white/[0.05] hover:text-ink"
                  }`}
                >
                  {isActive && (
                    <span className="animate-fade-in absolute inset-0 rounded-xl bg-gradient-to-r from-primary-500/20 to-primary-500/5 ring-1 ring-inset ring-primary-500/25" aria-hidden="true" />
                  )}
                  {isActive && (
                    <span
                      className="animate-fade-in absolute inset-y-2 left-0 w-[3px] rounded-full bg-primary-400 shadow-[0_0_10px_2px_rgb(124_92_255_/_0.55)]"
                      aria-hidden="true"
                    />
                  )}
                  <Icon
                    size={19}
                    weight={isActive ? "fill" : "regular"}
                    className={`relative z-10 shrink-0 transition-transform duration-200 group-hover:scale-110 ${
                      isActive ? "text-primary-300" : "text-ink-faint group-hover:text-ink-muted"
                    }`}
                  />
                  <div className="relative z-10 min-w-0">
                    <p className="leading-tight">{item.label}</p>
                    {isActive && <p className="mt-0.5 text-[11px] font-normal leading-tight text-primary-400/70">{item.description}</p>}
                  </div>
                </button>
              );
            })}
          </nav>

          <div className="mt-auto rounded-xl border border-white/[0.06] bg-white/[0.03] px-3.5 py-3.5 text-xs text-ink-muted ring-1 ring-inset ring-white/[0.04]">
            <p className="font-semibold text-ink">MedPartners · Кейс 2</p>
            <p className="mt-1 leading-relaxed">Автоматическая обработка архива прайс-листов клиник</p>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="relative z-10 flex-1">
        <header className="glass-panel relative z-20 hidden rounded-none border-0 border-b px-8 py-4 lg:flex lg:items-center lg:gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-500/15 text-primary-400 ring-1 ring-primary-500/20">
            {(() => { const Icon = active.icon; return <Icon size={16} weight="fill" />; })()}
          </div>
          <div className="relative z-10">
            <p className="text-sm font-semibold text-ink">{active.label}</p>
            <p className="text-xs text-ink-faint">{active.description}</p>
          </div>
        </header>
        <main className="px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div key={tab} className="animate-fade-in-up mx-auto max-w-6xl">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}

function AmbientBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden="true">
      <div className="ambient-blob -left-24 -top-24 h-96 w-96 bg-primary-300/60" />
      <div className="ambient-blob right-[-8rem] top-1/3 h-[28rem] w-[28rem] bg-accent-500/50" />
    </div>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600 text-white shadow-card">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      </div>
      <div>
        <p className="text-base font-bold leading-tight tracking-tight text-ink">MedArchive</p>
        {!compact && <p className="text-xs leading-tight text-ink-faint">Реестр прайсов клиник</p>}
      </div>
    </div>
  );
}
