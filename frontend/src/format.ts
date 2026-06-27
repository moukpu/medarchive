export function formatKzt(value?: number | null): string {
  if (value == null) return "—";
  return value.toLocaleString("ru-RU") + " ₸";
}

export function formatDate(value?: string | null): string {
  if (!value) return "Без даты";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
}
