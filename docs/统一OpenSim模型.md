# 统一 OpenSim 模型：当前实现与边界

> 本文记录上一版“只有路径线”的实现。精细肌肉表面、脚跟接触和更新后的三个动作请看[网页版精细肌肉与动作](网页版精细肌肉与动作.md)。

## 现行网页和 Android 包

首页现在是单模型视图。`src/unified.ts` 在同一场景中显示 80 个 OpenSim 体段的网格与 520 条肌肉肌腱路径；点击“静止”、深蹲、卧推、实力举时，仅更换同一个模型的预先计算姿势帧。体段变换、每条肌肉路径及肌肉肌腱长度都由 OpenSim 4.6 对 `cyclistFullBodyMuscle.osim` 求得，保存在 `public/data/unified_opensim_reference.json`。原先把静态 Z-Anatomy 与动态自制骨架/不同 OpenSim 模型切换显示的页面没有打入现行包。`scripts/copy-unified-public.mjs` 是发行资源白名单。

查看方式：`npm install`、`npm run build`、`npm run preview`，浏览器打开首页。`npm run check:unified-ui` 在 Chromium 中打开正式构建，检查模型载入、来源计数、三个动作的长度读数和页面错误。Android 调试包用 `powershell -ExecutionPolicy Bypass -File scripts/build-android-debug.ps1` 构建；需要本机 Android SDK 36、Build Tools 35 和 JDK 21。

## 模型和几何来源

- [主模型仓库](https://github.com/ross-wilkinson/opensim-model-fullBodyMuscleActuated)，固定提交 `3cfbe329a8ef9412494980419cb7177c41183a53`，MIT 许可。该模型面向站姿骑行，组合了 Rajagopal/Lai 下肢、Allaire 躯干和 Saul/McFarland 上肢。作者明确指出椎骨显示不准确、上身驱动还需简化。
- [Pose2Sim OpenSim 几何库](https://github.com/perfanalytics/pose2sim/tree/68304b47195dac80bc341cdfd9669140609358c4/Pose2Sim/OpenSim_Setup/Geometry)，固定提交 `68304b47195dac80bc341cdfd9669140609358c4`，BSD-3-Clause 许可。仅为主模型**已经引用**、但主仓库缺失的同名网格补文件；两处几何目录有 64 个同名且逐字节相同的文件。两份完整许可文本随包存于 `public/models/NOTICE-unified-opensim.txt`。
- `scripts/export_unified_opensim_meshes.py` 输出 `public/models/unified_opensim_skeleton.glb` 和 `docs/data/unified_opensim_geometry.json`。83 个引用网格进入画面；37 个引用网格在两处来源均缺失；另 12 个胸椎网格虽然可用，但主模型把它们放在头骨上方，因此排除。未画自制骨骼补片，也未把另一模型的关节坐标并入。

复现导出：在 `.cache/model-candidates/opensim-model-fullBodyMuscleActuated` 克隆主仓库，在 `.cache/model-candidates/pose2sim` 克隆 Pose2Sim；执行 `python scripts/export_unified_opensim_meshes.py` 与 `.cache/opensim-venv/Scripts/python.exe scripts/export_unified_opensim.py --samples 101`。需要 OpenSim 4.6 Python 环境、NumPy、Trimesh。导出数据本身已提交，网页和 Android 构建不需要安装 OpenSim。几何审计逐文件记录来源与缺失情况。

## 颜色和动作的正确解释

颜色使用同一肌肉的当前**整条肌肉肌腱长度**除以静止长度，变化超过 ±2.5% 才改变颜色：红色变长、蓝色变短。主动收缩、被动拉伸、肌腱伸长、肌肉纤维长度与神经激活并不相同；单靠该比值无法计算个人发力点。当前没有求解肌肉力、关节反力或外力。

OpenSim 的这份 `.osim` 文件给出肌肉路径、包绕体和动力学参数，没有精细的肌腹表面网格。因此现版只能忠实画路径线，不能称为真实人体肌肉外形。未来若要达到所期望的精细视觉效果，需要取得许可合适的解剖表面资源，把每块表面**一次性精确配准到同一个 OpenSim 模型的骨段坐标**，并在静止和动作中始终沿用该配准；还要验证形变、附着点、穿模和解剖尺度。

三个动作的关节曲线由 `scripts/export_unified_opensim.py` 明确写出，是演示姿态，不是录像逆运动学或经实测验证的动作。卧推没有长凳、杠铃和接触约束；深蹲没有足底接触或重心平衡求解；骑行模型的肩关节升举上限约 2.01 rad，过顶实力举无法完整重现。因此现阶段只供检查“同一模型的姿势和路径会随关节角变化”，**不可作为训练动作规范或发力指导**。

## 下一阶段

1. 寻找许可明确、骨网格齐全、肩关节可覆盖过顶动作且具有上肢与下肢肌肉的单一 OpenSim 模型；核验每个网格与骨段配准，再决定是否替换当前骑行模型，并为同一模型配准精细肌肉表面。
2. 用该模型的关节约束与逆运动学实现肢体拖动，拖动后实时或低延迟重新计算骨段和包绕肌肉路径；保留同一模型来源。
3. 用实测卧推、深蹲、实力举的姿态和外力数据校准预设；随后区分肌肉肌腱长度、激活、力和关节负荷，并逐项验证。
4. 验收 Android 真机加载时间、内存和离线启动，再引入少量身体参数缩放及训练记录估计。
