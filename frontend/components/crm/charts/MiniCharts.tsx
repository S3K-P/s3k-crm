'use client';

import { useId, useState } from 'react';
import { cn } from '@/lib/utils';

/* ============================================================
   MINI CHARTS
   Lightweight, dependency-free visualisations for the Sales
   Intelligence Snapshot. The project has no charting library,
   and these four shapes did not justify introducing one.

   All of them read theme tokens, work in light and dark mode,
   scale to their container, and expose their values as text so
   the information is not carried by colour alone.
   ============================================================ */

/** Series palette — drawn from the accent tokens plus the same
 *  stage colours already used by the CRM Kanban board. */
export const SERIES_COLORS = [
  'var(--accent)',
  '#818cf8',
  '#38bdf8',
  '#34d399',
  '#fbbf24',
  '#fb7185',
] as const;

interface Tooltip {
  index: number;
  label: string;
  value: string;
}

function TooltipBubble({ label, value, align }: { label: string; value: string; align: 'left' | 'center' | 'right' }) {
  return (
    <div
      role="presentation"
      className={cn(
        'surface bd pointer-events-none absolute bottom-full z-10 mb-2 w-max max-w-[180px] rounded-lg border px-2.5 py-1.5 shadow-lg',
        align === 'left' && 'left-0',
        align === 'center' && 'left-1/2 -translate-x-1/2',
        align === 'right' && 'right-0',
      )}
    >
      <p className="txt-faint text-[10.5px] font-semibold uppercase tracking-wider">{label}</p>
      <p className="txt font-display text-[13px] font-bold">{value}</p>
    </div>
  );
}

/* ------------------------------------------------------------
   Bar chart — CSS bars, one colour, values on hover
   ------------------------------------------------------------ */

interface BarChartProps {
  data: { label: string; value: number }[];
  formatValue: (value: number) => string;
  /** Accessible description of what the chart shows. */
  caption: string;
  color?: string;
  className?: string;
}

export function BarChart({ data, formatValue, caption, color = 'var(--accent)', className }: BarChartProps) {
  const [hovered, setHovered] = useState<Tooltip | null>(null);
  const max = Math.max(...data.map(point => point.value), 1);

  return (
    <figure className={cn('m-0', className)}>
      <figcaption className="sr-only">{caption}</figcaption>
      <div className="flex h-[150px] items-end gap-2">
        {data.map((point, index) => {
          const height = Math.max(4, (point.value / max) * 100);
          const active = hovered?.index === index;
          return (
            <div
              key={point.label}
              className="relative flex h-full flex-1 flex-col justify-end"
              onMouseEnter={() =>
                setHovered({ index, label: point.label, value: formatValue(point.value) })
              }
              onMouseLeave={() => setHovered(null)}
            >
              {active && (
                <TooltipBubble
                  label={point.label}
                  value={formatValue(point.value)}
                  align={index === 0 ? 'left' : index === data.length - 1 ? 'right' : 'center'}
                />
              )}
              <div
                className="w-full rounded-t-md motion-safe:transition-all motion-safe:duration-300"
                style={{
                  height: `${height}%`,
                  background: color,
                  opacity: hovered && !active ? 0.45 : 1,
                }}
              />
            </div>
          );
        })}
      </div>

      <div className="bd mt-2 flex gap-2 border-t pt-2">
        {data.map(point => (
          <div key={point.label} className="min-w-0 flex-1 text-center">
            <p className="txt-faint truncate text-[10.5px] font-semibold" title={point.label}>
              {point.label}
            </p>
            <p className="txt-muted mt-0.5 text-[11px] font-bold">{formatValue(point.value)}</p>
          </div>
        ))}
      </div>
    </figure>
  );
}

/* ------------------------------------------------------------
   Line / area chart — SVG, optional comparison series
   ------------------------------------------------------------ */

interface LineChartProps {
  data: { label: string; value: number; compare?: number }[];
  formatValue: (value: number) => string;
  caption: string;
  primaryLabel: string;
  compareLabel?: string;
  className?: string;
}

const CHART_W = 320;
const CHART_H = 120;

