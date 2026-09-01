"""SegAudit — quality control and triage for medical image segmentation.

A segmentation model draws outlines on a scan. Most of the time it is right.
Sometimes it is badly wrong, and without a reference outline nobody can tell
which cases those are. SegAudit is the layer that answers that question:
it quantifies how uncertain each segmentation is, predicts which ones are
likely to be wrong, and turns that into a short, prioritised review list.

The package is organised so that every capability is a plain Python function
reachable through :mod:`segaudit.api`. Command-line entry points, the review
app, and any future service all call that same API; none of them contain
pipeline logic of their own.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
