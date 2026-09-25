# Second Skin 深蹲实验数据核查

更新：2026-09-24。本页记录一个可用来校验深蹲动力学的**外部数据候选**，目前没有把任何实验关节力矩或肌肉力放进 App。

## 来源与范围

Georgia Tech EPIC Lab 的 [The Second Skin 数据集](https://www.epic.gatech.edu/the-second-skin-a-wearable-sensor-suite-that-enables-real-time-human-biomechanics-tracking-through-deep-learning/)包含同步的运动捕捉、力板、腿部肌电及 OpenSim 逆运动学、逆动力学输出。原始文件位于[学校官方仓库](https://repository.gatech.edu/entities/publication/c7a857c8-79d8-4119-8ce0-be568d942f49)，许可为 CC BY 4.0。官方压缩包约 12.5 GB；`scripts/inspect_second_skin.py` 利用服务器的 HTTP 字节范围功能，仅提取选定条目到被 Git 忽略的 `.cache/second-skin/`。保留了官方 README、文件名、受试者代码和来源 UUID，以便复核；数据不进入手机离线包。

这里选的是 `pseudo_static_sym_squat_unweighted_01` 与 `pseudo_static_sym_squat_vest_25lb_01`。官方 README 将两者定义为约 30 秒的对称半蹲静态保持，后者穿约 25 lb 负重背心。它们**不是**杠铃深蹲的下蹲—起身动作。导出的同步 CSV 里有右髋、膝、踝角度及 OpenSim gait2392 逆动力学力矩；力矩以 N·m/kg 报告，右膝关节反力以体重倍数报告。反力是模型计算值，不是直接测得的单块肌肉力量。

## 初步筛选

`scripts/analyze_second_skin_squat.py` 对各试次 5–25 秒的有效样本取中位数，保存 [AB01](data/second_skin_ab01_static_squat_compare.json) 和 [AB02](data/second_skin_ab02_static_squat_compare.json) 的可复核汇总：

| 受试者 | 右膝力矩：无负重 → 背心，N·m/kg | 右膝反力：无负重 → 背心，体重倍数 | 膝角中位数差异 |
| --- | ---: | ---: | ---: |
| AB01 | 0.600 → 0.841 | 2.698 → 3.591 | 约 13.7° |
| AB02 | 0.582 → 0.490 | 2.265 → 2.299 | 约 6.4° |

两位受试者的无负重与背心试次，在 5–25 秒内的**髋、膝、踝角度范围均互不重叠**。AB01 的膝力矩随背心增加，AB02 则减少；这不能被解释为负重导致的统一发力变化，因为深度与肢体姿势也变了。此数据可以用于建立每种姿势的外部关节力矩参考，但不能把两次中位数之差直接拿来验收个人负重模型，更不能据此给肌肉标红。

下一步需要在同一受试者、相近角度和外力作用线下匹配姿态，或使用同步力板与运动捕捉重新计算关节力矩，随后比较模型的力矩残余和独立肌电趋势。若要验证**动态杠铃深蹲**，还需对应动作的杠铃质量、轨迹与手部作用力；背心静态半蹲只能作为较窄的力学子问题。
