import { memo } from "react";
import { ChevronDown } from "lucide-react";

export const GlassSelect = memo(function GlassSelect({ value, onChange, options }) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none bg-white/[0.08] backdrop-blur-[16px] border border-white/[0.15] text-white/80 text-[0.8rem] rounded-[14px] px-4 py-2 pr-10 focus:outline-none focus:border-cyan-400/30 cursor-pointer transition-all hover:bg-white/[0.12]"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-[#1a2a4a] text-white">
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30 pointer-events-none" />
    </div>
  );
});
