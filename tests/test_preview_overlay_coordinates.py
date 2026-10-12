"""Image overlay coordinates cannot introduce additional filter operations."""
from pathlib import Path
import unittest
from produce_app_preview import build_command


class OverlayCoordinateTests(unittest.TestCase):
    def contract(self, **coordinates):
        return {'width':1920,'height':1080,'fps':30,'duration':15,
            'segments':[{'path':'fixture.mov','duration':15,'has_audio':False}],
            'overlays':[{'type':'image','path':'fixture.png','start':0,'end':15,**coordinates}]}

    def test_filter_expression_and_non_numeric_values_rejected(self):
        for field in ('x','y'):
            for value in ('0:shortest=1;movie=private-file.png[extra]', 'iw/2', True,
                          None, float('nan'), float('inf'), {}, []):
                with self.subTest(field=field,value=value):
                    with self.assertRaisesRegex(ValueError, 'coordinate'):
                        build_command(self.contract(**{field:value}),Path('preview.mp4'))

    def test_coordinates_outside_canvas_bounds_rejected(self):
        for field,value in [('x',1921),('x',-1921),('y',1081),('y',-1081),('x',10**400)]:
            with self.assertRaisesRegex(ValueError, 'coordinate'):
                build_command(self.contract(**{field:value}),Path('preview.mp4'))

    def test_numeric_positions_and_default_origin_remain_valid(self):
        for values,expected in [({},'overlay=x=0:y=0:'),
                                ({'x':7.5,'y':-12},'overlay=x=7.5:y=-12:')]:
            command=build_command(self.contract(**values),Path('preview.mp4'))
            graph=command[command.index('-filter_complex')+1]
            self.assertIn(expected,graph)
