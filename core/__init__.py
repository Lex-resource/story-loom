"""中立词汇层:models / services / agents 共同向下引用的常量与枚举。

本包只允许 import 标准库 —— 不许引 agents/services/worker_support/models,
它是依赖图的叶子,存在意义就是让上层之间的循环失去必要性。
"""
