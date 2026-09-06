# 德育助手 · 教师自部署版

项目地址：https://github.com/ypenglv8-a11y/deyu-selfhost

设计：**吕钰鹏老师**。版本：0.1.0-rc1（发布候选）。

帮助班主任可靠记录事实、准备支持行动、跟踪真实反馈。五项核心：阿德勒心理学、非暴力沟通、自我决定理论、场域视角、WOOP；ABC行为观察为补充方法。

**源码可用，教师与学校可自行部署；商业转售和代运营收费需另行授权。不是OSI标准开源许可。** 详见[许可](LICENSE.md)。不附带真实学生档案、私人案例库或作者个人研究资料。

## 本版定位

单个教师或学校指定的可信操作人员，在自有电脑/服务器通过命令行使用。不是多用户网站，不含注册、租户隔离、手机网页、已接通的钉钉/企业微信机器人。不要把本CLI直接包装成无鉴权公网接口。

相较原阿里云快照，本版重新收敛了发布范围：保留核心分析、周追踪、报告与案例检索代码；新增可靠记录、查询、回访和备份入口。旧平台适配器、个人部署配置、私人案例及自动外发调度未纳入发布候选。各实例自行保管数据，不汇集到作者服务器。

## 五分钟离线试用

需要Python 3.11或更新版本。下面全部是虚构数据，离线记录与演示无需API密钥，也无需安装第三方依赖。

```bash
python3 -m src.cli init-db
python3 -m src.cli student-add --id DEMO-001 --name 虚构学生甲 --class-name 示例班
python3 -m src.cli record --student DEMO-001 --type 作业 --text "虚构演示：今天开始作业时遇到困难，原因待核实" --request-id demo-message-001
python3 -m src.cli find --student DEMO-001 --query 作业
```

成功返回`verified: true`、事件编号、回读事实及内容哈希。相同请求重试复用同一事件；相同请求标识配不同事实会失败。保存事实完全独立于AI分析。

将以下`EVT编号`替换为刚才返回的真实编号：

```bash
python3 -m src.cli analyze --event EVT编号
python3 -m src.cli report --student DEMO-001 --period 2026-09
```

默认**离线固定示例，不是该学生的真实判断**；模拟分析/报告不写入正式库。报告月份必须有已记录事件，否则拒绝生成空泛结论。需要另选月份时改为事件所在月份。

## 回访闭环

明确一个问题、一个可观察变化和一个下一步决定。`YYYY-MM-DD`替换为今天或未来的实际日期：

```bash
python3 -m src.cli followup --event EVT编号 --due YYYY-MM-DD --plan "核实起步提示是否实际提供，听取学生体验，再决定是否调整任务"
python3 -m src.cli due
python3 -m src.cli complete --id FU编号 --feedback "填写真实学生反馈，未知就保持未完成" --review "填写教师本次真实复盘"
```

没有反馈和教师复盘不能完成。已完成内容不能覆盖；真实修正需另建关联回访。完成回访不自动把事件改成已改善。当前版本未提供延期/取消专用状态入口，无法完成时保留待办，不编造反馈消除清单。

## 使用真实模型

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

在本机进程环境中安全设置`DEEPSEEK_API_KEY`，不要写入源码或提交Git。可选`DEEPSEEK_MODEL`、`DEEPSEEK_BASE_URL`。CLI不自动加载`.env`。

```bash
.venv/bin/python -m src.cli analyze --event EVT编号 --real
.venv/bin/python -m src.cli weekly --real
.venv/bin/python -m src.cli report --student DEMO-001 --period 2026-09 --real
```

`--real`明确触发网络请求：相关学生档案、事件与回访资料会发往配置的模型服务。部署者需先确定相应处理依据、告知/授权及服务商数据政策，只提供必要材料。AI分析/报告是待教师核实的派生内容，不是诊断、事实或可直接外发的结论。实际网络服务本轮未联调。

## Docker（自有服务器，包括阿里云）

```bash
docker compose -f deploy/compose.yml build
docker compose -f deploy/compose.yml run --rm deyu init-db
docker compose -f deploy/compose.yml run --rm deyu student-add --id DEMO-001 --name 虚构学生甲
docker compose -f deploy/compose.yml run --rm deyu find --student DEMO-001
```

数据保存在命名卷`deyu-data`，不开放端口，不包含任何自动外发任务。不要用`down -v`删除持久化卷。真实模型参数通过宿主进程环境传入；`.env`只用本地私有文件管理且不可进入仓库。本轮验证了Python入口，Docker构建与阿里云部署仍需在目标环境验证。

## 备份与测试

```bash
python3 -m src.cli backup --to /安全目录/deyu-backup.db
python3 -m unittest discover -s tests -v
```

备份目标必须不存在；SQLite在线备份API完成后执行完整性检查。恢复时先停用写入，保留现有库，使用`--db /安全目录/deyu-backup.db`运行`find`验证后再决定切换。不要覆盖唯一原库。备份同样包含敏感学生数据，需部署者保护。

[设计与边界](docs/DESIGN.md) · [发布检查](docs/RELEASE.md) · [安全说明](SECURITY.md)
