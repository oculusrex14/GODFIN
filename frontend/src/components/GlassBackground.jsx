import { motion } from "framer-motion";

export function GlassBackground() {
  return (
    <div className="fixed inset-0 z-0">
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(135deg, #0c1929 0%, #0f2847 20%, #122a4e 35%, #1a3a5c 50%, #163550 65%, #0d2744 80%, #0a1f3a 100%)",
        }}
      />
      <motion.div
        animate={{ x: [0, 30, -20, 0], y: [0, -20, 30, 0], scale: [1, 1.1, 0.95, 1] }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
        className="absolute top-[-10%] right-[10%] w-[500px] h-[500px] rounded-full opacity-30"
        style={{ background: "radial-gradient(circle, rgba(100,200,255,0.3) 0%, transparent 70%)" }}
      />
      <motion.div
        animate={{ x: [0, -30, 20, 0], y: [0, 20, -30, 0], scale: [1, 0.95, 1.1, 1] }}
        transition={{ duration: 25, repeat: Infinity, ease: "easeInOut" }}
        className="absolute bottom-[-5%] left-[5%] w-[600px] h-[600px] rounded-full opacity-25"
        style={{ background: "radial-gradient(circle, rgba(160,120,255,0.25) 0%, transparent 70%)" }}
      />
      <motion.div
        animate={{ x: [0, 20, -10, 0], y: [0, -15, 20, 0] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
        className="absolute top-[40%] left-[40%] w-[400px] h-[400px] rounded-full opacity-20"
        style={{ background: "radial-gradient(circle, rgba(80,220,200,0.2) 0%, transparent 70%)" }}
      />
    </div>
  );
}
