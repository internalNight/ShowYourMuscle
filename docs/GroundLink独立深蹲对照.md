# GroundLink 独立实验室深蹲对照

[GroundLink 原始数据](https://csr.bu.edu/groundlink/)由 Han 等人公开，七名参与者有同步的全身光学标记、双脚地面反力与压力中心；[论文](https://arxiv.org/html/2310.03930)列出每人身高和体重。这里仅分析**自重深蹲**，以另一个实验室检查手机原型的整体竖直支撑力示意能否迁移。它不含杠铃负重或肌电，不用于估算个人肌肉力。

## 数据和复算

- 原始力板 `.npy` 包含 PyTorch 对象序列化。`scripts/groundlink_force_format.py` 只用 `pickletools` 定位两个浮点存储区，校验结构后解码，不执行外部 pickle。
- 每人的 C3D 压缩包约数百 MB。`scripts/download_groundlink_squat_c3d.py` 通过 HTTP Range 只下载各人的三份深蹲 C3D，并校验解压长度与 CRC。原始文件只放在 `.cache/groundlink/`，不进入 App。
- `scripts/audit_groundlink_squat_force.py` 按公开体重把两脚竖直反力换成体重倍数。原始数值乘以 1000 后，七人、21 段试验的逐人中位支撑力比值再取中位为 **1.019**，与静态体重基线量级相符；据此暂按 kN 解释原始量级，源文件未附字段单位表。双脚力加权压力中心在实验室 X/Y 轴的逐人 5%–95% 位移跨度中位分别约 **6.33／4.09 cm**。坐标轴尚未配准到足部前后，不能把这些跨度直接当成关节力臂。摘要见[力板初筛](data/groundlink_squat_force_audit.json)。
- `scripts/export_groundlink_squat_template.mjs` 直接调用 App 的 `squatVerticalSupportScenario`，用论文列出的七人身高体重，在 0 kg 负重、固定 2.8 秒下导出 99 个相位点；未在这批数据上拟合模板。
- `scripts/benchmark_groundlink_squat_template.py` 读取 21 份 C3D 的骨盆骶骨标记。每段均检出三个明显下降极小值；在骨盆回到站姿高度的 90% 处切分动作，得到 **63 次**。然后将力板信号按实验起止点映射到 99 个相位点。实验姿态只用于评估时对齐，不是手机输入。第七人的处理后力板文件比 C3D 少 456–597 帧；三段原始 C3D 模拟量力板通道与处理力板的时间相关峰值均在零偏移，因此仅剪去尾部。逐人及逐次结果见[独立对照](data/groundlink_squat_template_benchmark.json)。

在项目根目录依次运行 `python scripts/download_groundlink_force_zips.py`、`python scripts/download_groundlink_squat_c3d.py`、`node scripts/export_groundlink_squat_template.mjs`、`python scripts/audit_groundlink_squat_force.py`，最后用安装了 `ezc3d==1.7.2` 的研究 Python 环境执行 `python scripts/benchmark_groundlink_squat_template.py`。分析脚本使用的原始研究资料不会加入生产构建。

## 结果

误差为逐次 99 个相位点的平均绝对误差，单位是该受试者体重；先取每人重复动作的中位数，再跨人取中位数。

| 方案 | 七人误差中位数 | 优于静态基线的人数 |
| --- | ---: | ---: |
| 恒定体重 `1.0 × BW` | 0.1106 BW | — |
| App 固定 2.8 秒示意轨迹 | 0.0926 BW | 7／7 |
| 使用实验切分出的时长缩放加速度 | 0.1066 BW | 2／7 |

固定轨迹相对恒定体重的**逐人配对改善中位数**为 0.0169 BW。按人重采样的 95% bootstrap 区间是 0.0142–0.0192 BW；只有七人，这不是泛人群的性能保证。另一项 Georgia Tech 12 人、39 次自重深蹲对照中，固定轨迹的误差仅从静态 0.1143 降到 0.1117 BW。两个实验都需要实验姿态划定相位，不能直接外推到只填写几个参数的手机用户。

切分门槛还改变了对“时长输入”的判断：以骨盆站姿高度的 80%／90%／95% 切分，同一 63 次动作中固定模板均比静态基线好（逐人配对中位改善分别 0.0072／0.0169／0.0244 BW）；按切分时长放大加速度的配对改善却分别是 **−0.0488／−0.0062／+0.0180 BW**。因此不能仅凭一项动作时长数字就宣称动力学精度提升。80% 和 95% 的诊断输出保存在本地 `.cache/groundlink/benchmark_top80.json` 与 `benchmark_top95.json`。

## 结论及下一道验收

独立实验室的结果支持保留**明确标为示意**的整体支撑力曲线，也说明它有机会优于恒定体重线。当前评估借用了实验动作边界；App 未测实际运动，且两个实验都是自重深蹲。要输出用户负重训练时的个人发力分布，还需独立验证实际杠铃质量与轨迹、双脚反力及支撑点、关节净力矩，再核查肌肉容量与独立肌电。骨盆高度不等于全身质心，压力中心也不等于肌肉作用线。
