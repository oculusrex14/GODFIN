import { useEffect, useRef, useState } from 'react';

export default function PinInput({
  minLength = 4,
  maxLength = 4,
  displayLength = null,
  value,
  onChange,
  onComplete,
  autoSubmit = true,
  disabled = false,
  label = 'PIN',
}) {
  const [internalValue, setInternalValue] = useState('');
  const [focused, setFocused] = useState(false);
  const [selection, setSelection] = useState(0);
  const inputRef = useRef(null);
  const pin = value ?? internalValue;
  const slotCount = displayLength || Math.max(minLength, Math.min(maxLength, pin.length));

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
    <div
      className={`relative flex min-h-14 items-center justify-center gap-2.5 sm:gap-3 transition-opacity ${
        disabled ? 'opacity-50' : ''
      }`}
      data-pin-slots={slotCount}
    >
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
        onChange={(event) => {
          updatePin(event.target.value);
          setSelection(event.target.selectionStart ?? event.target.value.length);
        }}
        onFocus={(event) => {
          setFocused(true);
          setSelection(event.target.selectionStart ?? pin.length);
        }}
        onBlur={() => setFocused(false)}
        onSelect={(event) => setSelection(event.currentTarget.selectionStart ?? pin.length)}
        autoComplete="off"
        className="absolute inset-0 z-10 h-full w-full cursor-text touch-manipulation opacity-[0.01]"
      />
      {Array.from({ length: slotCount }, (_, index) => {
        const active = focused && Math.min(selection, slotCount - 1) === index;
        return (
          <span
            key={index}
            aria-hidden="true"
            className={`grid h-14 w-12 sm:w-14 place-items-center rounded-[16px] border bg-white/[0.08] text-xl text-white/90 shadow-[inset_0_2px_4px_rgba(0,0,0,0.1)] transition-all ${
              active
                ? 'border-cyan-300/45 ring-2 ring-cyan-300/15'
                : 'border-white/[0.18]'
            }`}
          >
            {index < pin.length ? '•' : ''}
          </span>
        );
      })}
    </div>
  );
}
