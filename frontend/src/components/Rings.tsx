/** Anneaux décoratifs autour de la sphère (rotatifs en CSS pur). */
export function DecorativeRings() {
  return (
    <>
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[56%]
                      w-[460px] h-[460px] rounded-full border border-cyan/[0.08]
                      pointer-events-none z-[1] animate-ring-spin">
        <div className="absolute -top-px left-[20%] w-3/5 h-0.5
                        bg-gradient-to-r from-transparent via-cyan to-transparent
                        shadow-[0_0_12px_var(--tw-shadow-color)] shadow-cyan-glow" />
      </div>
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[56%]
                      w-[380px] h-[380px] rounded-full border border-dashed border-cyan/[0.06]
                      pointer-events-none z-[1] animate-ring-spin-rev" />
    </>
  );
}
