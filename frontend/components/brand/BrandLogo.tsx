import Image from 'next/image';
import logoIcon from '@/public/s3k-logo.png';
import logoWordmark from '@/public/s3k-logo-wordmark.png';
import { BRAND } from '@/config/site';
import { cn } from '@/lib/utils';

/* ============================================================
   BRAND LOGO
   Source master is a square PNG with large white margins. We use
   pre-cropped public assets so both placements fit without CSS
   object-position hacks:
   - s3k-logo-icon.png      → brain mark (square)
   - s3k-logo-wordmark.png  → full wordmark (≈4.4:1)
   ============================================================ */

interface BrandLogoProps {
  variant?: 'wordmark' | 'icon';
  className?: string;
  priority?: boolean;
}

export default function BrandLogo({
  variant = 'wordmark',
  className,
  priority = false,
}: BrandLogoProps) {
  const isIcon = variant === 'icon';
  const src = isIcon ? logoIcon : logoWordmark;

  // #region agent log
  if (typeof window !== 'undefined') {
    fetch('http://127.0.0.1:7603/ingest/b1854439-59c0-42fc-8352-19484d0334d7', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Debug-Session-Id': '6b9d12',
      },
      body: JSON.stringify({
        sessionId: '6b9d12',
        runId: 'logo-fit-2',
        hypothesisId: 'A',
        location: 'BrandLogo.tsx:render',
        message: 'BrandLogo using cropped assets',
        data: {
          variant,
          srcW: src.width,
          srcH: src.height,
          ratio: Number((src.width / src.height).toFixed(3)),
        },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
  }
  // #endregion

  return (
    <span
      className={cn(
        'relative block shrink-0 overflow-hidden rounded-xl bg-white',
        isIcon ? 'h-9 w-9' : 'h-9 aspect-[1188/270]',
        className,
      )}>
      <Image
        src={src}
        alt={`${BRAND.name} logo`}
        fill
        sizes={isIcon ? '36px' : '160px'}
        priority={priority}
        className='object-contain object-center p-0.5'
      />
    </span>
  );
}
