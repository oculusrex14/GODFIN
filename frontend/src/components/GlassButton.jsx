import { memo } from "react";
import { motion } from "framer-motion";

const variants = {
  primary: "bg-cyan-500/20 text-cyan-300 border-cyan-400/20 hover:bg-cyan-500/30 shadow-[0_0_16px_rgba(34,211,238,0.1)]",
  secondary: "bg-white/[0.08] text-white/70 border-white/[0.12] hover:bg-white/[0.14] hover:text-white",
  danger: "bg-rose-500/15 text-rose-300 border-rose-400/20 hover:bg-rose-500/25",
  ghost: "bg-transparent text-white/50 border-transparent hover:bg-white/[0.06] hover:text-white/80",
};

export const GlassButton = memo(function GlassButton({
  children,
  icon,
  variant = "primary",
  disabled = false,
  onClick,
  type = "button",
  className = "",
}) {
  return (
    <motion.button
      whileHover={{ scale: disabled ? 1 : 1.02 }}
      whileTap={{ scale: disabled ? 1 : 0.98 }}
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`
        flex items-center gap-2 px-4 py-2.5
        rounded-[14px] border backdrop-blur-[12px]
        text-[0.8rem] transition-all duration-200
        disabled:opacity-40 disabled:cursor-not-allowed
        cursor-pointer
        ${variants[variant]}
        ${className}
      `}
      style={{ fontWeight: 500 }}
    >
      {icon}
      {children}
    </motion.button>
  );
});
