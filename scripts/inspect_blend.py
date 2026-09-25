"""Print a compact inventory of a Blender anatomy file; run after opening it."""

from collections import Counter

import bpy

print("SCENES", len(bpy.data.scenes))
print("OBJECT_TYPES", dict(Counter(obj.type for obj in bpy.data.objects)))
print("COLLECTIONS", len(bpy.data.collections))
for group in sorted(bpy.data.collections, key=lambda item: len(item.all_objects), reverse=True)[:25]:
    print("COLLECTION", group.name, len(group.all_objects))
for obj in bpy.data.objects:
    if obj.type == "ARMATURE":
        print("ARMATURE", obj.name, len(obj.data.bones))
for obj in list(bpy.data.objects)[:35]:
    print("OBJECT", obj.name, obj.type)
