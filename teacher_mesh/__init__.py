"""Teacher Mesh (spec §24, §27) — a health-gated panel of teachers backed by
the provider fabric.  See :mod:`teacher_mesh.mesh`."""

from .mesh import (
    Teacher,
    TeacherCallError,
    TeacherMesh,
    TeacherUnavailable,
)

__all__ = [
    "Teacher",
    "TeacherCallError",
    "TeacherMesh",
    "TeacherUnavailable",
]