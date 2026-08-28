import { translations, type Language } from "@/lib/translations";

type DurationUnit = "hours" | "minutes";

export function formatStudyDuration(
  value: number,
  language: Language,
  unit: DurationUnit = "hours",
) {
  const safeValue = Number.isFinite(value) ? value : 0;
  const totalMinutes = Math.max(
    0,
    Math.round(unit === "hours" ? safeValue * 60 : safeValue),
  );
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const copy = translations[language];
  const parts: string[] = [];

  if (hours > 0) {
    parts.push(
      `${hours} ${hours === 1 ? copy.durationHour : copy.durationHours}`,
    );
  }

  if (minutes > 0 || hours === 0) {
    parts.push(
      `${minutes} ${minutes === 1 ? copy.durationMinute : copy.durationMinutes}`,
    );
  }

  return parts.join(" ");
}
