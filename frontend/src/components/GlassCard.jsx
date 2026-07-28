import { memo } from "react";
import { motion } from "framer-motion";

export const GlassCard = memo(function GlassCard({ children, className = "", delay = 0, animate = true }) {
  const content = (
    <div
      className={`
        relative overflow-hidden rounded-[20px]
        bg-white/[0.08] backdrop-blur-[24px]
        border border-white/[0.18]
        shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)]
        ${className}
      `}
    >
      {/* Top highlight line */}
      <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
      {children}
    </div>
  );

  if (!animate) {
    return content;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
    >
      {content}
    </motion.div>
  );
});
