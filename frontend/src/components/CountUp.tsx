"use client";

import { useEffect, useRef, useState } from "react";

interface CountUpProps {
  value: number;
  prefix?: string;
  suffix?: string;
  duration?: number;
  decimals?: number;
  className?: string;
}

export function CountUp({
  value,
  prefix = "",
  suffix = "",
  duration = 1000,
  decimals = 0,
  className,
}: CountUpProps) {
  const [display, setDisplay] = useState("0");
  const ref = useRef<HTMLSpanElement>(null);
  const hasAnimated = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !hasAnimated.current) {
          hasAnimated.current = true;
          animate();
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(el);
    return () => observer.disconnect();

    function animate() {
      const start = performance.now();

      function tick(now: number) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = eased * value;

        setDisplay(formatNumber(current, decimals));

        if (progress < 1) {
          requestAnimationFrame(tick);
        } else {
          setDisplay(formatNumber(value, decimals));
        }
      }

      requestAnimationFrame(tick);
    }
  }, [value, duration, decimals]);

  return (
    <span ref={ref} className={className ?? "font-mono font-bold"}>
      {prefix}
      {display}
      {suffix}
    </span>
  );
}

function formatNumber(n: number, decimals: number): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}
