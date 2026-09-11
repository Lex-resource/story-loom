"""研究覆盖层。

本包只在研究运行(激活了 `ExperimentContext` 且版本/变体超出生产冻结点)时被加载。
生产代码**不得**在模块层导入本包——唯一入口是 `services/version_surface.py` 里的
函数内部导入,并且该导入被 `ImportError` 保护,因此部署时可以完全不包含本目录。

参见 `docs/research/novel-memory-continuity/PRODUCTION.md`:生产冻结在 A28/V43。
本包保存 V0–V42、V44–V66 以及 Ariadne A5/A6/A7 变体的行为,使这些实验仍可复现。
"""
