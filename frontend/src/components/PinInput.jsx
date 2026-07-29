import { useEffect, useRef, useState } from 'react';

export default function PinInput({
  minLength = 4,
  maxLength = 4,
  value,
  onChange,
  onComplete,
  autoSubmit = true,
  disabled = false,
  label = 'PIN',
}) {
  const [internalValue, setInternalValue] = useState('');
  const inputRef = useRef(null);
  const pin = value ?? internalValue;

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function updatePin(nextValue) {
    const next = nextValue.replace(/\D/g, '').slice(0, maxLength);
    if (value === undefined) {
      setInternalValue(next);
    }
    onChange?.(next);
    if (autoSubmit && next.length === maxLength) {
      onComplete?.(next);
    }
  }

  return (
    <input
      ref={inputRef}
      type="password"
      inputMode="numeric"
      enterKeyHint="done"
      aria-label={label}
      aria-describedby="pin-length-hint"
      minLength={minLength}
      maxLength={maxLength}
      pattern={`[0-9]{${minLength},${maxLength}}`}
      value={pin}
      disabled={disabled}
      onChange={(event) => updatePin(event.target.value)}
      autoComplete="off"
      className="w-full h-14 touch-manipulation text-center tracking-[0.45em] text-[1.2rem] bg-white/[0.06] backdrop-blur-[12px] border border-white/[0.15] rounded-[16px] text-white/90 focus:outline-none focus:border-cyan-400/40 disabled:opacity-50 transition-all shadow-[inset_0_2px_4px_rgba(0,0,0,0.1)]"
    />
  );
}
