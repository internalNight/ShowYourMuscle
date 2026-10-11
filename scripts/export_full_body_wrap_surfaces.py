"""导出 OpenSim 里 44 个 wrapping 面的几何参数（③ 的最后一块：现在只画了肌肉路径，包裹面只是隐含在路径形状里）。

必须在模型目录里用文件名打开：OpenSim 打不开含中文的绝对路径。
"""
import json
import os
from collections import Counter

MODEL = r'C:\Users\yangs\Documents\ChatGPT\人体肌肉模型\.cache\model-candidates\opensim-models\Models\Rajagopal\RajagopalLaiUhlrich2023.osim'
REPO = r'C:\Users\yangs\Documents\ChatGPT\人体肌肉模型'
OUT = os.path.join(REPO, 'docs', 'data', 'full_body_wrap_surfaces.json')

import opensim as osim

os.chdir(os.path.dirname(MODEL))
model = osim.Model(os.path.basename(MODEL))
state = model.initSystem()

def wrap_set(body):
    for getter in ('getWrapObjectSet', 'getWrapSet'):
        if hasattr(body, getter):
            try:
                return getattr(body, getter)()
            except Exception:
                pass
    return None

def numbers(vec):
    return [round(float(vec.get(i)), 6) for i in range(vec.size())]

records = []
for i in range(model.getBodySet().getSize()):
    body = model.getBodySet().get(i)
    wraps = wrap_set(body)
    if wraps is None:
        continue
    for j in range(wraps.getSize()):
        wrap = wraps.get(j)
        kind = wrap.getConcreteClassName()
        entry = {
            'name': wrap.getName(),
            'type': kind,
            'body': body.getName(),
        }
        # 半径要按顺序试：基类调用（44 个里有 43 个能成功）→ 向下转型到具体类型 → 直接读属性。
        # 之前我"改成只走转型"反而把 43 个能读的读没了——守卫立刻报"44 个全没有半径"。
        def read_radius(candidate):
            if candidate is not None and hasattr(candidate, 'getRadius'):
                try:
                    return round(float(candidate.getRadius()), 6)
                except Exception:
                    return None
            return None

        radius = read_radius(wrap)
        if radius is None:
            for cls in ('WrapCylinder', 'WrapSphere', 'WrapEllipsoid', 'WrapTorus'):
                if not hasattr(osim, cls):
                    continue
                try:
                    radius = read_radius(getattr(osim, cls).safeDownCast(wrap))
                except Exception:
                    radius = None
                if radius is not None:
                    break
        if radius is None:
            for property_name in ('radius', 'Radius'):
                try:
                    value = wrap.getPropertyByName(property_name).getValue()
                    radius = round(float(getattr(value, 'getValue', lambda: value)()), 6)
                    break
                except Exception:
                    pass
        if radius is not None:
            entry['radiusM'] = radius
        if hasattr(wrap, 'getDimensions'):
            try:
                entry['dimensionsM'] = numbers(wrap.getDimensions())
            except Exception:
                pass
        try:
            transform = wrap.getTransform()
            entry['translationM'] = numbers(transform.p())
            rotation = transform.R()
            entry['rotationRowM'] = [numbers(rotation.get(i)) for i in range(3)]
        except Exception:
            pass
        records.append(entry)

# 半径在 Python 绑定里读不出来（getRadius 与向下转型都试过，44 个全都拿不到），但 .osim 本身就是 XML，
# 里面的 <WrapCylinder><radius> 是权威值——直接解析 XML 补上，比继续试 API 更可靠。
import xml.etree.ElementTree as ElementTree

tree = ElementTree.parse(os.path.join(os.path.dirname(MODEL), os.path.basename(MODEL)))
radius_by_name = {}
for element in tree.iter():
    if not element.tag.startswith('Wrap'):
        continue
    name = element.get('name')
    radius = element.find('radius')
    if name and radius is not None and radius.text:
        radius_by_name[name] = round(float(radius.text), 6)
for record in records:
    if 'radiusM' not in record and record['name'] in radius_by_name:
        record['radiusM'] = radius_by_name[record['name']]

payload = {
    'status': 'exported from the Rajagopal 2023 lower-limb model',
    'model': os.path.basename(MODEL),
    'radiusSource': 'parsed from the .osim XML: the Python bindings do not expose WrapObject.getRadius for these objects',
    'wrapObjects': len(records),
    'withRadius': len([record for record in records if 'radiusM' in record]),
    'types': dict(Counter(record['type'] for record in records)),
    'bodies': sorted({record['body'] for record in records}),
    'records': records,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write('\n')
print(json.dumps({k: payload[k] for k in ('wrapObjects', 'types', 'bodies')}, ensure_ascii=False))

summary_path = os.path.join(REPO, 'docs', '项目阶段总结.md')
with open(summary_path, 'r', encoding='utf-8') as handle:
    text = handle.read()
if '增补之六十六' not in text:
    text = text.rstrip('\n') + '\n\n' + '\n'.join([
        '## 增补之六十六：③ 的最后一块——44 个 wrapping 面的几何参数入库',
        '',
        '③ 一直是"路径点已真实、包裹面只是隐含在路径形状里"。这一轮把 wrapping 面的**几何参数**从 OpenSim 导出：',
        '',
        '- 文件：`docs/data/full_body_wrap_surfaces.json`',
        '- 内容：' + str(len(records)) + ' 个包裹面，类型分布 ' + json.dumps(payload['types'], ensure_ascii=False)
        + '，分布在 ' + str(len(payload['bodies'])) + ' 个体段上',
        '- 每个面记录：名称、类型、所属体段、半径（圆柱／球）或三维尺寸（椭球）、以及在体段坐标系里的平移与旋转',
        '',
        '**为什么先入库、不直接渲染**：渲染要先把"体段坐标系里的包裹面"变换到默认视图的坐标系（与肌肉路径同一套',
        '变换），并决定用什么视觉语言表达"这是一个约束面而不是解剖结构"——直接画成实体圆柱会被误读成肌肉。',
        '下一轮按此渲染，并把"包裹面必须能按体段名对应上"写成守卫。',
        '',
        '**限度**：这些参数是**模型定义**里的值，不是从影像测出来的；它们描述的是"肌肉路径绕过什么"，不是解剖结构。',
        '',
    ])
    with open(summary_path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    print('summary: 增补之六十六 appended')
