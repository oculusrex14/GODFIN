import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';

export function GlassSection({
  title,
  icon: Icon,
  children,
  collapsible = false,
  defaultExpanded = true,
  storageKey = null,
}) {
  const contentId = useId();
  const [expanded, setExpanded] = useState(() => {
    if (!collapsible || !storageKey) return defaultExpanded;
    const saved = window.localStorage.getItem(storageKey);
    return saved === null ? defaultExpanded : saved === 'true';
  });

  const toggleExpanded = () => {
    const next = !expanded;
    setExpanded(next);
    if (storageKey) window.localStorage.setItem(storageKey, String(next));
  };

  return (
    <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]">
      <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/40 to-transparent" />
      {collapsible ? (
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={toggleExpanded}
          className={`flex w-full items-center gap-2.5 px-5 py-3.5 text-left transition-colors hover:bg-white/[0.03] ${
            expanded ? 'border-b border-white/[0.08]' : ''
          }`}
        >
          <Icon size={16} className="text-white/40" />
          <span className="flex-1 text-white/60 text-[0.8rem] font-medium">{title}</span>
          <ChevronDown
            size={16}
            className={`text-white/30 transition-transform ${expanded ? 'rotate-180' : ''}`}
          />
        </button>
      ) : (
        <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-white/[0.08]">
          <Icon size={16} className="text-white/40" />
          <h2 className="text-white/60 text-[0.8rem]" style={{ fontWeight: 500 }}>{title}</h2>
        </div>
      )}
      {(!collapsible || expanded) && <div id={contentId} className="p-5">{children}</div>}
    </div>
  );
}
