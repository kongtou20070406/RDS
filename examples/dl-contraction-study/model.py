"""Model definition for DL Contraction Study.

Control arm maintains strict contraction m < 1.
Treatment arm is modified by candidate research plans.
"""

def control(x):
    # Baseline: contractive operator with m = 19/20 < 1.0 everywhere
    return 19 * x / (20 * (1 + x))

def treatment(x):
    # Initial treatment candidate: genuine crossing for x >= 5
    return 6 * x / (5 * (1 + x))
