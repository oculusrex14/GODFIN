import { memo } from "react";
import { motion } from "framer-motion";

export const StatCard = memo(function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color = "text-white",
  delay = 0,
  calculationInfo,
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.5 }}
      whileHover={{ scale: 1.02, y: -2 }}
      className="relative overflow-hidden rounded-[20px] bg-white/[0.08] backdrop-blur-[24px] border border-white/[0.18] shadow-[0_8px_32px_rgba(0,0,0,0.08),inset_0_1px_0_rgba(255,255,255,0.2)] p-4"
    >
      <div className="absolute top-0 left-4 right-4 h-[1px] bg-gradient-to-r from-transparent via-white/30 to-transparent" />
      <div className="flex items-center gap-2.5 mb-2">
        <Icon size={16} className={color} />
        <span className="text-white/40 text-[0.7rem] uppercase tracking-wider" style={{ fontWeight: 400 }}>{title}</span>
        {calculationInfo}
      </div>
      <p className="text-white/90 text-[1.4rem] tracking-tight" style={{ fontWeight: 300 }}>{value}</p>
      {subtitle && <p className="text-white/30 text-[0.7rem] mt-0.5">{subtitle}</p>}
    </motion.div>
  );
});

export default StatCard;
