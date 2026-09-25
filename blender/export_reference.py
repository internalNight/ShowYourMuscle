"""Export a static, named reference subset from Z-Anatomy's Blender atlas.

Run after loading .cache/z-anatomy/Startup.blend in Blender. The resulting GLB
is a CC BY-SA 4.0 derivative; see public/models/NOTICE-z-anatomy.txt.
"""

from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "models" / "z_anatomy_reference.glb"
OUT.parent.mkdir(parents=True, exist_ok=True)

BONES = {
    "Clavicle", "Scapula", "Humerus", "Radius", "Ulna", "Femur", "Tibia", "Fibula",
    "Hip bone", "Sacrum", "Patella", "Calcaneus", "Body of sternum", "Manubrium of sternum",
}
MUSCLES = {
    "(Abdominal part of pectoralis major muscle)",
    "Clavicular head of pectoralis major muscle",
    "Sternocostal head of pectoralis major muscle",
    "Acromial part of deltoid muscle",
    "Clavicular part of deltoid muscle",
    "Scapular spinal part of deltoid muscle",
    "Long head of biceps brachii",
    "Short head of biceps brachii",
    "Lateral head of triceps brachii",
    "Long head of triceps brachii",
    "Medial head of triceps brachii",
    "Gluteus maximus muscle",
    "Rectus abdominis muscle",
    "Rectus femoris muscle",
    "Vastus intermedius muscle",
    "Vastus lateralis muscle",
    "Vastus medialis muscle",
    "Long head of biceps femoris",
    "Short head of biceps femoris",
    "Semimembranosus muscle",
    "Semitendinosus muscle",
    "Lateral head of gastrocnemius",
    "Medial head of gastrocnemius",
    "Soleus muscle",
    "Tibialis anterior muscle",
    "Gluteus medius muscle",
    "External abdominal oblique muscle",
    "Latissimus dorsi muscle",
    "Ascending part of trapezius muscle",
    "Transverse part of trapezius muscle",
    "Descending part of trapezius muscle",
    "Serratus anterior muscle",
    "Rhomboid major muscle",
    "Brachialis muscle",
    "Brachioradialis muscle",
    "Longissimus thoracis muscle",
}

bpy.ops.object.select_all(action="DESELECT")
chosen = []
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    base = obj.name[:-2] if obj.name.endswith((".l", ".r")) else obj.name
    is_bone = base in BONES or base.startswith("Vertebra ") or base.endswith(" rib")
    if not is_bone and base not in MUSCLES:
        continue
    if len(obj.data.vertices) < 100:
        continue
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.select_set(True)
    chosen.append(obj)

if len(chosen) < 50:
    raise RuntimeError(f"Expected >= 50 anatomical meshes, found {len(chosen)}")
bpy.context.view_layer.objects.active = chosen[0]
bpy.ops.export_scene.gltf(
    filepath=str(OUT),
    export_format="GLB",
    use_selection=True,
    export_materials="NONE",
    export_extras=False,
)
print(f"EXPORTED_REFERENCE {len(chosen)} meshes {OUT} {OUT.stat().st_size} bytes")
