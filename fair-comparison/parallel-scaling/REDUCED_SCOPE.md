# Reduced Completion Scope

The full solver-only DC matrix remains unchanged: strong scaling at all planned
complexities and weak scaling at all worker counts, with three repetitions.

To control the measured cost of high-worker HSPICE process startup and license
scheduling, the remaining work is reduced to:

- Weak-scaling DC end-to-end: workers `1`, `8`, and `32`; one repetition; all
  five methods.
- Transient end-to-end supplement: workers `1`, `8`, and `32`; four vectors;
  one repetition; HSPICE independent, HSPICE `.alter`, official NGSPICE
  independent, and optimized NGSPICE independent.

The report must label these as sampled end-to-end and transient measurements;
they do not replace the complete solver-only scaling conclusions.
