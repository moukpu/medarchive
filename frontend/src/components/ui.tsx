import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import { Button as ShadButton } from "@/components/ui/button";
import { Badge as ShadBadge } from "@/components/ui/badge";
import { Input as ShadInput } from "@/components/ui/input";

export function Card({
  children,
  className = "",
  padded = true,
  interactive = false,
  ...rest
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  interactive?: boolean;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border-subtle bg-surface-white card-elev-1",
        interactive && "hover-lift cursor-pointer",
        padded && "p-6",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

const VARIANT_MAP = {
  primary: "default",
  secondary: "secondary",
  ghost: "ghost",
  danger: "destructive",
  outline: "outline",
} as const;
const SIZE_MAP = { sm: "sm", md: "default", lg: "lg" } as const;

export function Button({
  children,
  variant = "primary",
  size = "md",
  className,
  icon,
  ...rest
}: {
  children?: ReactNode;
  variant?: keyof typeof VARIANT_MAP;
  size?: keyof typeof SIZE_MAP;
  icon?: ReactNode;
  className?: string;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <ShadButton variant={VARIANT_MAP[variant]} size={SIZE_MAP[size]} className={className} {...rest}>
      {icon}
      {children}
    </ShadButton>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "primary" | "success" | "warning" | "danger";
  className?: string;
}) {
  return (
    <ShadBadge variant={tone} className={className}>
      {children}
    </ShadBadge>
  );
}

export function StatusPill({ tone, children }: { tone: "success" | "warning" | "danger" | "neutral" | "primary"; children: ReactNode }) {
  const toneClass = {
    success: "bg-success-50 text-success-600",
    warning: "bg-warning-50 text-warning-600",
    danger: "bg-danger-50 text-danger-700",
    neutral: "bg-surface-low text-ink-muted",
    primary: "bg-primary-50 text-primary-700",
  }[tone];
  return <span className={cn("status-pill", toneClass)}>{children}</span>;
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border-strong bg-surface-white px-6 py-16 text-center">
      {icon && (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-surface-low text-brand-red">
          {icon}
        </div>
      )}
      <p className="text-base font-semibold text-ink-strong">{title}</p>
      {description && <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-ink-faint">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Spinner({ size = 18, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      className={cn("animate-spin-slow", className)}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      role="status"
      aria-label="Загрузка"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function LoadingBlock({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-ink-muted">
      <Spinner size={16} />
      {label}
    </div>
  );
}

export function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border-subtle bg-surface-white p-4 card-elev-1">
      <div className="skeleton-shimmer h-10 w-10 shrink-0 rounded-lg" />
      <div className="flex-1 space-y-2.5">
        <div className="skeleton-shimmer h-3 w-2/5 rounded-md" />
        <div className="skeleton-shimmer h-3 w-1/4 rounded-md" />
      </div>
      <div className="skeleton-shimmer h-6 w-16 shrink-0 rounded-full" />
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <ShadInput {...props} />;
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[28px] font-bold leading-tight tracking-tight text-ink-strong">{title}</h1>
        {description && <p className="mt-2 text-[15px] leading-relaxed text-ink-faint max-w-2xl">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <h2 className="text-xl font-semibold tracking-tight text-ink-strong">{children}</h2>
      {action}
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Подтвердить",
  cancelLabel = "Отмена",
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
      <div
        className="w-full max-w-sm rounded-xl border border-border-subtle bg-surface-white p-6 card-elev-2"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold text-ink-strong">{title}</h3>
        {description && <p className="mt-2 text-sm leading-relaxed text-ink-faint">{description}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="ghost" size="sm" onClick={onCancel}>{cancelLabel}</Button>
          <Button variant={danger ? "danger" : "primary"} size="sm" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
