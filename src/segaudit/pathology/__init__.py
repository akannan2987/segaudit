"""Track P — pathology: 2D whole-slide images and their tiles.

Everything that only makes sense for *slides* lives here: reading whole-slide
images with microns-per-pixel and magnification, cutting tiles, the synthetic
H&E-like tile generator, stain handling, nuclei and tissue models, cell graphs
and spatial statistics. Everything that works on *any* segmentation lives one
level up, in the shared core.

Two units matter on this track. A **tile** is what a model looks at; a
**slide** is what a reviewer decides about. Shared tables carry both through
``unit_kind``.
"""

TRACK = "pathology"
UNIT_KIND = "tile"  # models work on tiles; slide-level decisions aggregate them
