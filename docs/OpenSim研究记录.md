# OpenSim 深蹲研究记录

更新：2026-09-25。此页记录已运行的计算及未通过的产品化检查，供下一步建模使用。

## 轨迹版本与当前结论

2026-09-24 修正了教学深蹲姿态：躯干长度在动作中保持不变，双手握在示意杠铃上，并让身体加杠铃的静态重力作用线更接近足部。下文“本轮结果”“被动力、杠铃位置与质量分配敏感性”“身高与体重输入的研究性缩放”中的旧表格均基于**修正前的姿态**，只保留为历史诊断，不能与新姿态的数据直接并表比较。当前轨迹文件 `assets/opensim/squat_coordinates.sto` 的 SHA-256 为 `7b85b4f29cb8d5b0850a28519c4fa32ceb3c7727f81a17356db9e8a12623b077`；新求解结果及其版本标识见下文“修正后姿态”。旧轨迹角度文件未归档，因此仅靠目前仓库文件不能精确复现旧表格。

## 已实现的数据链

1. `src/model.ts` 在 2.8 秒内生成一次下蹲、起身的 101 帧姿态；双段逆运动学保持大腿和小腿长度。站立帧留少量膝屈，避免完全伸直时的运动学奇点。
2. `scripts/export-squat-angles.mjs` 将默认身高 175 cm 的右腿姿态换算为髋、膝、踝角度。
3. `scripts/build_opensim_lookup.py` 在 [OpenSim 官方三自由度、九肌肉深蹲模型](https://github.com/opensim-org/opensim-core/tree/main/Bindings/Java/Matlab/examples/Moco/exampleSquatToStand)中计算每帧九条肌肉的路径点、路径长度、三个关节的力臂和骨段关节中心，输出 `public/data/squat_opensim_reference.json`。App 的“OpenSim 参考”页用**同一模型数据**绘制单侧骨段与九条路径，点选肌肉可查看长度和力臂。`npm run check:opensim-lookup` 核对 101 帧、九条路径与数值一致；修正后轨迹所绘制折线路径与 OpenSim 长度的最大差异为 1.530 mm。
   同一 JSON 也经 `blender/build_opensim_squat_scene.py` 写入 [Blender 深蹲场景](../assets/blender/opensim_squat_reference.blend)，可在 101 帧时间轴查看右腿骨段和九条路径。保存后以 `blender/check_opensim_squat_scene.py` 抽查五帧共 220 项位置、长度和方向，均与 JSON 一致。这条链只证明运动学数据一致，不证明网格解剖准确或肌肉力量正确。
   JSON 还包含骨盆、右股骨和右胫骨的刚体坐标。在 Blender 中已据此驱动四块右腿解剖骨网格并抽查五帧；App 的 OpenSim 深蹲视图可选看同一组研究叠加。骨骼站姿位置只由两个包围盒中心作共同平移，尚未用真实关节中心或骨面配准。
   另以 Z-Anatomy 右股直肌网格作单肌肉形变实验：站立时五处网格切面中心与 OpenSim 路径相距约 2.1–4.7 cm；当前算法使肌腹随股骨刚体运动，并以降低到 50% 的权重在两端引入路径位移。Blender 形变文件在五帧抽样检查中符合规则、最深姿态没有网格边缩至原长一半以下；App 也可选显示紫色股直肌网格。上述检查只证明工程实现和有限的几何稳定性，不能证明真实肌肉形变、附着点或发力。
   `scripts/export_squat_attachments.py` 又导出原模型九条肌肉的 30 个路径点与八项包绕关联，包含各点所属骨段局部坐标和站立姿态坐标，见[模型附着点清单](data/opensim_squat_attachment_inventory.json)。它可供逐点配准审查，但不是 Z-Anatomy 网格的已验证附着点。
4. `scripts/solve_viewer_squat.py` 用 OpenSim MocoInverse 对相同动作轨迹求解肌肉激活和主动肌纤维力。实验分别施加 0、20、60 kg 杠铃重量。由于参考模型只有单侧下肢，代码将杠铃重量的一半作为竖直向下的定值力施加到模型躯干肩高处。该处理是实验近似。

手机端参考视图将骨段和路径几何按输入身高相对 175 cm 统一缩放，长度与力臂按相同比例显示。`scripts/probe_opensim_scaling.py` 在 OpenSim 中将模型均匀缩放 1.10 倍后，抽查的骨段、肌肉路径长度和力臂也约为 1.10 倍；这只支持几何比例处理，不代表已按用户腿长、体重或围度重建动力学参数。参考求解仍使用原始模型和参数。
前端半程深蹲页面检查：175 cm 时股中间肌路径 34.5 cm、膝力臂 2.0 cm；190 cm 时分别为 37.4 cm、2.2 cm，约按 190/175 缩放。

## 修正后姿态：质量与杠铃作用线

### 双侧实验模型与显式杠铃的组装探针

`scripts/probe_bilateral_barbell_model.py` 在 Scherpereel 等的 12 个个体缩放 `gait2354` 双腿模型上，加入质量 20 kg、长度 2.2 m 的显式杠铃刚体，用一个 `WeldJoint` 固定在躯干局部坐标 `(-0.03, 0.53, 0)` m。每个模型从 12 个骨段、12 个关节变为 13 个骨段、13 个关节，原有 54 条肌肉全部保留。中央位置的 12 份组合模型均成功保存为 `.osim` 并重新加载，质量、质心和结构数不变；三种杠铃局部前后位置的质量加权质心误差最大为 `8.9×10⁻¹⁶ m`。逐人数据见[双侧杠铃组装探针](data/bilateral_barbell_model_probe.json)，可用 `& '.cache/opensim-venv/Scripts/python.exe' scripts/probe_bilateral_barbell_model.py` 复算。

杠铃长轴在各模型的**参考姿态**中校准为地面左右方向，并在组装探针中逐一检查；偏离该姿态后它随躯干一起旋转。`scripts/export_bilateral_squat_blender_data.py` 从 AB01 的 51.0–51.5 秒实测 IK 导出 21 帧双腿骨架、54 条 OpenSim 肌肉路径及焊接杠铃，生成 [Blender 5.1 场景](../assets/blender/ab01_bilateral_squat_paths.blend)与[预览](../assets/blender/ab01_bilateral_squat_paths.png)。重新打开文件后，`blender/check_bilateral_squat_scene.py` 抽查 3 帧共 348 项路径段、关节和杠铃位置／方向。肌肉折线路径与 OpenSim 路径长度的最大误差约 `1.1×10⁻¹⁶ m`，见[导出数据](../assets/blender/ab01_bilateral_squat_kinematics.json)。这只核对运动学转写；场景没有上肢、解剖网格绑定或肌肉力着色。在这段短片里，杠铃两端最大高差约 0.36 m，表明刚性躯干焊接不是可信的真实握持约束。

AB01、AB02 使用已经复算的实验 IK 片段中右膝最深帧检查组合体，其余十人在源模型默认姿态检查结构；后者不是站立动作。此处的杠铃连接点是研究假定，没有上肢、握持约束、足地接触或实测杠铃轨迹。偏移是在**旋转的躯干局部 x 轴**上做 ±6 cm，不等于手机示意动画中的地面水平 ±6 cm；例如 AB01 最深帧，两端杠铃质心高度相差约 8.6 cm。组装成功也没有求出地面反力、关节净力矩或肌肉力，不能据此给手机发力高亮赋值。尤其 12 个模型的最大等长肌肉力量参数仍完全相同，没有实现用户力量标定。

### 实测自重深蹲的双腿静态优化质量门槛

`scripts/probe_full_bilateral_static_optimization.py` 从同一公开数据取 AB01 的 51.0–51.5 秒自重深蹲，输入已经复算的双腿 IK 和双力板地面反力，在 54 条肌肉模型上运行 [OpenSim Static Optimization](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53085189)，并为 23 个坐标加入残余／辅助执行器；`scripts/audit_full_bilateral_static_optimization.py` 按逐帧日志检查求解状态。此探针**使用了实测外力和姿态**，不是只凭手机身体参数、训练记录与预设动作预测肌肉力；也没有使用上段新建的杠铃模型。

OpenSim 工具整体返回成功并写出文件，但 101 帧中有 **73 帧优化失败**。剩余 28 帧内，达到 `≥0.99` 激活的肌肉数逐帧中位数为 **12 条**；骨盆平移残余力最大分量约 **40 N**，骨盆旋转残余力矩最大约 **49 N·m**，左髋旋转辅助力矩最大约 **47 N·m**。逐帧失败时间与分项峰值见[双腿静态优化审查](data/full_bilateral_static_optimization_audit.json)。这些是对当前设置的拒绝信号，不能将输出肌肉力解释为真实肌肉分担，失败帧的数值尤其不得使用。下一步须复核源模型肌肉容量、缺失的自由度与姿态、力板作用点及残余执行器配置，并在独立肌电趋势上验收。手机端仍不显示个人发力红色高亮。

为定位失败，保持同一 101 帧、外力、姿态与求解器设置，仅关闭 OpenSim 静态优化的肌肉生理约束，再运行一次；仍有 **73/101 帧**失败，成功帧的肌肉饱和中位数仍为 12 条，见[关闭生理约束对照](data/full_bilateral_static_optimization_no_physiology_audit.json)。两个配置的失败帧并非完全相同，但主要问题没有消失。将最深蹲附近 51.25–51.35 秒的迭代上限从 100 提到 500 后，原本 **21/21 帧**失败，仍有 **20/21 帧**失败；唯一成功帧需要约 **102 N** 骨盆竖直辅助力，见[高迭代对照](data/full_bilateral_static_optimization_high_iteration_audit.json)。这两项对照不支持把问题简单归因于生理约束过严或迭代次数不足。

`scripts/audit_bilateral_joint_capacity.py` 在 51.32 秒用重新复算的实验 ID 关节净力矩及完整 IK 姿态，逐个旋转坐标计算一个**故意乐观的独立上界**：把所有能产生目标方向力矩的模型肌肉力臂乘以各自最大等长力后相加，不考虑力长关系，也不要求它们同时满足其他关节。即便如此，左／右髋旋转需求与容量比为 **9.20／5.25**，右膝为 **1.22**，腰椎伸展为 **1.23**；在 51.25–51.35 秒的 21 帧中，双侧髋旋转及腰椎伸展均 21 帧超界，右膝 20 帧超界。骨盆自由关节和脚趾关节没有有效肌肉驱动，需由残余或其他结构处理。逐项数据见[双腿最深蹲容量审查](data/bilateral_deep_squat_joint_capacity.json)。这一审查指向模型参数、坐标／力板对齐或遗漏结构的问题；**不能**把大比例直接解释为受试者真实肌肉无力，也不能用调大肌肉力量绕过验证。

为避免只看一人，沿用同样方法核对 AB02 的另一段自重深蹲。23.65–23.75 秒的 21 帧中，右髋旋转、左髋旋转和腰椎伸展也都逐帧超过乐观独立容量，需求／容量比中位数分别为 **4.84、1.77、1.29**；右膝在这段没有超界。[AB02 逐坐标数据](data/bilateral_deep_squat_joint_capacity_AB02.json)支持优先检查两人的髋旋转与腰椎链，而不能据 AB01 右膝现象推断所有人都会出现相同失败。

最初的复算 ID **包含原始力板文件的自由力矩向量**，与源作者逐坐标结果不一致：按 N·m/kg 假设将原始 `Joint_Moments.csv` 乘体重后，AB01 最深 21 帧右／左髋旋转力矩的源数据幅值中位数约 **44／50 N·m**，此配置复算约 **64／94 N·m**；逐帧平均绝对差约 **19.3／43.2 N·m**。AB02 对应差约 **15.3／13.4 N·m**。使用原始 CSV 作为目标，AB01 双侧髋旋转需求／54 肌肉容量比中位数仍约 **3.53／4.76**，AB02 约 **3.74／2.44**，四组各 21 帧均超界。力矩是逆动力学结果，这仍只是**模型容量警报**，不表示人体真实无力。

`scripts/reproduce_dynamic_squat_id.py --omit-free-moment` 只移除两块力板的自由力矩，保持同一模型、IK、力板三轴力、压力中心与 6 Hz 坐标低通。`scripts/audit_deep_hip_id_alignment.py` 同时审查六个髋部坐标：AB01 最深 21 帧原先的 8–43 N·m 平均绝对差降至 **0.001–0.002 N·m**，两秒片段避开边缘后的 241 帧六坐标均不超过 **0.01 N·m**。AB02 最深片段的六坐标误差降至 **0.25–3.24 N·m**，中间 241 帧为 **0.36–2.21 N·m**。[逐坐标受控对照](data/deep_squat_hip_id_alignment.json)强烈表明源 CSV 的计算约定与**不加入自由力矩**的 ID 一致，也进一步支持 CSV 按 N·m/kg 乘体重；但原作者的实际设置文件未公开，本实验不能证明其全部处理步骤。AB01 六个对应 IK 角度平均绝对差 ≤0.004°，AB02 在当前精度下完全一致，因此姿态误差不是原先大差额的主要原因。该结果提高了**关节净力矩**输入的可复算性，仍未验证肌肉力分担。

### 92 肌肉官方下肢模型替换筛查

从 [OpenSim 官方模型仓库](https://github.com/opensim-org/opensim-models/tree/master/Models/Gait2392_Simbody) 的提交 `d9b05d4` 取得 `gait2392_millard2012muscle.osim`，只放在 `.cache/model-candidates/` 作研究对照。模型文件自身注明 CC BY 3.0；OpenSim 4.6 能加载 12 个骨段、23 个同名坐标及 **92 条肌肉**，默认总质量约 75.16 kg。[OpenSim 模型表](https://opensimconfluence.atlassian.net/wiki/spaces/OpenSim/pages/53090607)明确提醒此模型在深膝屈动作可能不准确，因此它也不是可直接发布的深蹲模型。

用**未按受试者缩放**的 92 肌肉模型、相同 AB01／AB02 实验 IK 和原始 CSV 力矩，再算同一个主动等长独立关节容量上界：

| 受试者 | 54 肌肉模型：右／左髋旋转需求容量比中位数 | 92 肌肉模型：右／左髋旋转需求容量比中位数 |
| --- | ---: | ---: |
| AB01 | 3.53／4.76 | 2.64／3.27 |
| AB02 | 3.74／2.44 | 4.53／2.86 |

四组仍各有 21/21 帧超界；AB01 右膝源 CSV 比值中位数也由 1.11 变为 1.49。逐坐标结果见[AB01 92 肌肉探针](data/gait2392_deep_squat_capacity_AB01.json)与[AB02 探针](data/gait2392_deep_squat_capacity_AB02.json)。默认模型质量与个体质量相差约 5–9%，几何及力量也未个体化；这些数值只能筛查“直接替换”能否消除缺口，不能作为两个模型的有效生理优劣排名。增加肌肉数量没有自动解决髋旋转问题；应继续核对源逆动力学、关节定义、肌肉力臂和生理参数。

### 高屈曲双腿模型候选与髋旋转轴复核

从 [OpenSim 官方 Rajagopal 模型目录](https://github.com/opensim-org/opensim-models/tree/master/Models/Rajagopal) 的同一提交 `d9b05d4` 读取 `RajagopalLaiUhlrich2023.osim`。[目录说明](https://github.com/opensim-org/opensim-models/blob/master/Models/Rajagopal/README.txt)记载此版本结合 Lai 的高髋／膝屈曲路径修正及后续肌肉、髋外展参数修改。本机 OpenSim 4.6 读出 22 个骨段、39 个坐标、80 条下肢肌肉；模型上肢没有对应的肌肉驱动，不可用它完成卧推或实力举的发力计算。模型副本仅保留在被 Git 忽略的 `.cache/` 研究目录；审查脚本保存在项目的 `scripts/` 和 `blender/`。官方仓库根页面未列出许可，模型文件与目录说明也未标明许可；目录说明明确该文件改编自多位作者的模型，不能根据同类软件仓库的许可推定其发布权。发布用模型的权利条款仍须逐文件核实。

`scripts/audit_high_flex_candidate.py` 将 AB01、AB02 各 101 帧的实验 IK 暂映射到该模型，同名坐标照抄、膝角反号。模型双膝允许屈曲 0–140°：AB02 全部 101 帧在范围内；AB01 有 22 帧右膝超界，最多超出 2.32°。三个抽样时刻，源模型与候选模型股骨轴夹角约 0.5–3.1°，胫骨轴夹角约 2.6–6.6°。这只说明姿态映射初步可用；身体几何、关节中心、路径和外力尚未做精确配准。见[关节范围与姿态审查](data/high_flex_squat_candidate_audit.json)。

`scripts/audit_high_flex_hip_capacity.py` 只在两膝均未超界的最深片段，比较原受试者 54 肌肉模型与候选 80 肌肉模型。目标力矩取作者原始 CSV 的髋旋转列，按前述证据暂以 N·m/kg 乘体重；容量仍为**逐关节、主动等长、所有同向力臂同时给满最大力的乐观上界**。同一行的两个比值只在同一批有效帧比较；它们不能与上段完整 21 帧结果直接作比例比较。

| 受试者及有效帧 | 原 54 肌肉：右／左髋需求÷容量中位数 | 高屈曲 80 肌肉：右／左髋需求÷容量中位数 |
| --- | ---: | ---: |
| AB01：最深片段 4/21 帧 | 3.09／3.96 | 1.27／1.38 |
| AB02：最深片段 21/21 帧 | 3.74／2.44 | 2.07／1.61 |

高屈曲模型使此计算中的缺口缩小，但四组仍全部逐帧超出这个乐观上界。特别是 AB02 右髋，原 CSV 目标力矩中位数约 52.2 N·m，而候选模型上界约 25.2 N·m。为检查坐标方向，脚本以股骨姿态对髋旋转坐标做有限差分：同一时刻两个模型的右／左髋轴点积在 AB01 为 1.000，在 AB02 至少 0.99887；此次差异因此不能简单归咎于髋旋转轴反向。候选模型仍是 75.34 kg 通用参数，没有按两位受试者的体段几何、肌肉最大力量和真实路径标定，原 CSV 单位与逆动力学设定也有残余不确定性。**这不是人体真实力量上限，更不是可以给 App 红色发力高亮的肌肉力结果。**逐帧摘要见[高屈曲髋容量审查](data/high_flex_hip_capacity_audit.json)。

#### 按个体骨段长度缩放后的复核

上述未缩放模型有实质性几何差异：AB02 的源模型膝至踝约 47.65 cm，候选模型约 39.65 cm；AB01 分别约 48.56／39.65 cm。[原始关节尺寸探针](data/high_flex_segment_probe.json)还记录了髋宽、髋至膝和踝至跖趾关节距离。`scripts/probe_high_flex_scaled_capacity.py` 以各人片段第一帧的这些关节中心距离计算骨盆、左右股骨、胫骨及足段的**逐体段统一比例**，调用 OpenSim `Model.scale`，并将候选模型总质量约束为该受试者源模型总质量。首帧选取尺寸在数值精度内对齐；在有效最深片段，髋至膝有效距离因两模型膝关节运动函数不同仍最多偏差 AB01 3.38%、AB02 1.46%。这不是用真人测量点重新做的完整个体标定。

| 有效最深片段 | 未缩放 80 肌肉：右／左髋需求÷容量中位数 | 骨段缩放后：右／左髋需求÷容量中位数 |
| --- | ---: | ---: |
| AB01：4 帧 | 1.27／1.38 | 1.44／1.57 |
| AB02：21 帧 | 2.07／1.61 | 2.00／1.55 |

缩放后四组仍**每帧超过乐观独立等长容量**。AB02 右髋的源 CSV 目标力矩中位数约 52.2 N·m，缩放后的容量约 26.1 N·m；改用上段“不加自由力矩”的独立 ID，AB01 右／左比值仍为 1.44／1.57，AB02 为 1.92／1.49，四组仍逐帧超界。OpenSim 此次几何／质量缩放使 80 条肌肉的最大等长力参数**完全不变**（逐肌肉缩放比均为 1.0），所以它仍缺少训练记录或实验测得的个人强度标定。AB01 的骨盆按髋宽统一缩至 0.819 倍，躯干和各体段质量比例也没有逐项对照测量；这些人为缩放选择会改变路径和力臂。该复核排除了“只因通用胫骨较短”这一单一解释，不能证明模型肌力或真实肌肉分担正确。[完整缩放与容量摘要](data/high_flex_segment_scaled_capacity.json)保留两套输入、各段比例和逐组误差。

进一步在每个有效姿态把 80 条肌肉设为 1% 激活、零速度并做静态肌纤维平衡，计算**被动肌纤维沿腱力 × 带符号髋旋转力臂**之和。以下均用不加力板自由力矩的独立 ID 为目标；被动力矩为正，而四组目标力矩均为负，故被动肌肉在此姿态下抵消所需方向，不能填补主动容量缺口。

| 最深片段 | 右／左被动肌纤维力矩中位数 N·m | 扣除被动后，右／左剩余需求÷乐观主动容量中位数 |
| --- | ---: | ---: |
| AB01：4 帧 | +6.36／+7.11 | 1.68／1.83 |
| AB02：21 帧 | +4.93／+9.40 | 2.11／1.79 |

这只是零速度、最低激活的**模型内被动肌纤维快照**；未包含动作速度引起的阻尼、韧带／关节囊、足地接触反力分担或个体组织参数。上表分母仍是所有同向肌肉都能同时达到最大等长力的独立单关节乐观量，不是实际肌力求解。四组在扣除被动后仍每帧超界；下一步需校准最大肌力和肌腱参数，并做独立肌电检查。

#### 双髋六轴同时可行性

`scripts/audit_high_flex_multiaxis_hip_capacity.py` 使用同一受试者 IK、不加入力板自由力矩的独立 ID，以及按骨段长度和总质量缩放后的 80 肌肉候选模型。先将源模型每侧三个广义力矩换算成空间髋关节力矩，再投影到候选模型的髋屈伸、内收和旋转轴；本次有效帧里同名轴点积在 AB01 均为 1.000、AB02 最低为 0.998834。对双髋六个目标力矩同时求线性规划：每条肌肉张力非负、最多为其名义最大等长力的共同倍率 `s`，寻找最小 `s`。约束重建残差低于输出的 10⁻⁸ N·m 精度。为对照，也分别计算六个轴各自最乐观的倍率下界。

| 最深片段的候选膝角有效帧 | 每帧六轴同时可行 | 名义强度 `s ≤ 1` 可行 | 最小共同倍率中位数（范围） | 单轴下界最大值的逐帧中位数 |
| --- | ---: | ---: | ---: | ---: |
| AB01：4 帧 | 4 | 0 | 3.37（3.18–3.57） | 1.56 |
| AB02：21 帧 | 21 | 0 | 2.99（2.82–3.04） | 1.71 |

相同肌肉会同时产生多个轴的力矩，因此单轴容量不能相加使用。这次多轴计算把之前的“旋转轴超界”进一步定位为**名义参数下的双髋力矩联合不可行**。它仍是极乐观的模型诊断：忽略肌纤维力长速关系、被动组织、其他关节需求、共同收缩与接触约束；骨段缩放也没有真实测量点和逐肌肉强度校准。`s` 不等于受试者力量倍率，也不是某条肌肉的发力数值。不能据此在 App 中给肌肉标红。逐帧目标、轴映射和求解结果见[双髋六轴审查](data/high_flex_multiaxis_hip_capacity.json)。

`scripts/audit_high_flex_hip_knee_ankle_capacity.py` 又把双膝屈伸和双踝跖屈／背屈加入同一规划，共十个轴。候选模型膝关节坐标方向与源模型相反，脚本按转轴点积映射目标力矩；膝、踝轴点积绝对值在 AB01 所有有效帧不低于 0.973、AB02 不低于 0.969。两组每帧的最小共同倍率在保留四位小数后均与六轴结果相同，说明**此参数和这些帧里髋部六轴是首要瓶颈**，不是说膝、踝肌力已独立验证。候选模型的距下与跖趾关节被锁定，所以没有把它们的源 ID 力矩硬塞进约束。膝、踝对应转轴最大相差约 14°，投影舍弃了垂直于候选轴的分量；还未加入骨盆、腰椎、接触和肌腱动力学。[十轴逐帧审查](data/high_flex_hip_knee_ankle_capacity.json)记录了每个轴的方向点积和求解残差。

同一十轴脚本再以 1% 激活、全部坐标零速度做静态肌纤维平衡，逐肌肉计算被动肌纤维沿腱力，按同一力臂从目标净力矩中扣除后重求主动容量倍率。髋旋转被动力矩中位数复现了上表的 AB01 右／左 +6.36／+7.11 N·m、AB02 +4.93／+9.40 N·m；十轴最小倍率中位数随之由 3.37 升至 **3.86**（AB01），由 2.99 升至 **3.79**（AB02）。这只是沿用固定被动力快照、仍允许每条肌肉达到名义最大等长主动拉力的数学检查。它没有按姿态和速度计算真实主动能力，也没有让被动力随人为强度倍率重新平衡，不能解释为两位受试者需要真实肌肉力量增加 3–4 倍。

#### 完整动作与同试次肌电的先验筛查

`scripts/audit_high_flex_full_squat_capacity.py` 将同一十轴诊断延伸到两人各自完整的两秒自重深蹲片段，每 20 ms 取一帧。AB01 的 101 个样本有 5 帧超出候选模型 140° 膝角范围；其余 96 帧中 **75 帧**可在名义最大等长力内同时配平，21 帧不可。AB02 的 101 帧均在范围内，其中 **74 帧**名义可行，27 帧不可。最小倍率峰值为 AB01 3.55、AB02 3.04；加入固定被动力快照后峰值为 3.95、3.83。缺口主要出现在较深屈膝阶段，而非整段动作都超界。[逐帧范围和解算结果](data/high_flex_full_squat_capacity.json)仍以实验 IK 与 ID 为输入，不是仅凭手机输入的预测。

`scripts/benchmark_high_flex_emg_trend.py` 做了一项更严格但规模很小的反证检查：人为统一把候选模型名义最大等长力放大 4.2 倍，使选取的十轴问题可行；每 100 ms 在同源实验 IK／ID 上，以“归一化张力平方和最小”先验求一组非负肌肉张力，再与**未参与求解**的同试次 20–450 Hz 滤波、100 ms RMS 表面肌电按时间比较。AB01 有 20 个有效帧，AB02 有 21 个；求解器均配平力矩，但 16 个对应电极通道里，AB01 只有 **4/16** 个模型张力趋势与肌电的 Spearman 绝对相关高于仅用膝屈角的基线；AB02 是 **8/15** 个可比较通道。AB01 右股直肌为模型 0.764、膝角 0.899；右臀中肌为模型 −0.570、膝角 +0.916。改用 6.0 倍人为强度后，优于膝角基线的通道为 4/16、9/15，结论没有变成全面优势。[4.2 倍逐通道结果](data/high_flex_squat_emg_prior_pilot.json)及[6.0 倍敏感性](data/high_flex_squat_emg_prior_6x_sensitivity.json)保留全部结果。

这不是“预测激活”的独立验证：模型解直接吃进实验姿态与关节力矩，电极只测局部电活动而非肌肉拉力，分肌头对应也近似；两个受试者、约 20 个高度相关的时间点没有总体外推能力。数值相关不能把人为的 4.2／6.0 倍强度变成真人标定。这个对照显示当前最小平方先验尚无稳定的简单基线优势，因此**仍不能给手机模型发布个人红色发力图**。

#### 候选模型自身逆动力学与静态优化复核

上述容量筛查把**原 54 肌肉个体模型**的逆动力学力矩投影到高屈曲候选模型坐标；两种模型的体段惯量与质心不同，投影并不等于候选模型自己的动力学需求。`scripts/reproduce_high_flex_candidate_id.py` 用同一 AB02 实测姿态和力板（不含力板自由力矩）在按关节中心距离和总质量缩放的 80 肌肉候选模型上重算逆动力学。23.60–23.70 秒深屈膝的 21 帧里，右髋旋转力矩中位数从原模型投影的 **−41.70 N·m** 变为候选模型自己的 **−53.82 N·m**，逐帧差额中位 **−12.13 N·m**；骨盆竖直残余力中位从 **+8.84 N** 变为 **−30.65 N**。所以前文 2.99 倍等数字应严格解读为“原模型力矩投影下的候选肌肉容量”，不能直接当作候选模型的完整需求。[逐轴对照](data/high_flex_candidate_id_alignment.json)。

`scripts/audit_high_flex_candidate_id_capacity.py` 再用候选模型自身逆动力学，约束双髋、双膝、双踝共十轴。忽略力长速及被动力时，21 帧名义最大等长肌力的最小统一倍率中位 **3.51**，范围 **3.23–3.80**；人为给所有肌肉设 4.2 倍则这十轴 21 帧都可行。扣除一个零速、低激活的固定被动力快照后，倍率中位升为 **4.46**，范围 **4.20–4.70**，4.2 倍仅 **1/21 帧**可行。十轴规划没有约束骨盆、腰椎、足部和接触，也没有真正的肌纤维力长速动态；这些倍率只是当前模型的诊断量。[候选 ID 十轴容量](data/high_flex_candidate_id_capacity.json)。

为检查完整 OpenSim 肌肉生理与辅助执行器，`scripts/probe_high_flex_static_optimization.py` 以候选模型、同一实测姿态／力板和人为 4.2 倍肌肉最大等长力运行 `StaticOptimization`。`scripts/audit_high_flex_static_optimization.py` 从警告日志逐帧排除未收敛输出。浅屈膝 23.00–23.10 秒有 **21/21 帧**没有优化失败警告，但骨盆竖直辅助力峰值仍达 **138.6 N**，骨盆侧倾辅助力矩 **48.7 N·m**。深屈膝 23.60–23.70 秒启用肌肉生理时 **13/21 帧失败**，其余 8 帧均有肌肉达到激活上限，右／左髋旋转辅助力矩峰值 **7.17／8.02 N·m**。关闭生理约束后仍有 **2/21 帧失败**，其余 19 帧均有饱和肌肉。再把下肢关节辅助执行器的每单位控制力矩从 1 降为 0.01 N·m，以加大使用代价，深屈膝后半段 **10/21 帧失败**；只有前 11 帧收敛，不能用失败帧的巨大骨盆辅助力作物理结论。所有上述最大值均只在没有失败警告的帧中计算。OpenSim 的整体 `tool.run()` 返回成功和输出 21 行，并**不**代表逐帧收敛。[逐帧收敛及辅助力审查](data/high_flex_static_optimization_audit.json)。

把试验性最大等长力进一步统一提到 **6 倍**，深段的 21 帧均没有优化失败警告，髋／膝／踝辅助力矩峰值降到右髋旋转 **0.063 N·m**；但双侧股二头肌长头在 **21/21 帧**都处于激活上限，骨盆竖直辅助力峰值仍为 **39.8 N**、侧倾辅助力矩 **48.4 N·m**。因此收敛改善不等于全身动力学匹配或个人力量被测得；这些参数没有个体训练记录校准。

候选模型仍缺少个体惯量、真实负重位置和经过验证的上肢／躯干肌肉分担；浅段的骨盆辅助力和深段的饱和、未收敛已经不满足个人发力结果的发布门槛。下一步应先校准完整动力学与辅助力，再用未参与拟合的实验肌电／动作条件验收；当前结果不进入手机端肌肉力着色。

为直接查看候选模型在实测动作上的肌肉路径，`scripts/export_high_flex_squat_blender_data.py` 从 AB02 的 23.4–23.9 秒 IK 每 25 ms 取一帧，写出 21 帧双腿关节与 80 条下肢肌肉的当前路径。`blender/build_high_flex_squat_scene.py` 在 Blender 5.1.2 中制作了[本地场景](../.cache/high-flex-scene/ab02_high_flex_paths.blend)和[预览](../.cache/high-flex-scene/ab02_high_flex_paths.png)。肌肉路径相对**片段第一帧**变长偏青蓝、变短偏紫、变化较小偏灰；左右路径的基底色略有区别。这里比较的是整个肌腱路径长度，第一帧也不是生理静息长度，**没有力或激活红色着色**。OpenSim 当前路径点间用直线显示，所有帧的直线总长与模型路径长度最大差约 1.40 mm，包绕曲面弧线未逐点复原；小于 0.5 mm 的折线段在场景中隐藏。重新打开 `.blend` 后，`blender/check_high_flex_squat_scene.py` 抽查第 1、12、21 帧共 1860 项路径段、长度比、颜色和关节位置／方向通过。场景和完整模型 JSON 保存在 Git 忽略的 `.cache/`，只供本机结构审查；它没有解剖网格、个人化缩放、上肢发力模型或经过验证的肌肉力量。

当官方模型候选和公开实验片段已按[动态数据说明](动态深蹲验证数据.md)放入上述 `.cache/` 路径后，可在项目根目录复算：

```powershell
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_candidate.py
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_hip_capacity.py
& .cache/opensim-venv/Scripts/python.exe scripts/probe_high_flex_segment_scaling.py
& .cache/opensim-venv/Scripts/python.exe scripts/probe_high_flex_scaled_capacity.py
& .cache/opensim-venv/Scripts/python.exe scripts/audit_deep_hip_id_alignment.py
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_multiaxis_hip_capacity.py
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_hip_knee_ankle_capacity.py
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_full_squat_capacity.py
& .cache/opensim-venv/Scripts/python.exe scripts/benchmark_high_flex_emg_trend.py
& .cache/opensim-venv/Scripts/python.exe scripts/benchmark_high_flex_emg_trend.py --strength-multiplier 6.0 --output docs/data/high_flex_squat_emg_prior_6x_sensitivity.json
& .cache/opensim-venv/Scripts/python.exe scripts/reproduce_high_flex_candidate_id.py
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_candidate_id_capacity.py
& .cache/opensim-venv/Scripts/python.exe scripts/probe_high_flex_static_optimization.py --subject AB02 --start 23 --end 23.1 --strength-multiplier 4.2 --verbose-warnings *> .cache/lower-limb/high-flex-so-shallow-physiology-warn.log
& .cache/opensim-venv/Scripts/python.exe scripts/probe_high_flex_static_optimization.py --subject AB02 --start 23.6 --end 23.7 --strength-multiplier 4.2 --verbose-warnings *> .cache/lower-limb/high-flex-so-deep-physiology-warn.log
& .cache/opensim-venv/Scripts/python.exe scripts/probe_high_flex_static_optimization.py --subject AB02 --start 23.6 --end 23.7 --strength-multiplier 4.2 --disable-muscle-physiology --verbose-warnings *> .cache/lower-limb/high-flex-so-deep-no-physiology-warn.log
& .cache/opensim-venv/Scripts/python.exe scripts/probe_high_flex_static_optimization.py --subject AB02 --start 23.6 --end 23.7 --strength-multiplier 4.2 --disable-muscle-physiology --joint-reserve-optimal-force 0.01 --verbose-warnings *> .cache/lower-limb/high-flex-so-deep-no-physiology-penalty-warn.log
& .cache/opensim-venv/Scripts/python.exe scripts/probe_high_flex_static_optimization.py --subject AB02 --start 23.6 --end 23.7 --strength-multiplier 6 --verbose-warnings *> .cache/lower-limb/high-flex-so-deep-physiology-6x-warn.log
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_static_optimization.py
& .cache/opensim-venv/Scripts/python.exe scripts/audit_high_flex_candidate_id_alignment.py
& .cache/opensim-venv/Scripts/python.exe scripts/export_high_flex_squat_blender_data.py
& D:\blender\blender.exe -b -t 4 --python blender/build_high_flex_squat_scene.py
& D:\blender\blender.exe -b .cache/high-flex-scene/ab02_high_flex_paths.blend -t 4 --python blender/check_high_flex_squat_scene.py
```

下一步用同一受试者**真实测量点**完整缩放和校准候选模型，并追查 AB02 髋旋转原始／重算 ID 的剩余差额；随后加入骨盆、腰椎和足地接触约束，在更多受试者与匹配动作中预先规定肌电趋势验收门槛。即使某个参数组合使十轴可行，也不能直接得到可信的单肌肉力量。

`scripts/export_squat_mass_template.py` 从公开数据集的 12 个缩放 `gait2354` 模型抽取体段质量比例。这 12 份模型的比例在机器精度内相同，因而它们提供的是**一套模板比例**，不是 12 人独立的局部质量分布测量。模板见 [JSON](../src/data/squat_mass_template.json)。`squatBalanceEstimate` 按用户体重缩放这些比例，用示意骨架估计躯干、骨盆和双腿的分段质心，再与杠铃质量及位置合成静态重力作用线；手臂质量并入躯干近似，没有实测身体分段质心。

旧姿态在默认 175 cm、72 kg、20 kg 杠铃的最深帧，把身体加杠铃的合成重力作用线放在右踝后方约 16.8 cm。修正后的同一情景约在右踝后方 2.0 cm，杠铃作用线约在踝前方 7.5 cm，合重力约 902 N。逐姿态与负重情景见[新探针](data/squat_balance_probe.json)和[旧探针](data/squat_balance_legacy_pose.json)。这只是**零加速度静态平衡的必要几何关系**，不能证明整个动作的稳定性：足底压力中心、地面反力、身体加速度、真实杠铃轨迹及个体体段质量均未测量。手机端显示这个情景的重力合力与位置，同时继续把关节表格明确标为杠铃外力矩，未推出关节净力矩或单肌肉力。

基于同一模板质心和 2.8 秒人工深蹲动画，`scripts/probe_squat_dynamic_grf.mjs` 进一步用逐帧二阶差分试算了 (F_y=m(g+a_{COM,y}))。默认 72 kg 加 20 kg 杠铃情景约为 839–1007 N（静态重量的 0.93–1.12 倍）；三组体型、三种负重的[逐帧探针](data/squat_dynamic_grf_probe.json)均只属于**人工轨迹**。独立实验的两段自重深蹲显示，加速度项对力板垂直力至关重要，见[动态数据核查](动态深蹲验证数据.md)；那两段实测姿态与本 App 的人工动画并不相同，因此不能用它们给这个 839–1007 N 区间背书。动态力值暂不进入手机界面，直到时间轨迹、接触与负重位置经对应实测动作验证。

## 修正后姿态：研究性 Moco 对照

相同的修正后姿态、单腿模型和半躯干质量近似下，新增了随动画变化的杠铃竖直作用线。它仍是施加给躯干的规定外力，不是有质量和握持约束的真实杠铃。以下为最深帧；±6 cm 是杠铃作用线的人工前后偏移。原始版本号、其余肌肉指标和辅助力矩见[新求解摘要](data/revised_squat_moco_summary.json)。

| 情景 | 臀大肌激活 | 臀大肌主动纤维力 | 股中间肌主动纤维力 | 踝辅助力矩峰值 |
| --- | ---: | ---: | ---: | ---: |
| 自重 | 0.005 | 17 N | 2522 N | 0.041 Nm |
| 20 kg，默认作用线 | 0.247 | 788 N | 4461 N | 0.049 Nm |
| 60 kg，默认作用线 | 0.607 | 1946 N | 9053 N | 0.069 Nm |
| 60 kg，前移 6 cm | 0.700 | 2249 N | 9437 N | 0.038 Nm |
| 60 kg，后移 6 cm | 0.513 | 1644 N | 8667 N | 0.106 Nm |
| 60 kg，关闭被动力 | 1.000 | 3173 N | 11216 N | 0.032 Nm |

六组优化器均报告收敛，但关闭被动力时臀大肌激活达到 1.000 上限；日志仍有模型组装和比目鱼肌肌腱松弛长度警告。几厘米作用线变化就显著改变肌肉分担，关闭被动力更改变结果。因此即使新姿态的辅助力矩较小，也不能据此验证这些肌肉力。模型缺少个体强度标定、双腿及真实足地接触，**这些力不进入 App 发力高亮**。

## 修正前姿态：初始求解结果（历史）

三组初始配置的优化均收敛。下蹲最深帧的数据如下，数值仅属于当前参考模型，不对应用户本人：

| 杠铃重量 | 股中间肌激活 | 股中间肌主动肌纤维力 | 胫骨前肌激活 | 臀大肌激活 | 踝关节辅助力矩峰值 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 kg | 0.443 | 6830 N | 0.775 | 0.000 | 0.054 Nm |
| 20 kg | 0.539 | 8368 N | 0.876 | 0.000 | 0.063 Nm |
| 60 kg | 0.728 | 11431 N | 1.000 | 0.000 | 9.817 Nm |

这些结果说明增加负重时股中间肌需求在该模型中上升，也暴露了明显缺陷：初始 60 kg 配置中胫骨前肌达到控制上限，踝关节还需要明显的辅助力矩；臀大肌在三组的最深帧都没有被优化器主动招募。辅助力矩按 `ModOpAddReserves(2)` 的 2 Nm/控制单位换算。“优化收敛”不能当作发力分布已可信的证据。当前 **不把这组激活和力量映射为 App 中的红色发力高亮**。

## 修正前姿态：被动力、杠铃位置与质量分配敏感性（历史）

为追查异常，以相同轨迹做了受控对比。表中臀大肌、胫骨前肌为最深帧激活，踝辅助力矩为整段绝对峰值；`passive force multiplier` 是臀大肌归一化被动力曲线值，不是以牛顿计的力。

| 配置 | 臀大肌激活 | 臀大肌被动力系数 | 胫骨前肌激活 | 踝辅助力矩峰值 |
| --- | ---: | ---: | ---: | ---: |
| 0 kg，初始被动力设置 | ≈0 | 0.272 | 0.775 | 0.054 Nm |
| 0 kg，关闭全部肌肉被动力 | 0.131 | 0 | 0.771 | 0.054 Nm |
| 60 kg，初始作用点 | ≈0 | 0.272 | 1.000 | 9.817 Nm |
| 60 kg，关闭全部肌肉被动力 | 0.248 | 0 | 1.000 | 9.264 Nm |
| 60 kg，作用点在躯干局部前移 0.12 m | 0.105 | 0.270 | 0.791 | 0.055 Nm |
| 60 kg，作用线全程固定在踝关节上方 | 0.114 | 0.270 | 0.795 | 0.056 Nm |
| 0 kg，躯干与骨盆质量/惯量减半 | ≈0 | 0.272 | 0.391 | 0.025 Nm |
| 60 kg，固定作用线且躯干与骨盆质量/惯量减半 | 0.054 | 0.271 | 0.409 | 0.026 Nm |

原始作用点在最深姿态时的竖直作用线位于踝关节后方约 11.8 cm；局部前移 0.12 m 后接近踝关节上方，但在站立帧会跑到踝关节前方约 8.7 cm。前移实验使踝辅助力矩峰值由 9.817 Nm 降至 0.055 Nm；把作用线在整个动作中固定于踝关节上方的另一个对照得到 0.056 Nm。两者共同说明原异常主要受器械作用点影响，而不只是求解器本身。关闭被动力后臀大肌开始被主动招募，说明“臀大肌近零激活”还受到肌肉被动力参数影响。实验同时说明：没有明确杠铃位置与肌肉参数时，同一关节轨迹可以得到明显不同的“发力图”。两种作用线方案都只是模型敏感性实验；尤其固定地面作用线不模拟杠铃与身体的真实连接，不能据此发布发力指导。

官方参考模型的当前单腿系统总质量约为 53.27 kg，其中躯干 26.83 kg、骨盆 11.78 kg。作为双侧对称的**纯实验近似**，只把躯干和骨盆的质量及惯量减半、保留右腿质量，总质量降到约 33.96 kg。最深帧胫骨前肌激活在 60 kg 固定作用线条件下从 0.795 降到 0.409。这表明单腿模型如何分摊共享躯干质量会显著改变预测。该设置没有依据用户身高、体重或体脂校准，也没有验证其力与运动学的生理真实性。

逐项数值保存在[旧深蹲敏感性计算摘要](data/squat_sensitivity_summary.json)。原始解、输出和优化日志留在 `.cache/moco-viewer-squat/`；修正前轨迹文件未归档，当前命令不能精确重建这些旧数值。几组结果都来自同一模型、同一预设姿态和不同的人工参数选择，不是独立实验验证。

## 修正前姿态：身高与体重输入的研究性缩放（历史）

`scripts/probe_person_scaling.py` 将单腿模型的躯干和骨盆质量及惯量先减半，再按身高相对 175 cm 均匀缩放所有体段几何，并用 [OpenSim `Model.scale` API](https://opensim-org.github.io/opensim-moco-site/docs/1.3.0/html_user/classOpenSim_1_1Model.html) 的 `finalMass=体重/2` 将模型总质量调整为半个用户体重。`finalMass` 是对模型质量的约束，不会识别局部脂肪或单块肌肉体积。四组几何及质量结果保存在[缩放探针](data/person_scaling_probe.json)：175→190 cm 使抽查的股骨长度、胫骨长度、股中间肌路径和膝力臂均约增加 8.57%；72→90 kg 使单侧模型质量从 36→45 kg，几何不变。这是参数输入进入计算模型的**研究性技术验证**，不是人体测量准确性验证。

相同的 60 kg 近似杠铃、固定踝上方作用线和半躯干质量方案下，四组 MocoInverse 都收敛。最深帧结果仅用于比较参数敏感性：

| 输入身高 / 体重 | 股中间肌激活 | 胫骨前肌激活 | 臀大肌激活 | 踝辅助力矩峰值 |
| --- | ---: | ---: | ---: | ---: |
| 175 cm / 72 kg | 0.43 | 0.43 | 0.06 | 0.028 Nm |
| 175 cm / 90 kg | 0.52 | 0.55 | 0.07 | 0.036 Nm |
| 190 cm / 72 kg | 0.43 | 0.44 | 0.06 | 0.026 Nm |
| 190 cm / 90 kg | 0.52 | 0.56 | 0.07 | 0.034 Nm |

本设置下体重输入比统一身高缩放更明显地改变优化结果，但这不是个体发力预测。模型只有一条腿，体重按左右对称分配；真实体段比例、体脂分布、肌肉最大力量、足地接触和杠铃轨迹都未标定。OpenSim 日志还反复报告比目鱼肌腱松弛长度问题及模型组装警告，需调查并验证后才可考虑把输出用于产品。**App 的发力视图继续不显示这些数值。**

### 比目鱼肌肌腱下界诊断

在 0 kg、半躯干与骨盆质量的同一研究配置中，重新输出比目鱼肌的肌腱长度和沿肌腱方向的肌纤维长度。`scripts/diagnose_squat_tendon.py` 从保存的 Moco 结果和原模型松弛长度生成[诊断 JSON](data/soleus_tendon_diagnostic.json)：113 个采样点中有 61 个的肌腱长度落在松弛长度的 1 μm 内，日志包含 21 行 buckling 提示。该模型的松弛长度为 0.276756 m，输出范围约 0.276756–0.276774 m。肌腱长期贴在下界与警告相符；不能据此判定求解出的肌肉分担具有生理真实性，模型组装警告也未被解决。

模型中的肌肉最大等长力按官方示例加倍，主动肌纤维力长度曲线加宽到 1.5，部分肌腱及被动力设置也按示例调整。这些选择用于让优化可求解，不能视为用户标定。训练记录尚未进入 Moco 参数，用户的身高、体重、体脂和围度也没有改变该动力学求解模型。现有姿态是手工设定的教学动作，尚未由真实动作学数据校验；只含右腿和简化躯干，没有真实杠铃或双侧足地接触模型，不能分析左右不对称、真实器械轨迹或卧推/实力举。

## 外部数据的第一轮筛查

从 [CEINMS-RT BackModel](https://github.com/CEINMS-RT/BackModel) 获取 5 kg 与 15 kg 蹲式搬箱试次的公开 IK/ID 文件，运行 `python scripts/analyze_external_backmodel.py`。两个试次各约 27 秒；L5/S1 屈伸力矩列的中位数分别为 64.03 和 88.41，最大值分别为 173.00 和 237.52，完整描述性结果见 [JSON](data/backmodel_box_lift_summary.json)。同一研究仓库里的较重试次显示更高的该列数值，提示可作负重趋势的关节层检查。尚未核对文件单位、搬起事件、速度和姿态匹配，也未与本项目求解结果对齐；动作是手持箱子的搬举，不是杠铃深蹲。**因此这些数值没有验证本项目的模型，更不能验证单块肌肉力。**

## 进入发力视图前的工作

- 建立和核查双侧完整人体，包括骨段质量、关节轴、肌肉附着点与包绕路径；使可见解剖资产与计算模型指向同一结构。
- 将杠铃质量、握持位置及人体质量一致地接入动力学；检查残余/辅助执行器大小、肌肉饱和及能量和力矩平衡。
- 用实验动作学、力台或已发表的关节力矩及肌电趋势作外部对照。激活预测不能被当作肌电实测，肌肉力也无法仅由肌电唯一确定。
- 对卧推和实力举分别建立上肢、躯干及器械模型；不能把深蹲单腿求解直接套用。
- 再建立身体参数缩放与训练记录标定，并输出参数敏感性或可信范围。根据验证结果决定哪些量能在手机离线预计算和插值。

## 复现当前轨迹

在项目根目录安装 npm 依赖及 OpenSim 4.6 Python 包后，先生成当前动画、质量模板与研究数据：

```powershell
npm run check:kinematics
npm run probe:squat-balance
python scripts/export_squat_mass_template.py
npm run build:squat-angles
python scripts/build_opensim_lookup.py
python scripts/export_squat_attachments.py
npm run check:opensim-lookup
python scripts/solve_viewer_squat.py --barbell-kg 0 --half-axial-mass
python scripts/solve_viewer_squat.py --barbell-kg 20 --viewer-bar-path --half-axial-mass
python scripts/solve_viewer_squat.py --barbell-kg 60 --viewer-bar-path --half-axial-mass
python scripts/solve_viewer_squat.py --barbell-kg 60 --viewer-bar-path --viewer-bar-offset-cm 6 --half-axial-mass
python scripts/solve_viewer_squat.py --barbell-kg 60 --viewer-bar-path --viewer-bar-offset-cm -6 --half-axial-mass
python scripts/solve_viewer_squat.py --barbell-kg 60 --disable-passive --viewer-bar-path --half-axial-mass
python scripts/analyze_viewer_squat.py --runs-root .cache/moco-viewer-squat/kinematics-7b85b4f29cb8
```

若输入轨迹改变，求解器会自动按其 SHA-256 创建新的 `kinematics-<哈希前12位>` 文件夹，分析时应改用新目录。历史表格的旧轨迹没有归档，以上命令只会重算当前轨迹。Moco 原始解和输出保存在忽略版本控制的 `.cache/moco-viewer-squat/`；提交的摘要带轨迹哈希。OpenSim 模型来源与许可见 `assets/opensim/NOTICE.txt`。实验使用的外力 API 见 [OpenSim PrescribedForce 文档](https://opensim-org.github.io/opensim-moco-site/docs/1.1.0/html_user/classOpenSim_1_1PrescribedForce.html)。
