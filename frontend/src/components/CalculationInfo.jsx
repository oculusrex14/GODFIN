import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
  const [position, setPosition] = useState(null);
  const buttonRef = useRef(null);
  const tooltipRef = useRef(null);
  const closeTimerRef = useRef(null);
  const id = useId();

  const cancelClose = useCallback(() => {
    if (closeTimerRef.current) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimerRef.current = window.setTimeout(() => setOpen(false), 100);
  }, [cancelClose]);

  const updatePosition = useCallback(() => {
    if (!buttonRef.current || !tooltipRef.current) return;
    const margin = 16;
    const gap = 8;
    const anchor = buttonRef.current.getBoundingClientRect();
    const tooltip = tooltipRef.current.getBoundingClientRect();
    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const left = Math.min(
      viewportWidth - tooltip.width - margin,
      Math.max(margin, anchor.left + (anchor.width - tooltip.width) / 2),
    );
    const spaceBelow = viewportHeight - anchor.bottom - gap - margin;
    const top = spaceBelow >= tooltip.height
      ? anchor.bottom + gap
      : Math.max(margin, anchor.top - tooltip.height - gap);
    setPosition({ left, top });
  }, []);

  useLayoutEffect(() => {
    if (open) updatePosition();
    return undefined;
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return undefined;
    const handleViewportChange = () => updatePosition();
    const handlePointerDown = (event) => {
      if (
        !buttonRef.current?.contains(event.target) &&
        !tooltipRef.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus({ preventScroll: true });
      }
    };
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open, updatePosition]);

  useEffect(() => () => cancelClose(), [cancelClose]);

  const tooltip = open ? (
    <div
      ref={tooltipRef}
      id={id}
      role="tooltip"
      onMouseEnter={cancelClose}
      onMouseLeave={scheduleClose}
      className="fixed z-[1000] max-h-[calc(100vh-2rem)] w-[min(330px,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-white/[0.16] bg-[#102342]/[0.98] p-4 text-left shadow-2xl"
      style={{
        left: position?.left ?? 0,
        top: position?.top ?? 0,
        visibility: position ? 'visible' : 'hidden',
      }}
    >
      <span className="block text-white/80 text-sm">{title}</span>
      <span className="mt-1.5 block text-white/45 text-xs leading-relaxed">{meaning}</span>
      <span className="mt-3 block text-white/25 text-[0.65rem] uppercase tracking-wide">Formula</span>
      <span className="mt-1 block rounded-lg bg-black/20 px-2.5 py-2 font-mono text-cyan-100/65 text-[0.68rem]">{formula}</span>
      <span className="mt-3 block text-white/35 text-[0.7rem]"><span className="text-white/55">Inputs:</span> {inputs}</span>
      <span className="mt-1 block text-white/35 text-[0.7rem]"><span className="text-white/55">Period:</span> {period}</span>
      <span className="mt-1 block text-white/35 text-[0.7rem]"><span className="text-white/55">Source:</span> {provenance}</span>
      {caveat && <span className="mt-2 block text-amber-100/45 text-[0.68rem] leading-relaxed">{caveat}</span>}
    </div>
  ) : null;

  return (
    <span
      className="inline-flex"
      onMouseEnter={() => {
        cancelClose();
        setOpen(true);
      }}
      onMouseLeave={scheduleClose}
    >
      <button
        ref={buttonRef}
        type="button"
        aria-label={`How ${title} is calculated`}
        aria-expanded={open}
        aria-controls={id}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={scheduleClose}
        onClick={event => {
          event.stopPropagation();
          setOpen(current => !current);
        }}
        onKeyDown={event => {
          if (event.key === 'Escape') {
            setOpen(false);
            event.stopPropagation();
            event.currentTarget.focus({ preventScroll: true });
          }
        }}
        className="w-7 h-7 -m-1 grid place-items-center rounded-full text-white/28 hover:text-cyan-200/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/50"
      >
        <Info size={13} />
      </button>
      {tooltip && createPortal(tooltip, document.body)}
    </span>
  );
}
