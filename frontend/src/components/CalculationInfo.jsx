import { useId, useState } from 'react';
import { Info } from 'lucide-react';

export default function CalculationInfo({
  title,
  meaning,
  formula,
  inputs,
  period,
  provenance = 'Calculated locally from included transactions.',
  caveat,
}) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={`How ${title} is calculated`}
        aria-expanded={open}
        aria-controls={id}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={event => {
          event.stopPropagation();
          setOpen(true);
        }}
        onKeyDown={event => {
          if (event.key === 'Escape') {
            setOpen(false);
            event.currentTarget.blur();
          }
        }}
        className="w-7 h-7 -m-1 grid place-items-center rounded-full text-white/28 hover:text-cyan-200/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/50"
      >
        <Info size={13} />
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute z-50 left-1/2 top-full mt-2 w-[min(330px,calc(100vw-2rem))] -translate-x-1/2 rounded-2xl border border-white/[0.16] bg-[#102342]/[0.98] p-4 text-left shadow-2xl"
          onMouseDown={event => event.preventDefault()}
        >
          <span className="block text-white/80 text-sm">{title}</span>
          <span className="mt-1.5 block text-white/45 text-xs leading-relaxed">{meaning}</span>
          <span className="mt-3 block text-white/25 text-[0.65rem] uppercase tracking-wide">Formula</span>
          <span className="mt-1 block rounded-lg bg-black/20 px-2.5 py-2 font-mono text-cyan-100/65 text-[0.68rem]">{formula}</span>
          <span className="mt-3 block text-white/35 text-[0.7rem]"><span className="text-white/55">Inputs:</span> {inputs}</span>
          <span className="mt-1 block text-white/35 text-[0.7rem]"><span className="text-white/55">Period:</span> {period}</span>
          <span className="mt-1 block text-white/35 text-[0.7rem]"><span className="text-white/55">Source:</span> {provenance}</span>
          {caveat && <span className="mt-2 block text-amber-100/45 text-[0.68rem] leading-relaxed">{caveat}</span>}
        </span>
      )}
    </span>
  );
}
