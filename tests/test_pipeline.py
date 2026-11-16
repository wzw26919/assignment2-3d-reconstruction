import json
import sqlite3
import struct
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_afs import probe, check_glb
from export_matches import MAX_IMAGE_ID, decode_pair, export
from pipeline import known_pose_dataset, manifest, orbit_path
from analyze_sfm import compare_poses


class PipelineTests(unittest.TestCase):
    def test_glb_fallback_and_invalid_length(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            valid = root/'actual'; valid.mkdir()
            path = valid/'a.glb'
            path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12))
            result = probe([root/'absent', valid])
            self.assertEqual(result['status'], 'readable')
            self.assertEqual(result['attempts'][0]['error'], 'FileNotFoundError')
            path.write_bytes(struct.pack('<4sII', b'glTF', 2, 100))
            with self.assertRaises(ValueError): check_glb(path)

    def test_verified_matches_export_keeps_correct_pair_direction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = root/'database.db'
            with closing(sqlite3.connect(db)) as conn:
                conn.executescript('CREATE TABLE images(image_id INTEGER,name TEXT);'
                                  'CREATE TABLE keypoints(image_id INTEGER,rows INTEGER,cols INTEGER,data BLOB);'
                                  'CREATE TABLE matches(pair_id INTEGER,rows INTEGER);'
                                  'CREATE TABLE two_view_geometries(pair_id INTEGER,rows INTEGER,cols INTEGER,data BLOB,config INTEGER);')
                for i in (3, 8):
                    name = f'{i}.png'
                    Image.new('RGB', (32,32), 'gray').save(root/name)
                    conn.execute('INSERT INTO images VALUES(?,?)', (i,name))
                    conn.execute('INSERT INTO keypoints VALUES(?,?,?,?)', (i,2,2,np.array([[4,5],[10,12]],np.float32).tobytes()))
                pair = 3*MAX_IMAGE_ID+8
                conn.execute('INSERT INTO matches VALUES(?,?)', (pair,3))
                conn.execute('INSERT INTO two_view_geometries VALUES(?,?,?,?,?)', (pair,2,2,np.array([[0,1],[1,0]],np.uint32).tobytes(),2))
                conn.commit()
            result = export(db, root, root/'out')
            self.assertEqual(decode_pair(pair), (3,8))
            self.assertEqual(result['inliers_total'], 2)
            self.assertEqual(result['verified_pairs'], 1)
            with np.load(root/'out/verified_matches.npz') as matches:
                np.testing.assert_array_equal(matches[str(pair)], [[0,1],[1,0]])
            self.assertTrue((root/'out/matches_00.png').is_file())

    def test_appearance_holdout_is_common_and_disjoint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); capture = root/'capture'; capture.mkdir()
            (capture/'capture.json').write_text(json.dumps({'w':512,'fl_x':700,'fl_y':700,'cx':256,'cy':256}))
            frames = [{'file_path':f'r{r}_{a:03}.png','ring':r,'azimuth':a,
                       'transform_matrix':np.eye(4).tolist()} for r in range(3) for a in range(24)]
            heldouts = []
            for stride in (1,2):
                target = root/f's{stride}'
                train_count, eval_count = known_pose_dataset(capture, [f for f in frames if f['azimuth']%stride==0], target, 512)
                split = json.loads((target/'split.json').read_text())
                self.assertTrue(set(split['training']).isdisjoint(split['evaluation']))
                self.assertEqual(eval_count, 12)
                self.assertEqual(train_count, 72//stride-12)
                heldouts.append(split['evaluation'])
            self.assertEqual(*heldouts)

    def test_no_silent_unapproved_data_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'manifest.json'
            path.write_text(json.dumps({'assignment1_manifest':None,'objects':[]}))
            with self.assertRaises(ValueError): manifest(path)

    def test_orbit_is_right_handed_and_looks_at_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'capture.json').write_text(json.dumps({'h':512,'fl_y':700}))
            orbit_path(root,root/'path.json')
            path = json.loads((root/'path.json').read_text())
            self.assertEqual(len(path['camera_path']),120)
            for frame in path['camera_path']:
                matrix = np.array(frame['camera_to_world']).reshape(4,4)
                rotation, center = matrix[:3,:3], matrix[:3,3]
                np.testing.assert_allclose(rotation.T@rotation,np.eye(3),atol=1e-10)
                self.assertAlmostEqual(np.linalg.det(rotation),1)
                self.assertAlmostEqual(np.linalg.norm(center),4)
                np.testing.assert_allclose(rotation[:,2],center/4,atol=1e-10)

    def test_camera_alignment_recovers_similarity_without_reflection(self):
        points=np.array([[1,0,0],[0,1,0],[0,0,1],[-1,-1,0]],dtype=float)
        rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]],dtype=float)
        estimated={}; frames=[]
        for i,point in enumerate(points):
            name=f'{i}.png'
            estimated[name]=(point,np.eye(3))
            matrix=np.eye(4); matrix[:3,3]=2.5*rotation@point+[3,4,5];matrix[:3,:3]=rotation
            frames.append({'file_path':name,'transform_matrix':matrix.tolist()})
        result=compare_poses(estimated,frames)
        self.assertAlmostEqual(result['alignment_scale'],2.5)
        self.assertLess(result['center_rmse'],1e-10)
        self.assertLess(result['rotation_median_degrees'],1e-5)


if __name__ == '__main__':
    unittest.main()
