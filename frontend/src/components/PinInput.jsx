import { useState, useRef, useEffect } from 'react';

export default function PinInput({ length = 4, onComplete }) {
  const [digits, setDigits] = useState(Array(length).fill(''));
  const inputsRef = useRef([]);

  useEffect(() => {
    inputsRef.current[0]?.focus();
  }, []);

  function handleChange(index, value) {
    if (!/^\d?$/.test(value)) return;
    const next = [...digits];
    next[index] = value;
    setDigits(next);

    if (value && index < length - 1) {
      inputsRef.current[index + 1]?.focus();
    }

    if (value && index === length - 1) {
      const pin = next.join('');
      if (pin.length === length) onComplete(pin);
    }
  }

  function handleKeyDown(index, e) {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
  }

  function handlePaste(e) {
    e.preventDefault();
    const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length);
    if (!text) return;
    const next = Array(length).fill('');
    text.split('').forEach((ch, i) => { next[i] = ch; });
    setDigits(next);
    if (text.length === length) {
      onComplete(text);
    } else {
      inputsRef.current[text.length]?.focus();
    }
  }

  return (
    <div className="flex gap-3 justify-center" onPaste={handlePaste}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={(el) => (inputsRef.current[i] = el)}
          type="password"
          inputMode="numeric"
          enterKeyHint={i === length - 1 ? 'done' : 'next'}
          aria-label={`PIN digit ${i + 1}`}
          maxLength={1}
          value={d}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          className="w-14 h-14 touch-manipulation text-center text-[1.2rem] bg-white/[0.06] backdrop-blur-[12px] border border-white/[0.15] rounded-[16px] text-white/90 focus:outline-none focus:border-cyan-400/40 transition-all shadow-[inset_0_2px_4px_rgba(0,0,0,0.1)]"
          autoComplete="off"
        />
      ))}
    </div>
  );
}
