# Blender 内容制作起点

## MyoSim 全身结构候选

已用 Blender 5.1.2 生成 [全身结构场景](../assets/blender/myosim_fullbody_structural_review.blend)和[站姿预览](../assets/blender/myosim_fullbody_structural_review.png)。它来自 [MyoSim](https://github.com/MyoHub/myo_sim) 的全身 MuJoCo 模型；本机实际编译到 104 个体段（含世界体）、123 个关节、416 个肌肉执行器和 102 个使用中的可见网格。Blender 默认显示骨骼和 206 条四肢肌肉运行时折线，躯干的 210 条可在集合中打开。折线包含 MuJoCo 计算出的包绕切点；在模型声明包绕的 176 条中，站姿有 98 条实际发生包绕，显示为橙色。**包绕曲面上的弧线仍用直线表示**，最长一条折线比求解器肌腱长度短约 4.4 cm，不能用可见线段直接求肌肉长度。重新打开 `.blend` 后，对全部 102 个网格的坐标和全部 416 条折线的运行时点、属性共完成 1,900 项核对。

```powershell
git clone --depth 1 https://github.com/MyoHub/myo_sim.git .cache/model-candidates/myo_sim
& '.cache/opensim-venv/Scripts/python.exe' -m pip install 'mujoco>=3.4,<4'
& '.cache/opensim-venv/Scripts/python.exe' scripts/probe_myosim_fullbody.py
& '.cache/opensim-venv/Scripts/python.exe' scripts/export_myosim_blender_snapshot.py
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_myosim_fullbody_snapshot.py'
& 'D:\blender\blender.exe' --background 'assets/blender/myosim_fullbody_structural_review.blend' --python-exit-code 1 --python 'blender/check_myosim_fullbody_snapshot.py'
```

Windows 下 MuJoCo 读取带中文路径的 STL 文件失败，导出脚本会把候选包暂存到系统英文临时目录再编译；项目文件仍在本工作区。该模型是**通用站姿结构**，未根据输入身高、围度或训练记录缩放，也没有深蹲、卧推或实力举动画。当前 AB01 实测最深深蹲的双膝弯曲约 139–142°，超过该模型膝关节设定的 120° 范围；OpenSim 与 MuJoCo 的关节坐标约定还须逐项对齐，不能直接把旧轨迹或旧力矩灌入新模型。此场景颜色只用于辨别路径状态，不表示肌肉长度变化、激活或力量。MyoSim 上肢源模型的商业使用权尚未核实，因此场景和预览已被 Git 忽略，**仅供本地研究，不进入 App 或发布文件**。[结构审查](../docs/data/myosim_fullbody_candidate_audit.json)与[权利说明](../assets/blender/NOTICE-myosim-research.txt)记录了限制。

## AB01 双腿深蹲研究场景

已用 Blender 5.1.2 生成 [双腿场景](../assets/blender/ab01_bilateral_squat_paths.blend)与[预览图](../assets/blender/ab01_bilateral_squat_paths.png)。21 帧来自 AB01 已复算的实验 IK；模型保留 54 条左右肌肉路径，并加入在参考姿态水平的 20 kg 显式杠铃。白色为骨架和杠铃，紫／青色区分左右肌肉路径，颜色不表示发力。保存后重新加载，对三个采样帧通过 348 项位置和方向核对。可复算：

```powershell
& '.cache/opensim-venv/Scripts/python.exe' scripts/export_bilateral_squat_blender_data.py
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_bilateral_squat_scene.py'
& 'D:\blender\blender.exe' --background 'assets/blender/ab01_bilateral_squat_paths.blend' --python-exit-code 1 --python 'blender/check_bilateral_squat_scene.py'
```

这个公开人体模型只有双腿和简化躯干，没有上肢或真实握持；杠铃焊接点由假设给定，偏离校准姿态会随躯干倾斜。在 0.5 秒片段中两端最大高差约 0.36 m，因此不应把此文件用作真实杠铃轨迹或个体发力指导。[模型组装和静态优化质量审查](../docs/OpenSim研究记录.md)记录了物理限制。

## 参数化示意人体

手机端和 Blender 现在共用 `src/model.ts` 的动作姿态、23 条示意肌肉路径、身体外轮廓尺寸和示意肌肉粗细规则。可用下列命令将合成样例 `assets/blender/demo_profile.json` 生成为 153 帧的 [个人化 Blender 文件](../assets/blender/personalized_demo.blend)，并查看 [预览图](../assets/blender/personalized_demo.png)：

```powershell
node scripts/export-blender-poses.mjs --profile assets/blender/demo_profile.json --out assets/blender/demo_profile_poses.json --load-kg 60
& 'D:\blender\blender.exe' --background 'assets/blender/muscle_atlas_seed.blend' --python-exit-code 1 --python 'blender/animate_seed.py' -- --input 'assets/blender/demo_profile_poses.json' --output 'assets/blender/personalized_demo.blend' --preview 'assets/blender/personalized_demo.png'
& 'D:\blender\blender.exe' --background 'assets/blender/personalized_demo.blend' --python-exit-code 1 --python 'blender/check_motion.py' -- --input 'assets/blender/demo_profile_poses.json'
```

要生成自己的场景，可复制 JSON 输入文件并修改 10 个参数，再替换命令中的输入和输出路径。只需身高、体重；其余字段可省略并使用模型默认比例。单位为厘米、公斤和体脂百分比；非法范围会被导出器拒绝。示例参数是虚构的，文件在本机生成，不上传。可选参数 `--load-kg 60` 指定示意杠铃总重量；`--squat-bar-offset-cm -6|0|6` 指定深蹲杠铃相对默认位置的前后偏移，两者与手机端使用同一位置函数，但不会计算肌肉力。`07_Animated_Barbell_Scenario` 集合包含可随三种动作移动的杠铃；卧推在该场景仍为直立动作示意。Blender 场景的 `06_Profile_Outer_Contours` 集合包含按臂围、胸围、腰围、大腿围和小腿围标定的半透明轮廓；骨段还受身高、臂展、内侧腿长影响。胸围还调整示意胸肌路径的视觉粗细，不能确定胸大肌体积。时间轴第 1–51 帧为深蹲、第 61–111 帧为卧推、第 121–171 帧为实力举。默认每组 50 个帧间隔与手机端共同读取 `src/data/demo_motion_protocol.json`，播放用时 2.8 秒；导出时可用 `--cycle-duration-s 2|2.8|4` 写入单个 JSON，并由 `animate_seed.py` 设置 Blender 的有效帧率。该时长仍是人工示意，不是使用者实际动作时间。

肌肉仍是由 2–3 个教学路径点连接的示意曲线，体重和体脂只用于调整显示粗细，不等于测得的肌肉量。Blender 将两点路径的中点插值成肌腹控制点；三点路径沿用原有中点。曲线两端收窄，路径变短时用 `1/√长度比` 略微加粗、变长时略微变细，幅度限制在 0.75–1.25；手机端示意椭球使用同一规则。这只是让教学形体的体积变化较平稳，**不是肌纤维体积守恒或收缩力测量**。蓝色表示路径相对本动作起始姿态变长超过 2.5%，紫色表示变短超过 2.5%，粉色表示变化较小；颜色从不表示肌肉发力。对象属性 `length_ratio` 与 `belly_radius_scale` 可查看当前帧的示意值。这个场景没有肌腱、包绕、接触力或已验证的肌肉受力计算。卧推在此场景中的姿态也只是可编辑的示意预览。重新打开 `.blend` 后，检查脚本抽查十帧的全部肌肉路径点、粗细、长度比、渲染颜色、外轮廓尺寸和关节位置。

[深蹲第 26 帧预览](../assets/blender/personalized_demo_length.png)可用于查看长度配色，[侧视预览](../assets/blender/personalized_demo_side.png)可检查杠铃与示意姿态的前后关系。当前深蹲轨迹保持躯干骨段长度和双手握持杠铃，但仍为人工运动学；路径颜色不能展示真实的肌肉激活或力量。

额外的[较深深蹲 117° 场景](../assets/blender/deep_squat_117_demo.blend)与[第 26 帧预览](../assets/blender/deep_squat_117_bottom.png)展示手机新增的动作幅度选择；其[逐帧 JSON](../assets/blender/deep_squat_117_poses.json)可用 `node scripts/export-blender-poses.mjs --squat-depth-deg 117 --out assets/blender/deep_squat_117_poses.json` 重建。场景保存后以 `blender/check_motion.py -- --input assets/blender/deep_squat_117_poses.json` 抽查十帧通过。较深版只根据预设膝角降低骨盆；在同一批公开力板数据中的整体竖直力误差**没有优于**原型默认版，见[深度对照](../docs/动态深蹲验证数据.md)。它不能作为真实深蹲技术或肌肉发力标准。

## 胸廓—肩胛卧推路径研究

`blender/build_tsm_bench_scene.py` 从手机端同一份 `public/data/bench_tsm_reference.json` 生成 [Blender 卧推研究场景](../assets/blender/opensim_tsm_bench_reference.blend) 和 [第 51 帧预览](../assets/blender/opensim_tsm_bench_preview.png)。Blender 时间轴 1–101 帧可查看单侧肩臂 5 段示意骨骼、6 个关节位置、33 束肌肉路径，以及胸廓、锁骨、肩胛骨、肱骨、尺骨、桡骨和手部 7 块模型刚体的坐标轴。卧推凳只用于空间参照，不计算接触。`blender/check_tsm_bench_scene.py` 在重新打开的文件中对五帧核对关节位置、路径端点和 21 条坐标轴，共 980 项。人工手部目标已按[Larsen 等（2022）的组均起举事件](../docs/卧推负重研究.md)修正沿凳轴方向；它仍未经个人逐帧测量或发力验证。

同一生成器以 `--exercise press` 可生成[实力举肩臂研究场景](../assets/blender/opensim_tsm_press_reference.blend)和[第 51 帧预览](../assets/blender/opensim_tsm_press_preview.png)。它也有 101 帧、33 束单侧肌肉路径和 7 块刚体坐标轴；保存后重新打开核对五帧共 1042 项。两份离线 JSON 均含逐帧刚体位姿，旋转矩阵经正交性和行列式检查，可作为今后解剖骨网格绑定的运动基底。它们**尚未绑定 Z-Anatomy 骨骼或肌肉网格**；坐标轴只是模型刚体的相对运动，不表示解剖配准、力量或个体化参数。两个研究动作都为人工轨迹。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_tsm_bench_scene.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_bench_reference.blend' --python-exit-code 1 --python 'blender/check_tsm_bench_scene.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_tsm_bench_scene.py' -- --exercise press
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_press_reference.blend' --python-exit-code 1 --python 'blender/check_tsm_bench_scene.py' -- --exercise press
```

运行 `blender --background --python blender/bootstrap_scene.py` 可生成 `assets/blender/muscle_atlas_seed.blend` 和 `public/models/prototype_parts.glb`。本机 Blender 5.1.2 位于 `D:\blender\blender.exe`，可直接使用 `& 'D:\blender\blender.exe' --background --python 'blender/bootstrap_scene.py'`。脚本创建统一命名的骨架、地标、23 条肌肉示意路径和移动端网格模板。

运行 `npm run build:blender-poses`，再执行 `& 'D:\blender\blender.exe' --background 'assets/blender/muscle_atlas_seed.blend' --python 'blender/animate_seed.py'`，会生成可直接在 Blender 时间轴拖动的 `assets/blender/muscle_atlas_motion.blend`，并渲染 `assets/blender/motion_preview.png`。时间轴第 1–51 帧为深蹲、第 61–111 帧为卧推、第 121–171 帧为实力举。`blender/check_motion.py` 对保存文件抽样核对关节、骨段和肌肉路径与 App 姿态数据一致。这里的动作仍是教学示意，不是解剖绑定或肌骨动力学。

[实力举第 146 帧预览](../assets/blender/press_motion_preview.png)展示经站姿推举组层轨迹范围筛查后重新导出的场景。它与手机端共用示意骨架姿态；杠铃范围的匹配不代表肌肉力经过验证。

初始场景是**静态结构占位**，动作场景是其可拖动时间轴的几何预览。动作场景的肌肉曲线改用手机端相同的 2–3 个示意路径点，但没有解剖学准确的起止点、肌腱、包绕物或受力参数。GLB 提供骨骼、关节、纺锤形肌腹等网格模板；手机端对网格施加独立的简化动作。不能将其用于发力计算。

正式资源制作应先核对素材许可，然后在 Blender/MuSkeMo 中建立可复用的人体分段、关节坐标、肌肉路径与参数。手机端使用轻量 GLB；肌骨计算端使用同一套关节和肌肉标识。

## 静态解剖参考层

`python scripts/fetch_z_anatomy.py` 从 [Z-Anatomy 官方仓库](https://github.com/Z-Anatomy/Models-of-human-anatomy)下载 Blender 源文件到忽略的 `.cache/`。随后可用 `& 'D:\blender\blender.exe' --background '.cache/z-anatomy/Startup.blend' --python 'blender/export_reference.py'` 导出 `public/models/z_anatomy_reference.glb`。当前导出 165 个网格，包括胸、肩、手臂、腹部、背部、臀腿主要肌肉及部分骨骼，新加入左右髌骨与跟骨，供手机端**静态识别**。来源和许可见 `public/models/NOTICE-z-anatomy.txt`。源资产保持原样；手机加载后可对选定肌肉网格作有限的围度外形调整，仍不随动作运动。

## OpenSim 深蹲同源场景

`blender/build_opensim_squat_scene.py` 从手机端同一份 `public/data/squat_opensim_reference.json` 生成 `assets/blender/opensim_squat_reference.blend`。Blender 时间轴为 101 帧，包含单侧下肢 4 段骨骼、5 个关节中心及九条肌肉的 35 个路径段；路径点数量随模型包绕状态变化时，多余段会缩为零。第 1、51、101 帧分别标记站立、最深姿态、回到站立。`assets/blender/opensim_squat_preview.png` 是第 51 帧预览。

```powershell
& 'D:\blender\blender.exe' --background --python 'blender/build_opensim_squat_scene.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_squat_reference.blend' --python 'blender/check_opensim_squat_scene.py'
```

检查器在保存后的文件中抽查五个时间点的骨段、关节和全部肌肉路径，当前为 220 项通过。导入时将手机视图的 Y 向上坐标转换为 Blender/Z-Anatomy 的 Z 向上坐标，并把右踝侧向位置暂放到解剖样本约 `x=-0.09 m`。`blender/probe_reference_alignment.py` 输出了右侧股骨、胫骨、髋骨等参考网格的包围盒至 `docs/data/reference_bone_bounds.json`，供后续拟合关节中心；包围盒不能当作附着点或关节中心。该场景把 OpenSim **运动学** 数据固定进 Blender，便于后续以相同关节和路径建立解剖网格绑定；只有右腿参考，没有全身骨骼、用户体型变形、杠铃载荷或肌肉发力高亮。

`blender/build_registration_overlay.py` 进一步在站立帧叠加 Z-Anatomy 的右髋骨、股骨、胫骨和腓骨，生成 `assets/blender/opensim_anatomy_registration.blend` 与 PNG。它仅用股骨、胫骨包围盒中心对 OpenSim 对应骨段中心求共同平移；目前平移约 `(-0.014, -0.065, +0.036) m`，这两个**包围盒中心**的剩余差约 4.7 mm。`blender/check_registration_overlay.py` 在重新打开的文件里检查该结果。数值和限制见 `docs/data/standing_registration_probe.json`。包围盒并非真实关节中心，中心对齐也不验证骨面、关节轴或肌肉附着点；这个文件只用于审查下一步精确绑定的偏差。

`scripts/build_opensim_lookup.py` 还导出 OpenSim 骨盆、右股骨、右胫骨、右髌骨和右跟骨在每帧的刚体坐标。运行 `blender/animate_registered_bones.py` 会将六块已平移的解剖骨网格按对应刚体运动写成 101 帧 `assets/blender/opensim_anatomy_bone_motion.blend`，第 51 帧预览为 `assets/blender/opensim_anatomy_bone_motion.png`。`blender/check_animated_registered_bones.py` 在重新打开的文件中抽查五帧、六块骨骼共 30 个世界矩阵。腓骨跟随胫骨，髋骨跟随骨盆，髌骨和跟骨分别跟随 OpenSim 的对应骨段；站立时只按股骨／胫骨包围盒中心求共同平移，髌骨和跟骨没有独立标志点配准。手机端复用同一 GLB 的六块骨网格和同源刚体数据，在 OpenSim 深蹲视图按需显示研究叠加层。

在已保存的六骨骼时间轴上，`blender/probe_animated_bone_surfaces.py` 对第 1、26、51、76、101 帧检查新增骨骼与相邻骨骼的几何间距：髌骨顶点到股骨表面的最短距离为 **0.01–0.23 cm**，跟骨到胫骨为 **0.93–1.75 cm**。[逐帧间距表](../docs/data/animated_patella_calcaneus_gap_screen.json)只用于排查明显脱离；没有检查骨面穿透、软骨、足部距骨或真实关节贴合。髌骨上五个 OpenSim 源路径点仍与对应 Z-Anatomy 骨面相距 **4.54–5.34 cm**。因此六块骨骼随动仍是粗配准研究层，不是可用于肌肉附着和发力计算的解剖绑定。

```powershell
& 'D:\blender\blender.exe' --background --python 'blender/animate_registered_bones.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_anatomy_bone_motion.blend' --python 'blender/check_animated_registered_bones.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_anatomy_bone_motion.blend' --python 'blender/probe_animated_bone_surfaces.py'
```

## 股直肌网格的研究形变

`blender/probe_rectus_alignment.py` 比较 Z-Anatomy 右股直肌网格站立姿态的五处横切面中心与 OpenSim `rect_fem_r` 路径，同一粗配准下偏差为 2.1–4.7 cm，数据见 `docs/data/rectus_rest_alignment_probe.json`。这足以说明现有路径不能直接当作网格的解剖中心线。

`blender/probe_leg_muscles.py` 以相同方法筛查八组右腿网格和模型路径，结果在 `docs/data/right_leg_muscle_path_screen.json`。最大中心偏差依次约为：股直肌 4.7 cm、股二头肌短头 5.5 cm、半膜肌 6.7 cm、臀大肌 6.8 cm、比目鱼肌 8.5 cm、胫骨前肌 8.9 cm、股中间肌 13.2 cm、腓肠肌内侧头 15.0 cm。不同资产对相同肌肉的范围和肌腱表示可能不同；目前只用股直肌开展网格形变研究，其余肌肉须先确定对应解剖标志点和路径范围。

`scripts/export_squat_attachments.py` 从 OpenSim 原模型导出九条肌肉的 30 个原始路径点（名称、所属局部骨段坐标系、局部坐标与站立世界坐标）及八项包绕关联，写入 `docs/data/opensim_squat_attachment_inventory.json`。它为逐点审查提供模型侧数据，不能自动验证 Z-Anatomy 网格上的附着点。后续应在骨网格上标记可审查的解剖点、建立对应关系，再检查整个动作里的路径和包绕。参照 [OpenSim Muscle Editor](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53090145)、[OpenSim 模型路径点格式](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53088473)和 [MuSkeMo](https://github.com/PashavanBijlert/MuSkeMo) 的局部坐标工作流。

`blender/build_attachment_review.py` 把上述 30 点与八块候选肌肉网格放进 `assets/blender/opensim_attachment_review.blend`，每条肌肉一组集合，默认只显示股直肌和它的路径点。绿色、浅蓝、深蓝标记分别为首点、中间点、末点；名称、父坐标系和局部位置保存在 Blender 对象属性中。保存后 `blender/check_attachment_review.py` 重新核对九组集合与 30 个点。标记代表 OpenSim 原模型位置，**还不是在解剖网格上确认的附着点**。

`blender/probe_attachment_surfaces.py` 进一步按每个路径点的**父骨段**查找已粗配准 Z-Anatomy 骨面的最近点。新增髌骨和跟骨网格后，30 个源路径点全部可筛查，距离中位 **2.20 cm**、最大 **8.89 cm**；18 点超过 2 cm、4 点超过 5 cm。髌骨五点的最近骨面距离为 **4.54–5.34 cm**，表明这些骨骼也需要独立的解剖标志点配准。[逐点筛查表](../docs/data/attachment_surface_screen.json)保留源点、最近面位置、距离与父骨段。审查场景为 30 点新增黄色／橙色最近面候选点和灰色间距线；橙色只表示距离超过 2 cm，**绝非肌肉发力高亮**。最近骨面不等于肌腱附着点，OpenSim 点也可能是离骨面有意偏移的抽象路径锚；不能把候选点自动吸附到骨面或据此改变肌肉形变。要完成真实配准，仍需解剖标志点的人工核对与动作中骨面、路径检查。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_attachment_surfaces.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_attachment_review.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_attachment_review.blend' --python-exit-code 1 --python 'blender/check_attachment_review.py'
```

`blender/animate_rectus_mesh.py` 在原站立网格上建立 101 帧形变：肌腹主要随 OpenSim 股骨刚体坐标移动，靠近两端时以 `0.5 × |2t−1|²` 混入对应路径分数的位移，`t` 仅来自网格原始高度。生成 `assets/blender/opensim_rectus_mesh_motion.blend` 和第 51 帧 PNG；`blender/check_rectus_mesh_motion.py` 对保存文件的五帧抽样顶点与全部网格边做检查。最深姿态没有边缩至站立长度一半以下，但此边长指标不证明肌纤维应变真实、表面不穿模或附着点正确。手机 OpenSim 深蹲视图的可选研究层使用相同公式，在设备本地更新 4,136 个顶点；紫色仅代表这块形变网格，不代表肌肉激活。

```powershell
& 'D:\blender\blender.exe' --background --python 'blender/probe_rectus_alignment.py'
& 'D:\blender\blender.exe' --background --python 'blender/probe_leg_muscles.py'
& 'D:\blender\blender.exe' --background --python 'blender/animate_rectus_mesh.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_rectus_mesh_motion.blend' --python 'blender/check_rectus_mesh_motion.py'
```

### 三块大腿肌肉的同步形变研究（2026-09-25）

在上述股直肌之外，又将 Z-Anatomy 的右侧**股二头肌短头**和**半膜肌**网格接到同一 OpenSim 深蹲参考轨迹。`blender/animate_leg_muscle_meshes.py` 从同一站姿配准与右股骨刚体运动生成三块网格的 101 帧形态关键帧；靠近网格上下端时，混入对应 OpenSim 肌肉路径的位移。Blender 5.1.2 场景为[三块肌肉时间轴](../assets/blender/opensim_thigh_mesh_motion.blend)，[第 51 帧预览](../assets/blender/opensim_thigh_mesh_motion.png)可直接查看。

重新打开文件后，`blender/check_thigh_mesh_motion.py` 对五帧各五个顶点核对公式，并扫描这三块网格的全部边。最深帧的最小／最大边长比依次为股直肌 **0.581／1.188**、股二头肌短头 **0.612／1.025**、半膜肌 **0.849／1.476**；五个抽查帧都没有边低于原长一半或高于 1.5 倍。[逐帧审查数据](../docs/data/right_thigh_mesh_motion_audit.json)可复核。这只排除了明显的局部折叠和异常拉伸，不能证实解剖附着或真实肌纤维应变。站姿切片中心到对应模型路径的最大距离仍分别约 **4.7／5.5／6.7 cm**，说明两套资产尚未精确配准。

手机 OpenSim 深蹲视图的可选研究层现在复用相同的三块静态 GLB 网格和逐帧形变公式；紫、青、粉只区分网格，列表中的长度百分比仍取自 OpenSim 路径。骨骼与路径按身高统一缩放；围度、体脂和训练记录没有经过验证的个人解剖对应关系。它们不表示激活或力量。

现在还可用**大腿围调整这三块网格的共同横向厚度**，不改变骨骼、路径长度或三块肌肉之间的相对比例。以 175 cm、54 cm 大腿围为 1.00 倍，厚度系数是 `大腿围 / (54 × 身高 / 175)`，限制为 0.80–1.20；未填大腿围时，手机按身高、体重和体脂给出示意默认围度。在参考股骨轴上投影每个站姿顶点，只缩放其垂直于轴的偏移。这个**外形假设**不能反推出肌肉量、纤维长度或力量。

[62 cm 大腿围的 Blender 场景](../assets/blender/opensim_thigh_mesh_62cm.blend)与[预览](../assets/blender/opensim_thigh_mesh_62cm.png)采用 175 cm 身高，三块网格相对股骨轴的最大径向距离都是默认的 **1.148 倍**。保存后重新打开检查了五帧各五个顶点及全部网格边；最深帧的边长比仍分别在 0.579–1.180、0.613–1.023、0.849–1.473 之间。[62 cm 审查数据](../docs/data/right_thigh_mesh_62cm_audit.json)含逐项数字。手机端同一围度换算已与 Blender 的 15 个抽样顶点及原网格路径分数交叉核对；将测试页面从 54 cm 改为 62 cm 时，输入身高 190 cm 下系数由 0.92 变为 1.06，测试后已恢复原输入。另在本地忽略目录制作 25／110 cm 两个输入边界，系数分别被限制为 0.80／1.20；最深帧全部网格边的总范围分别为 0.581–1.478／0.578–1.471，仍通过当前 0.5–1.5 的粗几何门槛。尚未把网格整体外围精确校准成实测大腿围，也没有验证内部分配。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_leg_muscle_meshes.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_thigh_mesh_motion.blend' --python-exit-code 1 --python 'blender/check_thigh_mesh_motion.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_leg_muscle_meshes.py' -- --thigh-cm 62 --output 'assets/blender/opensim_thigh_mesh_62cm.blend' --preview 'assets/blender/opensim_thigh_mesh_62cm.png' --report 'docs/data/right_thigh_mesh_62cm_audit.json'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_thigh_mesh_62cm.blend' --python-exit-code 1 --python 'blender/check_thigh_mesh_motion.py' -- --report 'docs/data/right_thigh_mesh_62cm_audit.json'
npm run check:body-measurements
```

### 胫骨前肌随胫骨形变研究（2026-09-25）

`blender/probe_muscle_surface_paths.py` 将八组右腿 OpenSim 站姿路径点与已粗配准的 Z-Anatomy 对应网格表面做最近距离筛查。[逐点数据](../docs/data/right_leg_muscle_surface_path_screen.json)中，胫骨前肌 21 个采样点的距离中位约 **1.1 cm**、95 百分位约 **1.3 cm**、最大约 **1.6 cm**，其中 20 点落在网格的高度范围内。这是候选资产的几何筛查；最近表面不是肌腱附着点，路径与网格也没有完成解剖验证。

`blender/animate_tibialis_mesh.py` 在三块大腿肌肉场景上增加右胫骨前肌：网格主体随 OpenSim 右胫骨刚体运动，两端按网格高度分数混入对应路径的位移。生成的 [Blender 5.1.2 四肌肉时间轴](../assets/blender/opensim_four_muscle_motion.blend)有 101 帧，六块骨网格和四块肌肉网格可同步查看。保存后重新打开，`blender/check_tibialis_mesh_motion.py` 核对第 1／26／51／76／101 帧的抽样顶点与全部网格边；移动帧边长比最低约 **0.789**、最高约 **1.014**，[审查数据](../docs/data/right_tibialis_mesh_motion_audit.json)可复核。这只检查公式和粗局部几何，不证明无穿模、真实肌纤维应变或发力。

小腿围以 **175 cm 身高、36 cm 小腿围**为横向厚度 1.00 倍基准；手机端系数为 `小腿围 / (36 × 身高 / 175)`，限制在 0.80–1.20。只缩放网格顶点相对参考胫骨轴的垂直偏移，不改变骨骼和 OpenSim 路径。另存的 [42 cm 小腿围场景](../assets/blender/opensim_four_muscle_42cm.blend)及[审查数据](../docs/data/right_tibialis_mesh_42cm_audit.json)在 175 cm 身高下使用 1.167 倍，并通过相同的重新打开核查。手机测试在 190 cm 身高下把小腿围从 36 改到 42 cm，显示系数由 0.92 改为 1.07，恢复输入后又回到 0.92。围度无法确定胫骨前肌的独立体积或力量。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_muscle_surface_paths.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tibialis_mesh.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_four_muscle_motion.blend' --python-exit-code 1 --python 'blender/check_tibialis_mesh_motion.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tibialis_mesh.py' -- --calf-cm 42 --output 'assets/blender/opensim_four_muscle_42cm.blend' --report 'docs/data/right_tibialis_mesh_42cm_audit.json'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_four_muscle_42cm.blend' --python-exit-code 1 --python 'blender/check_tibialis_mesh_motion.py' -- --report 'docs/data/right_tibialis_mesh_42cm_audit.json'
npm run check:body-measurements
```

### 臀大肌随骨盆形变研究（2026-09-25）

又将 Z-Anatomy 右臀大肌网格接到同一单侧深蹲参考动作。站姿时，OpenSim `glut_max2_r` 路径的 21 个采样点都在网格高度范围内，离网格表面最大约 3.6 cm；这只是几何候选，不能确定解剖附着。Blender 5.1.2 的[五肌肉时间轴](../assets/blender/opensim_five_muscle_motion.blend)保存了 101 帧，并有[最深蹲姿态预览](../assets/blender/opensim_five_muscle_preview.png)：臀大肌主体跟随骨盆刚体，网格两端各混入 0.1 倍路径端点位移。初版使用与大腿网格相同的 0.5 倍时，第 26 帧有边缩至原长的 0.361 倍，未通过粗几何门槛，因此已降低形变修正幅度；这不代表改进了真实解剖准确性。

保存后重新打开检查第 1／26／51／76／101 帧的抽样顶点和全部网格边。最深帧的边长比为 **0.664–1.027**，当前门槛 0.5–1.5 内没有异常边；[审查结果](../docs/data/right_gluteus_mesh_motion_audit.json)记录逐帧数值。手机 OpenSim 深蹲研究层使用相同的骨盆矩阵、路径插值和 0.1 倍端点权重，加载后显示右腿六块骨骼与五块肌肉网格。臀大肌暂不依据腰围修改横向厚度：腰围并不能单独测出臀肌体积。橙色只区分网格，蓝／紫模式只表示整条 OpenSim 肌肉肌腱路径相对站姿的长度变化，均不是肌纤维应变、主动收缩或力量。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_gluteus_mesh.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_five_muscle_motion.blend' --python-exit-code 1 --python 'blender/check_gluteus_mesh_motion.py'
```

### 比目鱼肌动态网格（2026-09-25）

`blender/animate_soleus_mesh.py` 在五肌肉场景上加入右比目鱼肌，使右腿研究层达到**六块骨骼、六块肌肉**。网格主体随胫骨刚体运动；接近网格上下端时，以 OpenSim `soleus_r` 肌肉肌腱路径的对应分数作 0.5 倍位移修正。保存了[默认小腿围 36 cm 的 101 帧场景](../assets/blender/opensim_six_muscle_motion.blend)和[42 cm 场景](../assets/blender/opensim_six_muscle_42cm.blend)。小腿围沿参考膝—踝轴缩放这块网格的横向宽度，36→42 cm 对应系数 1.167；手机端采用同一换算。[42 cm 逐顶点记录](../docs/data/right_soleus_mesh_42cm_audit.json)已纳入 `npm run check:body-measurements` 交叉核对。

两份 `.blend` 重开后，`blender/check_soleus_mesh_motion.py` 对第 1／26／51／76／101 帧抽样顶点及全部边长比核对通过：默认场景范围约 **0.992–1.116**，42 cm 场景约 **0.992–1.114**，均没有越过当前 0.5–1.5 的粗门槛。[默认逐帧记录](../docs/data/right_soleus_mesh_motion_audit.json)可复查。原始站姿网格与模型路径中段较接近，但模型路径的肌腱末端距候选网格表面约 **8.9 cm**；网格只表示肌腹外形候选，不能靠这一规则补出真实肌腱、附着点或纤维应变。颜色仍仅表示**整条模型肌肉肌腱路径长度**，不表示比目鱼肌发力。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_soleus_mesh.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_six_muscle_motion.blend' --python-exit-code 1 --python 'blender/check_soleus_mesh_motion.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_soleus_mesh.py' -- --calf-cm 42 --output 'assets/blender/opensim_six_muscle_42cm.blend' --report 'docs/data/right_soleus_mesh_42cm_audit.json'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_six_muscle_42cm.blend' --python-exit-code 1 --python 'blender/check_soleus_mesh_motion.py' -- --report 'docs/data/right_soleus_mesh_42cm_audit.json'
```

### 胸肩模型右臂三骨几何配准（2026-09-25）

`blender/build_tsm_upper_bone_registration.py` 把 Z-Anatomy 右肱骨、桡骨、尺骨网格放入卧推和上举的 TSM 单侧胸肩模型。它取每块源网格上下 5% 高度切片的顶点中心作为**几何代理点**，将肱骨两端拟合到模型肩、肘；桡骨和尺骨共同使用前臂两骨代理点的平均位置拟合到肘、手，保留两骨间距。每块网格随后跟随对应 TSM 刚体坐标逐帧运动。手机端 OpenSim 卧推／实力举视图有可选开关，并复用同一配准矩阵及逐帧刚体变换。

生成的 [卧推 Blender 场景](../assets/blender/opensim_tsm_bench_upper_bones.blend)、[实力举 Blender 场景](../assets/blender/opensim_tsm_press_upper_bones.blend)和[卧推配准报告](../docs/data/tsm_bench_upper_bone_registration.json)、[实力举配准报告](../docs/data/tsm_press_upper_bone_registration.json)可复查。肱骨统一缩放系数约 **0.815**，前臂两骨共用系数约 **1.060**。桡骨／尺骨各自代理点的最大近端残差约 **1.91 cm**、远端约 **1.48 cm**；这些残差仅说明双骨共同变换与代理点的拟合程度。保存场景后重新打开并在五个抽样帧各核查三块网格，两个动作各通过 60 项检查。代理点未经解剖标志点核对，也未验证骨面、关节间隙、肌肉附着或个体化肌肉力量。页面仅按身高统一缩放这组研究几何，臂围、体脂及训练记录不决定三块骨网格形状。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_tsm_upper_bone_registration.py' -- --exercise bench
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_tsm_upper_bone_registration.py' -- --exercise press
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_bench_upper_bones.blend' --python-exit-code 1 --python 'blender/check_tsm_upper_bone_registration.py' -- --exercise bench
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_press_upper_bones.blend' --python-exit-code 1 --python 'blender/check_tsm_upper_bone_registration.py' -- --exercise press
```

`blender/probe_tsm_upper_muscle_surfaces.py` 又将 Z-Anatomy 肱二头肌长头、短头和肱三头肌长头网格先用上述肱骨变换粗配准，取卧推与实力举第 0／25／50／75／100 帧的各 21 个模型路径采样点到网格表面的无符号最近距离。[逐帧筛查数据](../docs/data/tsm_upper_muscle_surface_screen.json)显示：长头肱二头肌在卧推／上举起点的中位距离约 **1.61／1.52 cm**，五帧最大距离 **4.18／3.26 cm**；短头肱二头肌最大 **7.89／7.97 cm**，长头肱三头肌最大 **6.72／6.19 cm**。因此当前只选肱二头肌长头做进一步形变实验，另两块需要更好的骨骼与附着点配准。最近骨面既可能位于肌腹外也可能反映路径在肌腹内部，不能当成纤维路径或解剖附着。短头肱二头肌和长头肱三头肌尚未进入手机动态网格层。

[卧推肱二头肌长头场景](../assets/blender/opensim_tsm_bench_biceps_long_probe.blend)与[实力举场景](../assets/blender/opensim_tsm_press_biceps_long_probe.blend)在三骨场景上增加一块紫色 Z-Anatomy 网格：主体随肱骨刚体运动，网格两端按合成 `BIC_long` 肌肉肌腱路径的位移各混入最多 0.25 倍修正。[卧推预览](../assets/blender/opensim_tsm_bench_biceps_long_probe.png)、[实力举预览](../assets/blender/opensim_tsm_press_biceps_long_probe.png)均为中间帧。两份场景各有 101 帧和 102 个形态键；保存后重新打开，在五帧各核对 **24,135** 条已求值网格边。卧推边长相对初始网格范围为 **0.782–1.221**，实力举为 **0.789–1.168**，通过当前 0.5–1.5 粗几何门槛。[卧推审查](../docs/data/tsm_bench_biceps_long_probe.json)、[实力举审查](../docs/data/tsm_press_biceps_long_probe.json)记录逐帧范围。手机 OpenSim 卧推／实力举研究层现复用同一肱骨刚体与路径修正规则；蓝／紫色只表示整条模型肌肉肌腱路径比起点长／短。该审查不证明无穿模或真实肌纤维应变，更不能作为红色发力提示。

研究网格新增放松臂围的**横向外形示意**：以 175 cm 身高、32 cm 臂围为 1.00 倍基准，厚度系数为 `臂围 / (32 × 身高 / 175)`，截断在 0.80–1.20；未填臂围时沿用身高、体重、体脂生成的示意默认围度。网格顶点仅在垂直于起始肩—肘骨轴的方向缩放，模型骨骼和 `BIC_long` 肌肉肌腱路径保持原样。[38 cm 臂围 Blender 场景](../assets/blender/opensim_tsm_bench_biceps_long_38cm.blend)与[审查数据](../docs/data/tsm_bench_biceps_long_38cm.json)采用 175 cm 身高，实际系数为 **1.1875**；保存后重新加载，五帧各 24,135 条网格边的相对初始长度范围仍在 **0.783–1.223**。手机端与 Blender 的五个抽样顶点及路径分数交叉核对通过。这是外形参数，不把臂围分解成单块肌肉体积、附着点或力量。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_tsm_upper_muscle_surfaces.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tsm_biceps_long_probe.py' -- --exercise bench
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tsm_biceps_long_probe.py' -- --exercise press
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_bench_biceps_long_probe.blend' --python-exit-code 1 --python 'blender/check_tsm_biceps_long_probe.py' -- --exercise bench
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_press_biceps_long_probe.blend' --python-exit-code 1 --python 'blender/check_tsm_biceps_long_probe.py' -- --exercise press
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tsm_biceps_long_probe.py' -- --exercise bench --arm-cm 38 --output assets/blender/opensim_tsm_bench_biceps_long_38cm.blend --preview assets/blender/opensim_tsm_bench_biceps_long_38cm.png --report docs/data/tsm_bench_biceps_long_38cm.json
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_bench_biceps_long_38cm.blend' --python-exit-code 1 --python 'blender/check_tsm_biceps_long_probe.py' -- --exercise bench --report docs/data/tsm_bench_biceps_long_38cm.json
npm run check:body-measurements
```

### 胸大肌三束路径体（2026-09-25）

`blender/probe_tsm_pectoralis_registration.py` 将 Z-Anatomy 胸大肌锁骨、胸肋、腹部三块网格暂按已有肱骨几何变换放置，与 TSM 对应的三条起点路径作 21 点最近表面距离筛查。卧推三束最大偏差约 **8.3／14.8／18.0 cm**，实力举约 **11.1／17.5／18.9 cm**；详见[筛查数据](../docs/data/tsm_pectoralis_registration_screen.json)。肱骨变换不等于胸廓或锁骨配准，故这三块解剖网格暂不能绑定到动作，更不能据此外推肌肉发力。

再试用 atlas 肱骨近端切片、锁骨中心和胸骨柄中心三个几何代理点，分别拟合 TSM 肩、锁骨和胸廓位置。统一缩放约 0.892，三个代理点残差约 **2.4／4.5／2.3 cm**。拟合后卧推三束的最大无符号路径表面距离约 **6.9／6.1／16.0 cm**，实力举约 **4.4／6.3／16.0 cm**；[候选记录](../docs/data/tsm_pectoralis_landmark_fit_screen.json)可复算。胸大肌腹部仍明显错位，其他两束的几何代理点也未获解剖核对，因此继续保留路径示意体，暂不把 atlas 胸肌网格作为动作绑定结果。

又把锁骨中心改成 atlas **内侧 5% 顶点的几何代理点**，与原方案并列检查。三个代理点残差降至约 **0.02／0.10／0.09 cm**；但卧推胸大肌锁骨／胸肋／腹部三束路径到对应网格表面的最大距离仍约 **5.7／6.2／16.2 cm**，实力举约 **4.0／5.9／16.2 cm**。腹部束在实力举起点的 TSM 路径与拟合后网格高度范围接近，却在前后方向分离超过 10 cm。三个代理点的三角形面积仅约 **23 cm²**，且并非同一套解剖标志；几何点贴合不能证明胸廓前后朝向和肌肉位置正确。

再加入一个**胸肋束靠胸骨的网格内侧 2% 几何代理点**，与 TSM 对应路径起点组成第四个拟合点。四点拟合的统一缩放约 **0.775**，四点残差约 **1.2–2.2 cm**。虽然胸肋束起点参与拟合，**未参与拟合**的锁骨束与腹部束也接近网格：卧推三束最大路径表面距离约 **3.5／3.3／3.9 cm**，实力举约 **3.0／2.6／3.5 cm**。这比三点方案的腹部束约 16 cm 差距小，但四点对应仍只是几何假设，且这些距离在同一合成起点姿态中取得，不能称为解剖附着验证。[三方案逐点距离、拟合残差与变换](../docs/data/tsm_pectoralis_landmark_fit_screen.json)。

为便于在 Blender 中检查方向差异，`blender/build_pectoralis_registration_review.py` 可生成[三点方案站姿场景](../assets/blender/pectoralis_registration_review_press.blend)及[预览图](../assets/blender/pectoralis_registration_review_press.png)，也能生成[四点方案站姿场景](../assets/blender/pectoralis_registration_review_press_4point.blend)及[预览图](../assets/blender/pectoralis_registration_review_press_4point.png)。粉色为三束 atlas 网格，青色为 TSM 路径，黄色／绿色球分别是路径起止点，白色为骨与关节代理点。三点图的下方青线明显离开腹部网格；四点图接近许多。两套 Blender 5.1.2 文件保存后重开，核对 7 块源网格、3 条路径和相机。它们只供人工审核，不进入手机包，也不表示肌肉力。

`blender/audit_tsm_pectoralis_dynamic_registration.py` 随后在卧推／实力举各 101 帧比较四点起始配准后的两种网格运动：只随胸廓／锁骨刚体运动时，卧推三束最远偏差不超过 **4.1 cm**，实力举增至 **7.7／8.9／9.0 cm**；再按原始路径端点轴向比例平滑加入起点与止点的位移修正，实力举最远偏差降至 **3.0／2.6／3.5 cm**。这一步由同一模型路径驱动，距离缩小是算法设计的结果，**不是独立准确性验证**。全部 101 帧的网格边长比在实力举为 **0.70–1.38**；卧推锁骨束最高 **1.516**，略超之前的 1.5 粗门槛，故当前只把此 atlas 形变用于实力举研究场景。[逐帧距离及边长筛查](../docs/data/tsm_pectoralis_dynamic_registration_audit.json)。

已把实力举三束 atlas 网格做成[Blender 5.1.2 的 101 帧研究形变场景](../assets/blender/opensim_tsm_press_pectoralis_atlas_probe.blend)，[第 51 帧预览](../assets/blender/opensim_tsm_press_pectoralis_atlas_probe.png)可看收拢时的表面。保存重开后对三块网格、五帧共 45 个顶点复核通过；[生成记录](../docs/data/tsm_press_pectoralis_atlas_probe.json)列出规则与抽样点。它仍没有经过真实解剖标志、肌纤维应变或个人动作验证；现已接入手机端实力举 OpenSim 研究层，按同一几何规则逐帧更新；卧推也已生成并接入 [101 帧候选网格场景](../assets/blender/opensim_tsm_bench_pectoralis_atlas_probe.blend)：使用 80% 路径端点修正，三束最远表面距离约 3.54／3.34／4.13 cm，边长比 0.961–1.412；[预览](../assets/blender/opensim_tsm_bench_pectoralis_atlas_probe.png)与[审查记录](../docs/data/tsm_bench_pectoralis_atlas_probe.json)供复核。两种动作手机端与 Blender 共 270 个抽样坐标交叉核对，最大误差小于 0.001 mm。

为让卧推和实力举的主要胸肌束先有可观察的三维表达，`blender/build_tsm_pectoralis_proxies.py` 沿 TSM 胸大肌锁骨束、胸肋中束、胸肋下束各建一块收窄路径体：每束 21 个弧长等分截面、每截面 8 个顶点，圆截面方向由该帧路径两端方向确定；半径分别假设为 1.8／2.7／2.2 cm。生成的[卧推场景](../assets/blender/opensim_tsm_bench_pectoralis_path_proxies.blend)和[实力举场景](../assets/blender/opensim_tsm_press_pectoralis_path_proxies.blend)各有 101 帧形态键，手机研究层已改为候选解剖网格，此路径体几何保留为早期对照。保存重开后抽查两种动作各 54 个顶点，通过；手机与 Blender 在两种动作、三束、三帧各六个顶点的 324 个坐标比较通过。五帧网格边长比的总范围为卧推约 **0.973–1.503**、实力举约 **0.947–1.371**；审查值见[卧推](../docs/data/tsm_bench_pectoralis_path_proxies.json)及[实力举](../docs/data/tsm_press_pectoralis_path_proxies.json)。胸肌路径体没有经过 atlas 形状配准，半径也是视觉假设；蓝紫颜色只表示路径长度趋势。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_tsm_pectoralis_registration.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_tsm_pectoralis_landmark_fit.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_pectoralis_registration_review.py' -- --method medial_clavicle_end_proxy
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_pectoralis_registration_review.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/audit_tsm_pectoralis_dynamic_registration.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tsm_pectoralis_atlas_meshes.py'
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_press_pectoralis_atlas_probe.blend' --python-exit-code 1 --python 'blender/check_tsm_pectoralis_atlas_meshes.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_tsm_pectoralis_proxies.py' -- --exercise bench
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/build_tsm_pectoralis_proxies.py' -- --exercise press
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_bench_pectoralis_path_proxies.blend' --python-exit-code 1 --python 'blender/check_tsm_pectoralis_proxies.py' -- --exercise bench
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_press_pectoralis_path_proxies.blend' --python-exit-code 1 --python 'blender/check_tsm_pectoralis_proxies.py' -- --exercise press
npm run check:pectoralis-proxies
```

### 卧推与实力举三角肌三束候选网格（2026-09-25）

以 Z-Anatomy 的三角肌锁骨部、肩峰部、肩胛冈部网格，分别对照 TSM `DeltoideusClavicle_A`、`DeltoideusScapula_M`、`DeltoideusScapula_P` 路径。先用已有肱骨端部代理配准检查两种动作各五帧、每束 21 个路径采样点：网格表面最近距离的最差值为卧推前／中／后束约 **4.9／4.1／6.9 cm**，实力举约 **5.6／4.0／4.0 cm**。[初筛记录](../docs/data/tsm_deltoid_surface_screen.json)不代表真实纤维路径或附着点。

试过让近端随锁骨或肩胛骨、远端随肱骨直接线性混合：两种动作 101 帧中，网格边长比最差仅 **0.053**、最高 **2.22**，明显扭曲，因此没有进入 App。[失败方案逐帧数据](../docs/data/tsm_deltoid_two_bone_deformation_screen.json)。当前研究方案让网格主体随肱骨，只在靠近路径起点处加入 `0.25 × (1 − 路径轴投影分数)²` 的模型路径位移差。六组肌肉与动作组合的全部 101 帧边长比合计 **0.717–1.208**；路径至表面最远仍约 **6.9 cm**。[候选方案逐帧数据](../docs/data/tsm_deltoid_endpoint_deformation_screen.json)仅排除粗尺度折叠，不能验证皮肤下实际运动。

[卧推 Blender 5.1.2 场景](../assets/blender/opensim_tsm_bench_deltoid_atlas_probe.blend)、[卧推第 51 帧预览](../assets/blender/opensim_tsm_bench_deltoid_atlas_probe.png)、[实力举场景](../assets/blender/opensim_tsm_press_deltoid_atlas_probe.blend)和[实力举预览](../assets/blender/opensim_tsm_press_deltoid_atlas_probe.png)各保存 101 帧三束形态键。重开后两动作共 **30 个肌肉帧**检查五个抽样顶点及全部网格边通过；手机端使用同一公式，两动作共 **450 个坐标**与 Blender 相差最多 **2.424×10⁻⁷ m**。[卧推审查](../docs/data/tsm_bench_deltoid_atlas_probe.json)、[实力举审查](../docs/data/tsm_press_deltoid_atlas_probe.json)。这些网格只随身高整体缩放，放松臂围无法确定肩部单肌肉体积；颜色按模型整条肌肉肌腱路径长度变化，不表示三角肌纤维应变、肌电或发力。

```powershell
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_tsm_deltoid_surfaces.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_tsm_deltoid_deformation.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/probe_tsm_deltoid_endpoint_deformation.py'
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tsm_deltoid_meshes.py' -- bench
& 'D:\blender\blender.exe' --background --python-exit-code 1 --python 'blender/animate_tsm_deltoid_meshes.py' -- press
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_bench_deltoid_atlas_probe.blend' --python-exit-code 1 --python 'blender/check_tsm_deltoid_meshes.py' -- bench
& 'D:\blender\blender.exe' --background 'assets/blender/opensim_tsm_press_deltoid_atlas_probe.blend' --python-exit-code 1 --python 'blender/check_tsm_deltoid_meshes.py' -- press
npm run check:deltoid-atlas
```

### 静态完整解剖层的有限体型响应（2026-09-25）

手机的 165 网格 Z-Anatomy 静态参考层按身高相对 175 cm 等比例缩放，并按放松臂围、胸围、腰围、大腿围、小腿围对左右共 **46 块**对应肌肉网格做中段横向调整（上臂 12、胸大肌三束 6、腹外斜肌及腹直肌 4、大腿 16、小腿 8）。来源网格缺少完整头部，模型显示高度不等于输入的总身高。网格自身最长轴由顶点协方差计算，中段横向偏移按 `sin²(π·轴向比例)` 缩放，因此两端保持原位；围度比例限制在 0.80–1.20。胸围、腰围尤其不能把脂肪、骨架和单肌肉体积区分开；骨骼形状与附着点也没有个体化。静态层仍不随动作运动，也不表示真实肌肉纤维伸长或发力。

`blender/build_reference_profile_scene.py` 使用手机端同一套来源网格和宽度规则，按命令参数生成可编辑的[190 cm、胸围 118 cm、腰围 110 cm、臂围 40 cm、大腿围 66 cm、小腿围 44 cm 场景](../assets/blender/z_anatomy_profile_190_40_66_44_chest118_waist110.blend)与[预览图](../assets/blender/z_anatomy_profile_190_40_66_44_chest118_waist110.png)。样例还输入体重 90 kg 和体脂 28% 以计算未填围度的示意基线。Blender 5.1.2 保存后重开，核对 165 块网格和相机；[审查 JSON](../docs/data/z_anatomy_profile_190_40_66_44_chest118_waist110.json)记录五组围度比例、网格数及顶点最大位移。`npm run check:reference-shape` 从手机实际使用的 GLB 读取全部 165 块网格，验证 46 块围度网格可逆、两端不移动，并与 Blender 场景的五组最大局部顶点位移比较，差异小于 0.1 mm。Z-Anatomy/BodyParts3D 衍生物继续遵循 [CC BY-SA 来源声明](../public/models/NOTICE-z-anatomy.txt)。

```powershell
& 'D:\blender\blender.exe' --background --factory-startup --python-exit-code 1 --python 'blender/build_reference_profile_scene.py' -- --height-cm 190 --weight-kg 90 --body-fat-pct 28 --chest-cm 118 --waist-cm 110 --upper-arm-cm 40 --thigh-cm 66 --calf-cm 44
npm run check:reference-shape
```
