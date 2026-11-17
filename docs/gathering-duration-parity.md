# Gathering duration parity

Gathering (`taskType == 3`) now follows the original client's
`Script_3253_GetVillagerTaskDuration` arithmetic:

1. Read at most the first 18 saved skill slots, counting matching task skills.
2. Start a float32 factor at 1 and subtract the authored `professionMultiplier`
   once per matching rank, rounding to float32 after each subtraction.
3. Clamp the factor to at least 0.25, multiply by the float32 base duration,
   then truncate the float32 product to integer seconds.

For example, a 100-second task with three matching 0.1 reductions produces
69 seconds with native rounding, whereas exact decimal arithmetic gives 70.
Skills after slot 18 must not change the native preview or server deadline.

The reference was checked against the original client library SHA256
`066a8fe3b0d90473c9138fba2aa3a3fcf3c22c55f977c567d4c0016966d2edb9`:
duration routine at `0x449f5c`, float32 subtraction at `0x44a038`, quarter-floor
clamp at `0x44a04c` through `0x44a068`, and product/truncation at
`0x44a06c` through `0x44a07c`. The library and authored game data are not
included in this change.

The existing start path assigns both response and saved deadlines. There is
no post-start timer rewrite. Existing jobs, costs, rewards, other task families
and save formats retain their current behavior.

`tests/test_original_gathering_duration.py` uses synthetic definitions to cover
rank/origin/key variants, float rounding, slot limits, saved deadlines, existing
jobs and early-harvest rejection. This is backend regression coverage, not a
new claim of physical-device gameplay validation or a gathering crash fix.
