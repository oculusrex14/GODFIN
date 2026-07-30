export default function GodfinBrand({
  compact = false,
  showTagline = true,
  className = '',
}) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <img
        src="/godfin-mark.svg"
        alt=""
        aria-hidden="true"
        className={compact ? 'h-9 w-9 rounded-xl' : 'h-12 w-12 rounded-2xl'}
      />
      <div className="min-w-0">
        <div
          className={`${compact ? 'text-[1.08rem]' : 'text-[1.5rem]'} tracking-[0.02em] leading-none font-semibold`}
          aria-label="GODFIN"
        >
          <span className="text-white/95">GOD</span>
          <span className="bg-gradient-to-r from-[#54E1D0] to-[#17C3B2] bg-clip-text text-transparent">FIN</span>
        </div>
        {showTagline && (
          <p className={`mt-1 uppercase text-white/28 ${compact ? 'text-[0.48rem] tracking-[0.12em]' : 'text-[0.55rem] tracking-[0.15em]'}`}>
            Local-first. Private. In control.
          </p>
        )}
      </div>
    </div>
  );
}
