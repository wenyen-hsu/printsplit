# PrintSplit

[![tests](https://github.com/wenyen-hsu/printsplit/actions/workflows/tests.yml/badge.svg)](https://github.com/wenyen-hsu/printsplit/actions/workflows/tests.yml)

**Split any mesh for 3D printing and snap the parts back together —
rigidly or with articulated joints.**

PrintSplit is a free, open-source Blender extension (4.2+): draw a line
across a mesh in the viewport to cut it into two watertight pieces, then
generate an interlocking male/female joint (dovetail key or cylinder pin)
across the cut so the printed parts assemble without glue.

Inspired by the workflow of commercial split-and-key add-ons; this is an
independent clean-room implementation, GPL-3.0 licensed.

## Features

- **Draw-to-cut** — drag a straight line or a freehand stroke across the
  mesh; only the geometry under the stroke is cut. Both halves come out
  watertight, with the total volume conserved (the cut is pure `bmesh`
  bisection — no boolean, no kerf).
- **One-click joints** — select the two halves and generate a joint sized
  automatically from the cut cross-section, with print-ready clearance in
  millimetres (default 0.15 mm for FDM; use 0.05–0.10 mm for resin).
- **Fixed joint shapes** — dovetail (mechanically locks, slide-in
  assembly), cylinder pin (alignment + press fit) and cross key
  (anti-rotation pin). The dovetail defaults to a full-width **rail**
  that runs across the whole cut and ends flush with the surface —
  assembled parts have no voids; a local **key** style is also
  available.
- **Movable joints** (action-figure style, snap-fit assembly):
  - **Ball socket** — all-direction rotation + twist; the socket opening
    ratio sets the snap retention, the ROM angle dishes the surrounding
    face so the joint really swings;
  - **Hinge** — single-axis bend with a hard stop at the range-of-motion
    limit; a full-width barrel that slides in from the side, no loose
    pin;
  - **Swivel** — mushroom snap pivot, twist-only (turn a head, rotate a
    waist), with optional elastic slits for easier snap-in;
  - **Double ball** — both halves get sockets plus a separate dumbbell
    connector for maximum articulation; undo removes the connector too.
  Movable joints default to a larger articulation clearance (0.3 mm) and
  enforce the Exact solver. Snap retention is validated against a PLA
  press-fit window and warns when a joint is too small to hold.
- **Live preview** — attach the joint as unapplied boolean modifiers,
  tweak everything in the F9 panel while watching the real result, then
  Confirm or Cancel.
- Shapes live in a small registry (`joints/`), so new shapes are one
  file away.
- **Adjust everything live** — all joint parameters (shape, scale, depth,
  rotation, flip, clearance, boolean solver) are operator properties:
  tweak them in the F9 / *Adjust Last Operation* panel and the joint
  rebuilds from the pre-joint state.
- **Non-destructive** — every cut and joint backs up the previous mesh
  datablock. *Undo Last* / *Delete All Cuts* restore your model exactly,
  even after saving and reopening the file.
- **Built for heavy meshes** — NumPy prefiltering plus per-segment bmesh
  bisection cuts a 12-segment freehand stroke through a 540k-face mesh in
  ~2.4 s.

## Install

```bash
blender --command extension build
```

then in Blender: *Edit → Preferences → Get Extensions → Install from
Disk…* and pick the generated `printsplit-0.1.0.zip`.

## Use

1. Open the **PrintSplit** tab in the 3D viewport sidebar (N-panel).
2. Select your object, click **Draw Cut**, and drag a line across it
   (press **S** during the tool to toggle straight/freehand).
3. Select the two halves and click **Generate Joint**. Adjust the shape
   and fit in the F9 panel.
4. Export both halves and print. The dovetail slides in from the side and
   locks; the cylinder pin presses straight in.

## Notes & limitations

- The male peg goes on the **active** object; enable **Flip** to swap.
- Joints can be generated even after moving the halves apart — placement
  is computed in the halves' shared local space.
- Works on curved cuts: the joint sits along the average cut normal. A
  warning appears when the cut surface is too curved to seat a joint.
- Hollow shells (nested cap contours) are capped per-contour; slicers
  handle the coincident-face result, but solid meshes are recommended.
- Clearance is real millimetres, honoring the scene unit scale.

## Development

```bash
"/Applications/Blender 4.5.app/Contents/MacOS/Blender" \
    --background --factory-startup --python tests/run_tests.py
```

The test suite asserts watertightness, volume conservation, joint fit
(zero intersection at positive clearance) and history restoration. Core
logic (`core/`, `joints/`) is context-free and runs headless.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
