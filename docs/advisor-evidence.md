# RDS Advisor 文献核验与采纳边界

核验日期：2026-09-30（Asia/Shanghai）。范围：训练诊断、低保真筛选与预算建议、科研证据链。RDS的目标是辅助人类科研。本文没有运行GPU实验、训练曲线预测器或接入外部服务，也没有测得Advisor的科研成功率。

## 采纳决定

本次采用“有来源的候选解释 → 复用已有证据 → 必要时最小判别探针 → 保留适用边界”的路线。论文支持某种现象或干预，不足以证明Advisor能从压缩遥测准确诊断该现象。规则库中的 `evidence_status=SOURCE_SUPPORTED_ENGINEERING_HYPOTHESIS` 表示原文有支持、具体触发与探针是工程推断，仍需目标任务证据。

先删去普适loss/梯度阈值、固定warmup比例、norm衰减必然坍塌、固定FFT分支和自动“健康收敛”默认值。预算建议优先读取已有完整日志、同seed配对、兼容checkpoint和可比控制组；只有已有seed不稳定证据且会改变决策时，才考虑多seed。此成本选择来自用户要求，不是论文保证。

## 主要来源与原文能够支持的结论

核验了以下10个学术来源的书目信息与相关章节/摘要。没有复现其基准结果。旧文用于检查原有归因；最新进展优先用于审查迁移边界。

