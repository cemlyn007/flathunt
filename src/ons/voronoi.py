import collections
import itertools
import numpy as np
import scipy.spatial

__all__ = [
    "get_all_face_vertices",
    "get_polylines",
]


def get_all_face_vertices(
    voronoi: scipy.spatial.Voronoi,
) -> list[list[tuple[tuple[float, float], tuple[float, float]]]]:
    """
    Returns a list where each element is a list of edges for the corresponding Voronoi cell.
    Each edge is a tuple of two endpoints ((x, y), (x, y)).
    """
    faces = [[] for _ in range(len(voronoi.points))]
    center = voronoi.points.mean(axis=0)
    ptp_bound = np.ptp(voronoi.points, axis=0)
    for point_idx, simplex in zip(
        voronoi.ridge_points, voronoi.ridge_vertices, strict=True
    ):
        simplex = np.asarray(simplex)
        if all(v >= 0 for v in simplex):
            edge = (
                tuple(voronoi.vertices[simplex[0]].tolist()),
                tuple(voronoi.vertices[simplex[1]].tolist()),
            )
        else:
            finite_indices = [v for v in simplex if v >= 0]
            i = finite_indices[0]
            t = voronoi.points[point_idx[1]] - voronoi.points[point_idx[0]]
            t /= np.linalg.norm(t)
            n = np.array([-t[1], t[0]])
            midpoint = voronoi.points[point_idx].mean(axis=0)
            direction = np.sign(np.dot(midpoint - center, n)) * n
            if voronoi.furthest_site:
                direction = -direction
            aspect_factor = (
                abs(ptp_bound.max() / ptp_bound.min()) if ptp_bound.min() != 0 else 1
            )
            far_point = (
                voronoi.vertices[i] + direction * ptp_bound.max() * aspect_factor
            )
            edge = (tuple(voronoi.vertices[i].tolist()), tuple(far_point.tolist()))
        if point_idx[0] == point_idx[1]:
            raise ValueError("Point indices should not be equal")
        faces[point_idx[0]].append(edge)
        faces[point_idx[1]].append(edge)
    # min ridge point is actually 1.
    return faces


def get_polylines(
    face_edges: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[float, float]]:
    face_edges = face_edges.copy()
    vertices = list(itertools.chain.from_iterable(face_edges))
    lone_vertices = []
    for vertex, count in collections.Counter(vertices).most_common():
        if count == 1:
            lone_vertices.append(vertex)
    if len(lone_vertices) != 0:
        # We have a boundary point that we'd like to stitch together :D
        # This is an assumption to an extent, and I should more concretely
        #  assert this.
        if len(lone_vertices) != 2:
            raise ValueError(
                f"Expected exactly 2 lone vertices, but found {len(lone_vertices)}: {lone_vertices}"
            )
        face_edges.append(tuple(lone_vertices))
    vertex = face_edges.pop()
    belt = [vertex[0], vertex[1]]
    frontier = [(vertex[0], True), (vertex[1], False)]
    while len(frontier) > 1:
        # print(frontier, face_edges)
        vertex, append = frontier.pop()
        for e in face_edges:
            if any(vertex == v for v in e):
                other_vertex = e[(e.index(vertex) + 1) % 2]
                face_edges.remove(e)
                if append:
                    frontier.append((other_vertex, True))
                    belt.insert(0, other_vertex)
                else:
                    frontier.insert(0, (other_vertex, False))
                    belt.append(other_vertex)
                break
        else:
            if len(frontier) == 1 and len(face_edges) == 0:
                # We have a closed loop
                if vertex == belt[-1] and frontier[0][0] == belt[0]:
                    pass
                elif vertex == belt[0] and frontier[0][0] == belt[-1]:
                    pass
                else:
                    raise ValueError("Unexpected vertex in closed loop")
            else:
                raise ValueError("No edge found for vertex")
    # Now reverse if the wrong winding order
    if (
        sum(
            (ax - bx) * (ay + by)
            for (ax, ay), (bx, by) in itertools.pairwise(belt + [belt[0]])
        )
        > 0.0
    ):
        belt.reverse()
    return belt
