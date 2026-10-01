# Exact whole-unit-disk coverage by rational sites

`geometry.unit_disk_rational_voronoi` proves that the declared rational centers,
with declared rational squared radius Q, cover the **entire closed unit disk**.
It establishes an upper bound for that construction. It does not establish a
matching unrestricted lower bound, global optimality, or research-policy gain.
This is an exact Python certificate rule, not native Lean verification.

The reusable RSI changes live in the verification framework: trusted proof rules
can declare supporting source files, and all framework declarations/certificates
share a bounded exact-JSON admission function. The disk backend is one consumer
and acceptance case for these mechanisms; neither mechanism has n=100 constants.

The statement kind is distinct from the existing quadtree rule:

```json
{"schema":1,"kind":"unit_disk_rational_voronoi","centers":[["0","0"]],"radius_squared":"1"}
```

```text
python -B scripts/rds_cli.py formal verify --spec examples/formal/unit_disk_rational_voronoi.json --tactics rational
```

## Why a finite certificate covers a continuous disk

For each distinct center c_i, construct its closed Voronoi cell using every
inequality `(c_j-c_i) dot x <= (|c_j|²-|c_i|²)/2`. Intersect with `[-1,1]²`,
which contains the disk, to obtain a compact convex polygon P_i. Exact rational
half-plane clipping preserves these intersections, including empty cells,
segments, points, coincident vertices and tangent boundaries.

Every extreme point of P_i intersected with the unit disk is either a vertex
of P_i inside the disk, or lies on the unit circle. Indeed, a nonvertex in the
open disk admits two distinct nearby points of P_i whose midpoint is that
point, so it cannot be extreme. Check all polygon vertices in the disk against
their cell's center. These are nearest-center distances because all Voronoi
inequalities hold; an uncovered such vertex is a genuine interior diagnostic.

It remains to cover the full unit circle. Cut it at **every** pairwise center
bisector intersection. Between consecutive cuts the ordering of all squared
distances is fixed, hence one center remains nearest and the squared nearest
distance is `1+|c_i|²-2 c_i dot x`. Its maximum on that closed arc occurs at an
endpoint or, for a nonzero center, its antipodal direction. A zero center gives
a constant on the arc. Include `(1,0)` for the case of no cuts and a constant
whole-circle function. Checking all cuts, all nonzero-center antipodes and
this fixed point therefore bounds the circle's continuous maximum, without
sampling. Extra inactive-center candidates are harmless.

Any covered circle point in P_i is also covered by center c_i, since c_i is a
nearest center there. Thus the closed ball at c_i contains every extreme point
of P_i intersected with the disk. A nonempty compact convex set in the plane
is the convex hull of its extreme points, including the lower-dimensional
cases; convexity of that ball gives coverage of the whole intersection.
All the Voronoi cells together contain the disk. This completes the argument.

For the bisector use v=c_j-c_i, V=|v|²>0, h=(|c_j|²-|c_i|²)/2. Intersections
exist exactly when Δ=V-h²>=0, and are `h v/V ± sqrt(Δ) Jv/V`, where J rotates
by 90 degrees. Their norm is exactly one. The distance checks reduce to
`a+b sqrt(Δ)<=0` with rational a,b,Δ. For b>0 this means a<=0 and b²Δ<=a²;
for b<0 it means a<=0 or a²<=b²Δ; for b=0 or Δ=0 compare a<=0 directly.
The antipodes use the same radical arithmetic. All equality cases are included.

## Replay and bindings

The core is a byte-preserved research implementation from the disk100 work
area, SHA-256 `bd9bf6c0d2b693bff575d77943f509d17b79424d0105982ffe30cf9e85b315b2`.
`rds_unit_disk_voronoi_core.py` retains that identity so original frozen core
certificates can replay. The RDS adapter adds statement validation and its
own certificate envelope, binding the statement, core, adapter and arithmetic
helpers. The framework verifier identity also includes the core's source.
The rule declares that core through the general `ProofRule.support_files` field;
the application-owned dependency manifest is exposed by `formal rules`. Authors
must declare complete supporting files; this is not automatic import discovery.

Generation uses floating point only to propose a covering center for a boundary
candidate. Every accepted inequality is exact; unsuccessful proposals fall
back to checking every center exactly. Frozen replay uses only recorded coverers
and exact arithmetic, regenerates the entire candidate list, and rejects missing,
extra or modified rows and changed input/source hashes. It never invokes the
generator or a floating proposal. Wrapping an original core certificate first
requires complete exact replay through `from_core_certificate` or:

```text
python -B scripts/rds_rational_voronoi_verify.py --spec <RDS-statement.json> --core-certificate <original-core-certificate.json> --output <adapter-result.json>
python -B scripts/rds_rational_voronoi_verify.py --spec <RDS-statement.json> --certificate <adapter-result.json> --output <replay.json>
```

The corresponding core statement uses `kind=unit_disk_cover`; all remaining
fields are identical. Conversion does not change centers, radius or the original
core certificate. Use the framework checker for framework certificate envelopes.

## Capability and parser bounds

Declarations have exactly schema, kind, centers and radius_squared. Support is
1..256 centers, coordinates in [-8,8], Q in [0,64], exact integer or rational/
decimal strings up to 160 characters, and at most 512 bits per parsed numerator
or denominator. Declarations/certificates have at most 2 MiB, 100000 JSON nodes
and depth 32. Booleans, floating values (including nonfinite ones), oversized
strings, invalid fractions, forged optimality fields and duplicate file keys
are rejected. Node admission bounds containers before adding their children.

These are verifier capability bounds, not restrictions on competing centers
in the original global-optimality problem. An invalid, unsupported or uncovered
input yields UNKNOWN without a coverage certificate; this adapter does not
implement formal FAIL certificates. PASS carries CERTIFICATE_CHECKED assurance.
Verification cost belongs to the authorized research budget. A faster checked
implementation alone does not demonstrate improved exploration policy.
