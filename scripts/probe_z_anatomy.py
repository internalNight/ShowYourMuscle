"""Inspect candidate Z-Anatomy objects before selecting an export subset."""

import re

import bpy

PATTERNS = re.compile(
    r"pectoralis major|deltoid|biceps brachii|triceps brachii|gluteus maximus|"
    r"rectus femoris|vastus |biceps femoris|semitendinosus|semimembranosus|"
    r"gastrocnemius|rectus abdominis|humerus|femur|tibia|fibula|radius|ulna|"
    r"scapula|clavicle|pelvis|sternum|rib|vertebra",
    re.IGNORECASE,
)

for obj in bpy.data.objects:
    if obj.type != "MESH" or not PATTERNS.search(obj.name):
        continue
    if len(obj.data.vertices) < 100 or not obj.name.endswith((".l", ".r")):
        continue
    print("CANDIDATE", obj.name, len(obj.data.vertices), tuple(round(v, 4) for v in obj.dimensions))
