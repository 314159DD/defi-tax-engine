"use client";

interface Threshold {
  value: number;
  color: string;
}

interface GaugeArcProps {
  value: number;
  max: number;
  size?: number;
  thresholds?: Threshold[];
  label?: string;
}

const DEFAULT_THRESHOLDS: Threshold[] = [
  { value: 0, color: "oklch(0.72 0.19 155)" },     // green
  { value: 50, color: "oklch(0.82 0.17 75)" },      // amber
  { value: 80, color: "oklch(0.65 0.22 25)" },       // red
];

export function GaugeArc({
  value,
  max,
  size = 300,
  thresholds = DEFAULT_THRESHOLDS,
  label,
}: GaugeArcProps) {
  const clamped = Math.min(max, Math.max(0, value));
  const percent = max > 0 ? (clamped / max) * 100 : 0;

  // SVG arc geometry
  const strokeWidth = size * 0.06;
  const radius = (size - strokeWidth * 2) / 2;
  const cx = size / 2;
  const cy = size / 2;

  // Semi-circle: start at left (180deg), end at right (0deg)
  const arcLength = Math.PI * radius;
  const offset = arcLength - (percent / 100) * arcLength;

  // Determine color from thresholds
  const sortedThresholds = [...thresholds].sort((a, b) => b.value - a.value);
  const activeColor =
    sortedThresholds.find((t) => percent >= t.value)?.color ??
    "oklch(0.82 0.17 75)";

  // Arc path for semi-circle (bottom half)
  const startX = cx - radius;
  const startY = cy;
  const endX = cx + radius;
  const endY = cy;

  return (
    <div className="relative inline-flex flex-col items-center" style={{ width: size, height: size * 0.6 }}>
      <svg
        width={size}
        height={size * 0.55}
        viewBox={`0 0 ${size} ${size * 0.55}`}
        className="overflow-visible"
      >
        {/* Background arc */}
        <path
          d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          className="text-border"
        />
        {/* Progress arc */}
        <path
          d={`M ${startX} ${startY} A ${radius} ${radius} 0 0 1 ${endX} ${endY}`}
          fill="none"
          stroke={activeColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={arcLength}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-out"
        />
      </svg>

      {/* Center value */}
      <div
        className="absolute flex flex-col items-center"
        style={{ bottom: 0, left: "50%", transform: "translateX(-50%)" }}
      >
        <span
          className="font-mono font-bold text-foreground leading-none"
          style={{ fontSize: size * 0.14 }}
        >
          {typeof value === "number" ? value.toLocaleString() : value}
        </span>
        {label && (
          <span
            className="text-muted-foreground mt-1"
            style={{ fontSize: size * 0.055 }}
          >
            {label}
          </span>
        )}
        <span
          className="text-muted-foreground/60 font-mono mt-0.5"
          style={{ fontSize: size * 0.04 }}
        >
          / {max.toLocaleString()}
        </span>
      </div>
    </div>
  );
}
