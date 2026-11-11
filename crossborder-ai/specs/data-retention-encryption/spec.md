# 数据保留与加密改造

## 目标

把当前“只有政策说明、没有真实执行”的数据保留能力改为可调度、可审计、可演练的清理任务；补齐独立数据加密密钥、PostgreSQL TLS 配置和加密备份，并让安全措施可以被脚本核验。

## 能力点

### CAP-01 可执行的数据保留

#### Requirement

系统按配置的保留天数清理已经结束且不再需要的临时记录：

- 图片生成任务
- Agent 任务
- 内容生成记录
- 历史巡检记录

运行中或等待中的任务不得删除。商品、Listing、备案素材和用户主动保留的素材库不在此任务中自动删除。

#### Scenario

- Given 图片生成任务、Agent 任务和内容生成记录超过保留期且已结束
- When 数据保留任务执行
- Then 过期记录被删除
- And 新记录和非终态记录保留

### CAP-02 清理审计与 dry-run

#### Requirement

每次清理写入 `data_retention_runs`，记录截止时间、是否演练、各类删除数量、状态和错误。dry-run 只统计不删除。

#### Scenario

- Given 存在可清理数据
- When 执行 dry-run
- Then 返回预计删除数量
- And 数据仍然存在
- And 审计记录标记 `dry_run=true`

### CAP-03 独立数据加密密钥

#### Requirement

敏感字段加密优先使用 `DATA_ENCRYPTION_KEY`，不再直接从 JWT 签名密钥派生。支持 `DATA_ENCRYPTION_PREVIOUS_KEYS` 解密历史密文，并保留现有 JWT 密钥回退兼容。

#### Scenario

- Given 旧密文由 JWT 密钥生成
- When 配置新的数据加密密钥和旧密钥列表
- Then 旧密文仍可解密
- And 新密文使用新密钥加密

### CAP-04 数据库传输加密配置

#### Requirement

PostgreSQL 连接支持 `disable`、`require`、`verify-ca`、`verify-full` 四种 TLS 模式，并可配置 CA 与客户端证书。

#### Scenario

- Given 生产配置 `DB_SSL_MODE=verify-full`
- When 创建数据库引擎
- Then asyncpg 使用校验证书的 SSLContext

### CAP-05 备份加密与安全核验

#### Requirement

备份脚本支持 OpenSSL AES-256 加密，密钥只从权限受控文件读取。安全核验脚本检查数据库 TLS、数据加密密钥、备份加密密钥和云盘/对象存储静态加密证据。

#### Scenario

- Given 生产环境完成 TLS、密钥和云存储加密
- When 执行安全核验脚本
- Then 所有检查通过并输出可留档结果

- Given 缺少任一关键配置
- When 执行安全核验脚本
- Then 脚本非零退出并指出缺失项

## 不在代码内自动完成

- 阿里云 ECS 云盘 KMS 加密开关
- OSS/S3 服务端加密开关

这两项需要云控制台确认，并以证据文件交给核验脚本。

## 验收

- 新增后端测试先失败后通过
- 后端全量测试通过
- Alembic head 包含数据保留审计表
- 加密备份脚本语法检查通过
- 安全核验脚本能正确区分通过和缺失配置
