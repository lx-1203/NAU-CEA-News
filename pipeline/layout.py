"""Small editorial layout contract; derived crops never replace source files."""
import math
from PIL import Image


def contain_rect(box, size):
    scale = min(box['width']/size[0], box['height']/size[1])
    # yuv420p chroma requires even sizes; odd CSS heights can make FFmpeg
    # round the scaled picture larger than its pad and abort the whole issue.
    w, h = max(2, int(size[0]*scale)//2*2), max(2, int(size[1]*scale)//2*2)
    return (round(box['x']+(box['width']-w)/2),
            round(box['y']+(box['height']-h)/2), w, h)


def validate_framing(value=None):
    value = dict(value or {})
    crop = value.get('crop', [0, 0, 1, 1])
    if (not isinstance(crop, list) or len(crop) != 4 or
        not all(isinstance(v, (int, float)) and math.isfinite(v) for v in crop) or
        not (0 <= crop[0] < crop[2] <= 1 and 0 <= crop[1] < crop[3] <= 1)):
        raise ValueError('素材裁框必须是原图内有效的归一化区域')
    layout = value.get('layout', 'photo')
    if layout not in {'photo', 'portrait', 'document', 'wide-document', 'interface', 'diagram', 'cinema'}:
        raise ValueError('未知素材版式')
    return dict(value, crop=crop, layout=layout)


def key_facts(story):
    facts = story.get('key_facts', story.get('visual_labels', [])[:3])
    if (not isinstance(facts, list) or not 1 <= len(facts) <= 3 or
        any(not isinstance(v, str) or not v.strip() or len(v) > 22 for v in facts)):
        raise ValueError('事实卡需要1至3条非空短事实，每条不超过22字')
    return facts


def prepare_image(source, target, framing):
    framing = validate_framing(framing)
    with Image.open(source) as im:
        w, h = im.size
        box = tuple(round(v * (w if i % 2 == 0 else h)) for i, v in enumerate(framing['crop']))
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError('裁图区域小于一个像素')
        im.crop(box).save(target)