export function LineChart({
  data,
  formatValue,
  caption,
  primaryLabel,
  compareLabel,
  className,
}: LineChartProps) {
  const gradientId = useId();
  const [hovered, setHovered] = useState<number | null>(null);

  const values = data.flatMap(point => [point.value, point.compare ?? point.value]);
  const max = Math.max(...values) * 1.1;
  const min = Math.min(...values) * 0.9;
  const span = max - min || 1;

  const x = (index: number) => (index / Math.max(1, data.length - 1)) * CHART_W;
  const y = (value: number) => CHART_H - ((value - min) / span) * CHART_H;

  const toPath = (accessor: (point: (typeof data)[number]) => number) =>
    data.map((point, index) => `${index === 0 ? 'M' : 'L'} ${x(index)} ${y(accessor(point))}`).join(' ');

  const linePath = toPath(point => point.value);
  const areaPath = `${linePath} L ${CHART_W} ${CHART_H} L 0 ${CHART_H} Z`;
  const comparePath = data.some(point => point.compare !== undefined)
    ? toPath(point => point.compare ?? point.value)
    : null;

  return (
    <figure className={cn('m-0', className)}>
      <figcaption className="sr-only">{caption}</figcaption>

      <div className="relative">
        {hovered !== null && (
          <div
            className="pointer-events-none absolute top-0 z-10 -translate-x-1/2"
            style={{ left: `${(hovered / Math.max(1, data.length - 1)) * 100}%` }}
          >
            <div className="surface bd w-max rounded-lg border px-2.5 py-1.5 shadow-lg">
              <p className="txt-faint text-[10.5px] font-semibold uppercase tracking-wider">
                {data[hovered].label}
              </p>
              <p className="txt font-display text-[13px] font-bold">
                {formatValue(data[hovered].value)}
              </p>
              {data[hovered].compare !== undefined && compareLabel && (
                <p className="txt-muted text-[11px] font-medium">
                  {compareLabel}: {formatValue(data[hovered].compare as number)}
                </p>
              )}
            </div>
          </div>
        )}

        <svg
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          preserveAspectRatio="none"
          className="h-[130px] w-full"
          role="img"
          aria-label={caption}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </linearGradient>
          </defs>

          <path d={areaPath} fill={`url(#${gradientId})`} />

          {comparePath && (
            <path
              d={comparePath}
              fill="none"
              stroke="var(--muted)"
              strokeWidth="1.5"
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
            />
          )}

          <path
            d={linePath}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />

          {data.map((point, index) => (
            <circle
              key={point.label}
              cx={x(index)}
              cy={y(point.value)}
              r={hovered === index ? 4 : 2.5}
              fill="var(--accent)"
              stroke="var(--surface)"
              strokeWidth="1.5"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>

        {/* Hover targets sit above the SVG so pointer areas stay rectangular */}
        <div className="absolute inset-0 flex">
          {data.map((point, index) => (
            <div
              key={point.label}
              className="flex-1"
              onMouseEnter={() => setHovered(index)}
              onMouseLeave={() => setHovered(null)}
            />
          ))}
        </div>
      </div>

      <div className="mt-1.5 flex justify-between">
        {data.map(point => (
          <span key={point.label} className="txt-faint text-[10.5px] font-semibold">
            {point.label}
          </span>
        ))}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="txt-muted flex items-center gap-1.5 text-[11px] font-semibold">
          <span className="h-0.5 w-4 rounded-full" style={{ background: 'var(--accent)' }} />
          {primaryLabel}
        </span>
        {compareLabel && (
          <span className="txt-faint flex items-center gap-1.5 text-[11px] font-semibold">
            <span className="h-0.5 w-4 rounded-full border-t-2 border-dashed" style={{ borderColor: 'var(--muted)' }} />
            {compareLabel}
          </span>
        )}
      </div>
    </figure>
  );
}

/* ------------------------------------------------------------
   Donut chart — SVG arcs with a text legend
   ------------------------------------------------------------ */

interface DonutChartProps {
  data: { label: string; value: number }[];
  formatValue: (value: number) => string;
  caption: string;
  className?: string;
}

export function DonutChart({ data, formatValue, caption, className }: DonutChartProps) {
  const [hovered, setHovered] = useState<number | null>(null);
  const total = data.reduce((sum, point) => sum + point.value, 0) || 1;

  const radius = 54;
  const circumference = 2 * Math.PI * radius;

  // Each arc starts where the previous one ended, so the offsets are a running
  // sum. Built with `reduce` rather than a `let` the map callback increments:
  // mutating a variable that outlives the render is what
  // `react-hooks/immutability` forbids, and under concurrent rendering a
  // half-updated cursor would draw overlapping arcs.
  const segments = data.reduce<
    Array<(typeof data)[number] & {
      index: number;
      color: string;
      dash: number;
      offset: number;
      percent: number;
    }>
  >((accumulated, point, index) => {
    const fraction = point.value / total;
    const previous = accumulated[index - 1];
    accumulated.push({
      ...point,
      index,
      color: SERIES_COLORS[index % SERIES_COLORS.length],
      dash: fraction * circumference,
      offset: previous ? previous.offset + previous.dash : 0,
      percent: fraction * 100,
    });
    return accumulated;
  }, []);

  return (
    <figure className={cn('m-0 flex flex-col items-center gap-4 sm:flex-row sm:items-center', className)}>
      <figcaption className="sr-only">{caption}</figcaption>

      <div className="relative shrink-0">
        <svg viewBox="0 0 140 140" className="h-[140px] w-[140px]" role="img" aria-label={caption}>
          <circle cx="70" cy="70" r={radius} fill="none" stroke="var(--border)" strokeWidth="16" />
          {segments.map(segment => (
            <circle
              key={segment.label}
              cx="70"
              cy="70"
              r={radius}
              fill="none"
              stroke={segment.color}
              strokeWidth={hovered === segment.index ? 20 : 16}
              strokeDasharray={`${segment.dash} ${circumference - segment.dash}`}
              strokeDashoffset={-segment.offset}
              transform="rotate(-90 70 70)"
              opacity={hovered !== null && hovered !== segment.index ? 0.4 : 1}
              className="motion-safe:transition-all motion-safe:duration-200"
              onMouseEnter={() => setHovered(segment.index)}
              onMouseLeave={() => setHovered(null)}
            />
          ))}
        </svg>

        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <p className="txt-faint text-[10px] font-bold uppercase tracking-wider">
              {hovered === null ? 'Total' : segments[hovered].label}
            </p>
            <p className="txt font-display text-[15px] font-extrabold leading-tight">
              {formatValue(hovered === null ? total : segments[hovered].value)}
            </p>
          </div>
        </div>
      </div>

      <ul className="min-w-0 flex-1 space-y-1.5">
        {segments.map(segment => (
          <li
            key={segment.label}
            className="flex items-center gap-2"
            onMouseEnter={() => setHovered(segment.index)}
            onMouseLeave={() => setHovered(null)}
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: segment.color }}
              aria-hidden="true"
            />
            <span className="txt-muted min-w-0 flex-1 truncate text-[12px] font-medium">
              {segment.label}
            </span>
            <span className="txt text-[12px] font-bold">{Math.round(segment.percent)}%</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/* ------------------------------------------------------------
   Funnel — CSS bars with conversion rates between steps
   ------------------------------------------------------------ */

interface FunnelChartProps {
  /** `value` is optional — a funnel counted in records has no money on it. */
  data: { label: string; count: number; value?: number }[];
  formatValue: (value: number) => string;
  caption: string;
  className?: string;
}

export function FunnelChart({ data, formatValue, caption, className }: FunnelChartProps) {
  const max = Math.max(...data.map(step => step.count), 1);

  return (
    <figure className={cn('m-0 space-y-2', className)}>
      <figcaption className="sr-only">{caption}</figcaption>
      {data.map((step, index) => {
        const width = Math.max(6, (step.count / max) * 100);
        const previous = index > 0 ? data[index - 1].count : null;
        const conversion = previous ? Math.round((step.count / previous) * 100) : null;

        return (
          <div key={step.label}>
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <span className="txt text-[12px] font-semibold">{step.label}</span>
              <span className="txt-muted text-[11.5px] font-medium">
                {step.count.toLocaleString('en-US')}
                {step.value !== undefined && (
                  <span className="txt-faint"> · {formatValue(step.value)}</span>
                )}
                {conversion !== null && (
                  <span className="txt-faint"> · {conversion}% conv.</span>
                )}
              </span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full" style={{ background: 'var(--border)' }}>
              <div
                className="h-full rounded-full motion-safe:transition-[width] motion-safe:duration-500"
                style={{
                  width: `${width}%`,
                  background: SERIES_COLORS[index % SERIES_COLORS.length],
                }}
              />
            </div>
          </div>
        );
      })}
    </figure>
  );
}
