import type { ReactNode } from "react";
import { useState } from "react";
import {
  Gauge,
  MagnifyingGlass,
  Buildings,
  ClipboardText,
  ChartLineUp,
  List as ListIcon,
  X,
} from "@phosphor-icons/react";
import type { Tab } from "../types";

const NAV: { id: Tab; label: string; icon: typeof Gauge }[] = [
  { id: "dashboard", label: "Дашборд", icon: Gauge },
  { id: "search", label: "Поиск услуги", icon: MagnifyingGlass },
  { id: "partners", label: "Партнёры", icon: Buildings },
  { id: "verify", label: "Верификация", icon: ClipboardText },
  { id: "reports", label: "Отчёты", icon: ChartLineUp },
];

export function Layout({ tab, onTabChange, children }: { tab: Tab; onTabChange: (t: Tab) => void; children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-surface text-ink">
      <TopNav tab={tab} onTabChange={onTabChange} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />

      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-8 sm:px-8 lg:px-16">
        <div key={tab} className="animate-fade-in-up">
          {children}
        </div>
      </main>

      <Footer />
    </div>
  );
}

function TopNav({
  tab,
  onTabChange,
  mobileOpen,
  setMobileOpen,
}: {
  tab: Tab;
  onTabChange: (t: Tab) => void;
  mobileOpen: boolean;
  setMobileOpen: (v: boolean) => void;
}) {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border-subtle bg-surface-white/95 backdrop-blur supports-[backdrop-filter]:bg-surface-white/80">
      <div className="mx-auto flex h-16 w-full max-w-[1440px] items-center justify-between gap-6 px-4 sm:px-8 lg:px-16">
        <Brand />

        <nav className="hidden h-full items-center gap-1 md:flex" aria-label="Основная навигация">
          {NAV.map((item) => {
            const isActive = item.id === tab;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                aria-current={isActive ? "page" : undefined}
                className={`relative flex h-16 items-center gap-2 px-4 text-sm font-semibold transition-colors duration-150 ${
                  isActive
                    ? "text-brand-red"
                    : "text-ink-muted hover:text-ink-strong"
                }`}
              >
                <span>{item.label}</span>
                {isActive && (
                  <span
                    className="absolute inset-x-3 -bottom-px h-[3px] rounded-t-full bg-brand-red"
                    aria-hidden="true"
                  />
                )}
              </button>
            );
          })}
        </nav>

        <div className="flex items-center gap-3">
          <span className="hidden text-xs font-medium text-ink-faint lg:block">+7 (700) 000-00-00</span>
          <button
            aria-label={mobileOpen ? "Закрыть меню" : "Открыть меню"}
            onClick={() => setMobileOpen(!mobileOpen)}
            className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg text-ink-muted hover:bg-surface-low md:hidden"
          >
            {mobileOpen ? <X size={20} /> : <ListIcon size={20} />}
          </button>
        </div>
      </div>

      {mobileOpen && (
        <nav className="border-t border-border-subtle bg-surface-white px-4 py-3 md:hidden" aria-label="Мобильная навигация">
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
                className={`flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-semibold transition-colors ${
                  isActive ? "bg-surface-low text-brand-red" : "text-ink-muted hover:bg-surface-low hover:text-ink-strong"
                }`}
              >
                <Icon size={18} weight={isActive ? "fill" : "regular"} />
                {item.label}
              </button>
            );
          })}
        </nav>
      )}
    </header>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="brand-mark" aria-hidden="true">
        <span>N</span>
      </div>
      <span className="text-lg font-bold uppercase leading-none tracking-tight text-brand-blue">
        Nomad <span className="font-medium lowercase text-brand-red tracking-normal">medarchive</span>
      </span>
    </div>
  );
}

function Footer() {
  return (
    <footer className="mt-12 w-full bg-brand-blue text-white/80">
      <div className="mx-auto grid w-full max-w-[1440px] grid-cols-1 gap-8 px-4 py-12 sm:px-8 md:grid-cols-4 lg:px-16">
        <div className="flex flex-col gap-4 md:col-span-2">
          <div className="flex items-center gap-2.5">
            <div className="brand-mark" aria-hidden="true">
              <span>N</span>
            </div>
            <span className="text-lg font-bold uppercase leading-none tracking-tight text-white">
              Nomad <span className="font-medium lowercase text-primary-200 tracking-normal">medarchive</span>
            </span>
          </div>
          <p className="max-w-sm text-sm leading-relaxed text-white/60">
            Надёжная система архивации и управления медицинскими прайс-листами. Точность и безопасность ваших данных.
          </p>
          <span className="mt-4 text-xs text-white/50">© 2026 Nomad MedArchive. Все права защищены.</span>
        </div>

        <FooterCol title="Навигация" links={["Дашборд", "Поиск услуги", "Партнёры", "Верификация", "Отчёты"]} />
        <FooterCol title="Информация" links={["Контакты", "О компании", "Политика конфиденциальности", "Условия использования"]} />
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: string[] }) {
  return (
    <div className="flex flex-col gap-3">
      <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-white">{title}</h4>
      {links.map((l) => (
        <a key={l} href="#" className="text-sm text-white/60 transition-colors hover:text-white">
          {l}
        </a>
      ))}
    </div>
  );
}
