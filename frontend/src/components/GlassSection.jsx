export function GlassSection({ title, icon: Icon, children }) {
  return (
    <div className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]">
      <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/40 to-transparent" />
      <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-white/[0.08]">
        <Icon size={16} className="text-white/40" />
        <h2 className="text-white/60 text-[0.8rem]" style={{ fontWeight: 500 }}>{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}