| 来源、版本与定位 | 原文发现 | 对Advisor的边界 |
|---|---|---|
| Ian Goodfellow、Yoshua Bengio、Aaron Courville，*Deep Learning*，MIT Press，2016，[Chapter 11](https://www.deeplearningbook.org/contents/guidelines.html)，§11.3、11.4.1、11.5 | 有效容量受表达、优化与正则化共同影响，应先建立指标、baseline与诊断测量。 | 不支持用两个loss标量或固定比例确诊容量不足；原书也不能作为“欠拟合时一律禁止早停”的依据。 |
| Razvan Pascanu、Tomas Mikolov、Yoshua Bengio，*On the difficulty of training recurrent neural networks*，ICML 2013，PMLR 28(3):1310–1318，[论文](https://proceedings.mlr.press/v28/pascanu13.pdf)，§3.2、Algorithm 1 | 在RNN中研究梯度爆炸，提出范数截断；阈值是超参数，可参考已有norm统计。 | 不支持 `norm > 50` 通用确诊或 `max_norm=1` 通用修复；截断后达标只是执行检查。 |
| Dayal Singh Kalra、Maissam Barkeshli，*Why Warmup the Learning Rate? Underlying Mechanisms and Improvements*，NeurIPS 2024，[正式页面](https://papers.nips.cc/paper_files/paper/2024/hash/ca98452d4e9ecbc18c40da2aa0da8b98-Abstract-Conference.html)，摘要及初始化/参数化讨论 | SGD与Adam实验将主要收益联系到承受更大目标LR；初始化和参数化影响warmup必要性，部分设置可减弱或去除warmup。 | 不支持统一前500步、variance=1.5或总步数5%–10%；早期震荡只有候选解释。 |
| Ilya Loshchilov、Frank Hutter，*Decoupled Weight Decay Regularization*，ICLR 2019，[arXiv v3，2019-01-04](https://arxiv.org/html/1711.05101v3)，摘要、§1–3 | Adam下L2正则与decoupled weight decay不等价；原图像分类实验支持AdamW的经验收益。 | 不能从论文推出所有1D参数应免衰减，也不能据此认定norm/bias衰减导致表示坍塌。 |
| Tong He、Zhi Zhang、Hang Zhang、Zhongyue Zhang、Junyuan Xie、Mu Li，*Bag of Tricks for Image Classification with Convolutional Neural Networks*，CVPR 2019，[arXiv v2，2018-12-05](https://arxiv.org/html/1812.01187v2)，§3.1、Table 4 | CNN/BN经验方案将bias与BN的gamma/beta排除衰减。 | Table 4为顺序堆叠消融，免衰减步骤的top-1也有下降，不能声称普适增益；LayerNorm与任意1D向量属于额外迁移假设。 |
| HyunJae Lee、Gihyeon Lee、Junhwan Kim、Sungjun Cho、Dohyun Kim、Donggeun Yoo，*Improving Multi-fidelity Optimization with a Recurring Learning Rate for Hyperparameter Tuning*，WACV 2023，[arXiv v1，2022-09-26](https://arxiv.org/html/2209.12499v1)，§1、3、5.1 | CNN中的优质配置可能慢启动；低保真与LR schedule相互作用，MORL研究压缩周期schedule的改善。 | 提前排名不能当最终排名；直接采用MORL还改变了训练过程，不能把收益只归因于预算分配。 |
| Steven Adriaensen、Herilalaina Rakotoarison、Samuel Müller、Frank Hutter，*Efficient Bayesian Learning Curve Extrapolation using Prior-Data Fitted Networks*，NeurIPS 2023，[arXiv v1，2023-10-31](https://arxiv.org/html/2310.20447v1)，§4.3、5、Appendix C.3 | LC-PFN用先验训练预测分布，研究基于外推的早停；同时展示分布失配与失败。 | 论文的NAS-Bench-201全部3任务上，测试的早停准则失败；作者联系到曲线拐点和先验失配。不能把该论文的加速迁移成RDS保证。 |
| Mengyang Li、Pinlong Zhao，*Difficulty-Aware Learning Curve Extrapolation*，AAAI 2026，40(27):23021–23029，[正式页面，2026-03-14](https://ojs.aaai.org/index.php/AAAI/article/view/39467)，摘要与Methodology | DA-LCE研究任务难度条件化和diffusion生成先验，针对不同任务动态与先验的失配。 | 是本次检索到的较新相关进展；本地没有复现，难度proxy不可直接升格为普适诊断。离线训练新预测器不属于本次采纳范围。 |
| Ziming Luo、Atoosa Kasirzadeh、Nihar B. Shah，*The More You Automate, the Less You See: Hidden Pitfalls of AI Scientist Systems*，[arXiv v2，2025-12-20](https://arxiv.org/html/2509.08713v2)，NeurIPS 2025 AI4Science Spotlight，§4–7 | 对两个自动科研系统的受控评估发现评估口径与事后选择等风险，日志/代码有助于审计。 | 属于workshop/preprint证据，非所有系统的失败率估计；原文未发现直接偷看测试数据或蓄意metric挑选，也须保留这些反证。 |
| Chris Lu、Cong Lu、Robert Tjarko Lange等，*Towards end-to-end automation of AI research*，Nature 651:914–919，[正式版本，2026-03-25](https://www.nature.com/articles/s41586-026-10265-5)，Human evaluation results、Limitations | 有生成论文达到workshop评审门槛的实例，同时描述人工筛选与实现、方法、引用等局限。 | 是对“自动科研完全不可行”的反证；workshop实例、同行评议或自动reviewer通过均不保证目标任务有效。RDS因此保留人类目标与实验证据判断。 |

实现定位参考：[PyTorch autograd官方文档](https://docs.pytorch.org/docs/main/autograd.html#debugging-and-anomaly-detection)（2026-09-30核验，main文档）说明anomaly detection定位失败backward对应的forward，并检查backward NaN；有调试开销，不能当成全面Inf检测器或永久运行默认值。

## 可落地规则：触发、替代解释与最小判别

下表都是工程推断，完整结构化规则见 [scientific_tuning_principles.json](../references/scientific_tuning_principles.json)。`trigger_condition` 是范围描述，不是无需验证的自动执行表达式。探针只在已有授权预算内、其结果会改变下一步决策时执行。

| 规则 | 触发条件 | 主要替代解释 | 最小判别与适用边界 |
|---|---|---|---|
| 拟合状态保留不确定性 | 同口径训练表现未达目标，或开发表现持续恶化；依据上表Goodfellow | 容量、优化、数据质量、train/eval模式差异 | 先查已有轨迹与baseline；再考虑同seed小样本拟合或单因素LR探针。单点loss返回证据不足。 |
| 平台先辨因 | 已有时间序列显示进展停滞；依据Goodfellow | 已收敛、LR过大/过小、梯度断开、标签噪声、schedule阶段 | 优先查梯度是否存在、实际更新/LR与数据；增减LR只列成对候选。没有“STAGNANT就提升2–3倍”。 |
| 非有限值先定位 | 首次观察NaN/Inf；依据官方PyTorch接口说明 | 非法数值域、数据污染、低精度、更新不稳 | 保存失败batch与checkpoint，同seed重放，显式检查输入/输出/loss/梯度/参数；eps或clamp改变目标语义，需原因支持。 |
| 截断是候选干预 | 同尺度norm尖峰与不稳定更新相伴；依据Pascanu | AMP未unscale、batch/reduction改变、异常样本 | 用已有norm分布与实际update测量选择候选threshold，记录clip命中率；同seed比较稳定性与开发进展。 |
| Warmup按条件审查 | 早期不稳定与目标LR/更新量相关；依据Kalra与Barkeshli | 数据或算子错误、scheduler实现问题 | 复用日志；只比较较低起始LR或短warmup中的一个候选。不是固定比例，也不是必做实验。 |
| Decoupling和参数组分别检验 | 已核对optimizer语义或可疑norm/bias分组；依据AdamW与He | LR/衰减量失配、其它技巧交互、正常scale变化 | 分别做decoupling或norm/bias免衰减同seed配对，按角色检查参数；不把多个改动捆成已确证修复。 |
| 低保真先回放 | 短训练指标将决定淘汰；依据MORL | 曲线交叉、慢启动、schedule失配、噪声 | 用已有完整日志衡量最终优质候选保留率与成本；不足则延后筛选或保留候选。预算不可从毫秒固定换算训练步。 |
| 外推先校准 | 部分轨迹将用于后期预测/早停；依据LC-PFN与DA-LCE | 先验/任务失配、拐点未出现 | 遮蔽已有完整轨迹，预留未用于选规则的曲线检验误杀与区间覆盖；本次不训练/导入外推模型，不编造概率。 |
| 证据链可审查 | 自动摘要/报告将支持规则或科研结论；依据Luo与Lu | 真增益、数据/metric变化、事后选择、实现不对应主张 | 原文定位与完整运行日志支持复核；未经审查摘录保持摘录身份。hash/执行收据证明一致性，不能证明科学因果。 |

固定FFT方向没有从“连续两次停滞”得到的证据。边界参考是Matthew Tancik等的 [Fourier Features Let Networks Learn High Frequency Functions in Low Dimensional Domains，NeurIPS 2020](https://proceedings.nips.cc/paper_files/paper/2020/hash/55053683268957697aa39fba6f231c68-Abstract.html)：其对象是低维坐标输入MLP的高频函数拟合。只有任务符合该范围、残差/频率测量支持此瓶颈时，频率表征才是候选；FFT残差滤波也不等同于原论文的Fourier feature mapping。领域未知时应从当前失败证据与已有候选选择方向。

## 反证、覆盖限制与剩余验证

最直接反证是LC-PFN的先验失配失败、He的免衰减非单调收益，以及Luo没有发现部分预设失当行为。它们保留在结论中，避免只检索支持当前建议的文字。Nature 2026提供受限自动科研成功实例，因此本次采用可审查辅助，而不将自动化一概排除。

本次检索并非穷尽综述。来源覆盖主要是监督学习、CNN/RNN和训练曲线基准；迁移到强化学习、在线数据、科学算子或新loss尚未验证。未系统比较所有2025–2026的曲线预测器，也未复核每个来源的全部实验。DA-LCE只核对了书目、方法主张与相关原文，不认定其优于所有后来方法。

采纳后的必要验证是Advisor能正确表示缺证据、列出替代解释、保留文献定位，并不自动升级未审查摘录；这些可用离线单元/回归测试检查。科研收益、诊断准确率和省算力幅度仍未知。未来有真实完整日志且需要做预算决策时，才开展会改变决策的有限回放。Lean或其它形式化工具只适用于相应数学子任务，不是RDS整体科研效果的验收标准。
