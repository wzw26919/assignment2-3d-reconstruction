"""Run using Blender: blender -b -P scripts/render_views.py -- --glb ... --out ..."""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--glb', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--size', type=int, default=512)
    p.add_argument('--azimuths', type=int, default=24)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    args.out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.glb.resolve()))
    scene = bpy.context.scene
    # Freeze imported animation at its first frame and remove imported lighting/cameras.
    scene.frame_set(1)
    for obj in list(scene.objects):
        if obj.type in {'CAMERA', 'LIGHT'}:
            bpy.data.objects.remove(obj, do_unlink=True)
    meshes = [o for o in scene.objects if o.type == 'MESH' and not o.hide_render]
    if not meshes:
        raise RuntimeError('GLB contains no visible mesh')
    bpy.context.view_layer.update()
    corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(v[k] for v in corners) for k in range(3)])
    hi = Vector([max(v[k] for v in corners) for k in range(3)])
    center = (lo + hi) / 2
    extent = max(hi - lo)
    if not math.isfinite(extent) or extent <= 1e-8:
        raise RuntimeError('Invalid or degenerate bounding box')
    # Parent top-level imported objects once, preserving all relative transforms.
    root = bpy.data.objects.new('normalization', None)
    scene.collection.objects.link(root)
    for obj in list(scene.objects):
        if obj != root and obj.parent is None:
            obj.parent = root
    root.scale = (2 / extent,) * 3
    root.location = -center * (2 / extent)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 32
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 6
    scene.cycles.seed = 42
    # Ubuntu's Blender package can omit OpenImageDenoise; use deterministic samples.
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = 'RGB'
    # Keep world illumination independent of the visible background. Composite white
    # explicitly, rather than rendering the gray appearance of a dimmed world.
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    layers = tree.nodes.new('CompositorNodeRLayers')
    over = tree.nodes.new('CompositorNodeAlphaOver')
    over.inputs[0].default_value = 1
    over.inputs[1].default_value = (1, 1, 1, 1)
    composite = tree.nodes.new('CompositorNodeComposite')
    tree.links.new(layers.outputs['Image'], over.inputs[2])
    tree.links.new(over.outputs['Image'], composite.inputs['Image'])
    scene.world = bpy.data.worlds.new('world')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (1, 1, 1, 1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = 0.7
    # World-fixed lights preserve view consistency. No camera-following lights.
    for i, xyz in enumerate(((4, -4, 6), (-4, -2, 3), (0, 4, 5))):
        light = bpy.data.lights.new(f'area_{i}', 'AREA')
        light.energy = 350
        light.size = 5
        obj = bpy.data.objects.new(light.name, light)
        scene.collection.objects.link(obj)
        obj.location = xyz
        obj.rotation_euler = (-obj.location).to_track_quat('-Z', 'Y').to_euler()
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'Medium High Contrast' if bpy.app.version < (4, 0, 0) else 'None'
    camera = bpy.data.cameras.new('camera')
    camera.lens = 50
    camera.sensor_width = 36
    camera.sensor_fit = 'HORIZONTAL'
    cam = bpy.data.objects.new('camera', camera)
    scene.collection.objects.link(cam)
    scene.camera = cam
    frames = []
    for ring, elevation in enumerate((-20, 15, 50)):
        for azimuth in range(args.azimuths):
            theta = 2 * math.pi * azimuth / args.azimuths
            phi = math.radians(elevation)
            cam.location = (4 * math.cos(phi) * math.cos(theta),
                            4 * math.cos(phi) * math.sin(theta), 4 * math.sin(phi))
            cam.rotation_euler = (-cam.location).to_track_quat('-Z', 'Y').to_euler()
            bpy.context.view_layer.update()
            filename = f'r{ring}_{azimuth:03d}.png'
            scene.render.filepath = str(args.out / filename)
            bpy.ops.render.render(write_still=True)
            frames.append({'file_path': filename, 'ring': ring, 'azimuth': azimuth,
                           'elevation': elevation,
                           'transform_matrix': [list(row) for row in cam.matrix_world]})
    focal = args.size * camera.lens / camera.sensor_width
    metadata = {'source': str(args.glb), 'capture_version': 2, 'background': 'white_composite', 'camera_model': 'OPENCV',
                'w': args.size, 'h': args.size, 'fl_x': focal, 'fl_y': focal,
                'cx': args.size / 2, 'cy': args.size / 2,
                'normalization_center': list(center), 'normalization_scale': 2 / extent,
                'frames': frames, 'blender_version': bpy.app.version_string}
    (args.out / 'capture.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
