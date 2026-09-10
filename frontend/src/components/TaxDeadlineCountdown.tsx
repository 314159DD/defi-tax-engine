"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface Deadline {
  labelKey: string;
  descKey: string;
  descParams?: Record<string, string | number>;
  date: Date;
  urgent: boolean;
}

function getDaysUntil(target: Date): number {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const t = new Date(target);
  t.setHours(0, 0, 0, 0);
  return Math.ceil((t.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function getDeadlines(year: number): Deadline[] {
  const deadlines: Array<Omit<Deadline, "urgent">> = [
    {
      labelKey: "q1Estimated",
      descKey: "q1Desc",
      date: new Date(year, 3, 15),
    },
    {
      labelKey: "filingDeadline",
      descKey: "filingDesc",
      descParams: { year: year - 1 },
      date: new Date(year, 3, 15),
    },
    {
      labelKey: "q2Estimated",
      descKey: "q2Desc",
      date: new Date(year, 5, 16),
    },
    {
      labelKey: "q3Estimated",
      descKey: "q3Desc",
      date: new Date(year, 8, 15),
    },
    {
      labelKey: "extensionDeadline",
      descKey: "extensionDesc",
      descParams: { year: year - 1 },
      date: new Date(year, 9, 15),
    },
    {
      labelKey: "q4Estimated",
      descKey: "q4Desc",
      descParams: { year },
      date: new Date(year + 1, 0, 15),
    },
  ];

  return deadlines
    .map((d) => ({ ...d, urgent: getDaysUntil(d.date) <= 30 && getDaysUntil(d.date) >= 0 }))
    .filter((d) => getDaysUntil(d.date) >= 0)
    .sort((a, b) => a.date.getTime() - b.date.getTime());
}

function DeadlineCard({ deadline }: { deadline: Deadline }) {
  const t = useTranslations("deadlines");
  const tc = useTranslations("common");
  const days = getDaysUntil(deadline.date);
  const dateStr = deadline.date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  let urgencyClass = "text-muted-foreground";
  let daysLabel = `${days} ${tc("days")}`;
  if (days === 0) {
    urgencyClass = "text-red-400 font-bold";
    daysLabel = tc("today");
  } else if (days === 1) {
    urgencyClass = "text-red-400 font-bold";
    daysLabel = tc("tomorrow");
  } else if (days <= 7) {
    urgencyClass = "text-orange-400 font-semibold";
  } else if (days <= 30) {
    urgencyClass = "text-yellow-400";
  }

  return (
    <div className="flex items-center justify-between py-3 px-4 rounded-lg border border-border bg-card/50">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">{t(deadline.labelKey)}</span>
          {deadline.urgent && (
            <Badge variant="destructive" className="text-xs py-0">
              {tc("soon")}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t(deadline.descKey, deadline.descParams)}
        </p>
        <p className="text-xs text-muted-foreground">{dateStr}</p>
      </div>
      <div className={`text-right ml-4 ${urgencyClass}`}>
        <div className="text-2xl font-bold tabular-nums">{days === 0 ? "0" : days}</div>
        <div className="text-xs">{days === 0 ? tc("today") : days === 1 ? tc("day") : tc("days")}</div>
      </div>
    </div>
  );
}

export function TaxDeadlineCountdown() {
  const t = useTranslations("deadlines");
  const year = new Date().getFullYear();
  const deadlines = useMemo(() => getDeadlines(year), [year]);
  const nextDeadline = deadlines[0];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          {t("title")}
          {nextDeadline && getDaysUntil(nextDeadline.date) <= 30 && (
            <Badge variant="destructive" className="text-xs">
              {getDaysUntil(nextDeadline.date)}d
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {deadlines.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("noDeadlines")}</p>
        ) : (
          <div className="space-y-2">
            {deadlines.slice(0, 4).map((d) => (
              <DeadlineCard key={d.labelKey + d.date.toISOString()} deadline={d} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
