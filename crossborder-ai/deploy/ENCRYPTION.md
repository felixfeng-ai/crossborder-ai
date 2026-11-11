# VeyaShip 加密与数据保留运维说明

## 目标

生产环境需要同时满足：

- 公网 HTTPS
- 后端到 PostgreSQL 的 TLS
- 数据库云盘和对象存储静态加密
- 备份文件加密
- 敏感字段使用独立数据加密密钥

## 1. PostgreSQL TLS

在 PostgreSQL 服务端开启 `ssl=on`，配置服务器证书、私钥和 CA，然后在生产 `.env` 设置：

```dotenv
DB_SSL_MODE=verify-full
DB_SSL_CA_PATH=/etc/veyaship/certs/postgres-ca.pem
```

如使用客户端证书，同时配置 `DB_SSL_CERT_PATH` 和 `DB_SSL_KEY_PATH`。

## 2. 独立数据加密密钥

生成高熵密钥并只写入服务器 `.env`：

```bash
openssl rand -base64 48
```

设置 `DATA_ENCRYPTION_KEY`。轮换时把旧密钥放入逗号分隔的 `DATA_ENCRYPTION_PREVIOUS_KEYS`，确认旧密文完成迁移后再移除。

## 3. 备份加密密钥

```bash
sudo install -d -m 700 /etc/veyaship
sudo sh -c 'umask 077; openssl rand -base64 48 > /etc/veyaship/backup.key'
sudo chmod 600 /etc/veyaship/backup.key
```

生产 `.env`：

```dotenv
BACKUP_ENCRYPTION_KEY_FILE=/etc/veyaship/backup.key
BACKUP_ENCRYPTION_REQUIRED=1
```

备份密钥必须进入企业密码库或 KMS 托管，不能只保存在单台服务器。

## 4. 云盘和对象存储静态加密

在阿里云或其他云控制台开启：

- ECS 系统盘与数据盘 KMS 加密
- OSS/S3 存储桶默认服务端加密
- 数据库备份存储加密

把控制台或 CLI 证据整理为：

```text
disk_encryption=KMS
object_storage_encryption=KMS
```

保存到 `/etc/veyaship/at-rest-encryption.txt`，并设置：

```dotenv
AT_REST_ENCRYPTION_EVIDENCE=/etc/veyaship/at-rest-encryption.txt
```

## 5. 核验

```bash
sudo /opt/veyaship/crossborder-ai/deploy/security-check.sh
```

全部通过后，Shopify Protected Customer Data 的存储相关问题才有真实依据选择 Yes。
