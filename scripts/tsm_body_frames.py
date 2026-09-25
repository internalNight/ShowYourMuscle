"""Export proper Blender rigid frames for the TSM viewer conventions.

Both legacy viewer maps reflect OpenSim ground axes. Reflecting one local
model axis as well keeps each exported body rotation in SO(3). The local
coordinate convention is only for relative rigid motion, not anatomical
registration of a separate mesh.
"""

BODY_NAMES = ("thorax", "clavicle", "scapula", "humerus", "ulna", "radius", "hand")
LOCAL_FLIP = (-1, 1, 1)
Q_ROWS = {
    "bench": ((0, 0, 1), (0, 1, 0), (1, 0, 0)),
    "press": ((0, 0, 1), (-1, 0, 0), (0, 1, 0)),
}


def export_body_frames(body_set, state, viewer_position, convention):
    q_rows = Q_ROWS[convention]
    frames = {}
    for name in BODY_NAMES:
        transform = body_set.get(name).getTransformInGround(state)
        rotation = transform.R()
        rows = [[LOCAL_FLIP[col] * sum(q_rows[row][axis] * rotation.get(axis, col)
                                        for axis in range(3))
                 for col in range(3)] for row in range(3)]
        x, y, z = viewer_position(transform.p())
        frames[name] = {
            "translationM": [x, -z, y],
            "rotationRows": rows,
        }
    return frames
