"""FORK: code that exists only in the motor256 fork, not in KapJI/capital-gains-calculator.

Everything fork-specific lives in this package, so a rebase onto upstream has
one place to look. The few places where upstream files call into it are marked
with a `# FORK:` comment and listed in `FORK.md` at the repository root.

Nothing here runs unless the user passes one of the options added by
`cgt_calc.fork.options`, so a run without them behaves exactly like upstream.
"""
