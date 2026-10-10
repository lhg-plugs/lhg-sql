# 灵感来源与致谢（Attribution）

本插件的**方法论灵感**来自以下优秀的开源项目与公开资料，**所有实现代码、检测规则与文案均为原创**，未复制任何第三方的原文案。

| 项目 | 作者 / 组织 | 许可 | 链接 | 借鉴了什么思路 |
|---|---|---|---|---|
| sqlfluff | sqlfluff 团队 | Apache-2.0 | https://github.com/sqlfluff/sqlfluff | "SQL 静态规则检查"的思想；本插件审计脚本的规则引擎模式受其启发，**规则条目全部自研** |
| PostgreSQL / MySQL / SQLite 官方文档 | 各官方 | 开放文档 | https://www.postgresql.org/docs/ 等 | 方言函数差异的事实依据；本插件 `lhg-sql-dialect` 的对照表以官方文档为准自行整理 |
| lhg-plugs 组织模板 | 刘洪光 | MIT | https://github.com/lhg-plugs/lhg-fullstack | 插件目录结构、GEO 规范、"规则注册表 + JSON/text 双输出"审计脚本模式 |

## 声明

1. **借鉴思路，实现与文案均为原创**：以上项目的具体文案、规则原文、代码实现均未被复制。本插件的 skill 方法论文案、审计规则、命令流程均为独立撰写。
2. **许可合规**：上述项目均为 Apache-2.0 / MIT 许可，允许在保留声明的前提下进行思路借鉴与二次创作。本文件即为保留声明的一部分。
3. **商标与归属**：各项目名称与作者署名归其各自所有者所有。

## 本插件自身的许可

本插件原创部分采用 MIT 许可（见 `LICENSE` 文件），版权所有：刘洪光（https://github.com/lhg-skills）。
