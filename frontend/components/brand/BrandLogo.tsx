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
  /**
   * What the mark stands for *here*.
   *
   * The artwork is the same on both layers, but the alt text is not:
   * on the workspace this mark means S3K Platforms, and inside the CRM
   * it means S3K CRM. Defaults to the CRM, which is where most of its
   * uses are.
   */
  label?: string;
}

export default function BrandLogo({
  variant = 'wordmark',
  className,
  priority = false,
  label = BRAND.name,
}: BrandLogoProps) {
  const isIcon = variant === 'icon';
  const src = isIcon ? logoIcon : logoWordmark;

  return (
    <span
      className={cn(
        'relative block shrink-0 overflow-hidden rounded-xl bg-white',
        isIcon ? 'h-9 w-9' : 'h-9 aspect-[1188/270]',
        className,
      )}>
      <Image
        src={src}
        alt={`${label} logo`}
        fill
        sizes={isIcon ? '36px' : '160px'}
        priority={priority}
        className='object-contain object-center p-0.5'
      />
    </span>
  );
}
