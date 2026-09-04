import type { ComponentProps } from 'react';

function Badge({ className = '', ...props }: ComponentProps<'span'>) {
  return (
    <span
      className={`inline-flex w-fit shrink-0 items-center justify-center gap-1 rounded-full border px-2.5 py-1 font-mono text-[10px] font-semibold tracking-[0.08em] whitespace-nowrap ${className}`}
      {...props}
    />
  );
}

export { Badge };
