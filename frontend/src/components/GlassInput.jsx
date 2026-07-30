import { memo, useId } from "react";

export const GlassInput = memo(function GlassInput({ label, className = "", id, ...props }) {
  const generatedId = useId();
  const inputId = id || generatedId;
  return (
    <div>
      {label && <label htmlFor={inputId} className="block text-white/40 text-[0.75rem] mb-1.5" style={{ fontWeight: 400 }}>{label}</label>}
      <input
        id={inputId}
        {...props}
        className={`w-full px-3.5 py-2.5 bg-white/[0.06] backdrop-blur-[12px] border border-white/[0.12] rounded-[14px] text-white/90 text-[0.85rem] placeholder-white/20 focus:outline-none focus:border-cyan-400/30 transition-all ${className}`}
      />
    </div>
  );
});
