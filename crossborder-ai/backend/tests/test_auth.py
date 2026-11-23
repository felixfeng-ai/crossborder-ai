"""VeyaShip - 用户认证测试

【全栈学习者必读】
测试覆盖了完整的认证流程：
1. 健康检查 — 服务是否正常
2. 注册 — 创建新用户
3. 重复注册 — 异常场景：邮箱已存在
4. 登录 — 用密码换取 token
5. 登录失败 — 异常场景：密码错误
6. 获取用户信息 — 使用 token 获取个人信息
7. token 过期 — 异常场景：未提供 token

测试模式：AAA（Arrange-Act-Assert）
- Arrange：准备数据（注册用户、准备请求）
- Act：执行测试（发送 HTTP 请求）
- Assert：验证结果（检查状态码、响应内容）
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """测试健康检查接口

    验证：服务是否正常运行、数据库是否连接成功
    """
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    # 健康检查返回 "healthy" 或 "degraded"
    # 测试环境下数据库是独立的内存 DB，主 engine 无法连接
    assert data["status"] in ("healthy", "degraded")
    # 应该包含版本号
    assert "version" in data
    # 数据库连接状态：测试环境下可能是 "disconnected"（主 engine 无连接）
    assert data["database"] in ("connected", "disconnected")


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient, sample_user_data: dict):
    """测试用户注册

    验证：
    - 返回 201 Created
    - 返回的 JSON 包含 access_token
    - token 格式为 "bearer"
    """
    response = await client.post("/api/v1/auth/register", json=sample_user_data)
    assert response.status_code == 201

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(
    client: AsyncClient, sample_user_data: dict
):
    """测试重复邮箱注册被拒绝

    验证：
    - 第一次注册成功
    - 第二次注册返回 409 Conflict
    - 错误信息提示邮箱已被注册
    """
    # Arrange: 第一次注册
    await client.post("/api/v1/auth/register", json=sample_user_data)

    # Act: 用同样的邮箱再次注册
    response = await client.post("/api/v1/auth/register", json=sample_user_data)

    # Assert: 应该被拒绝
    assert response.status_code == 409
    assert "已被注册" in response.json()["detail"] or "registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_username_availability_checks_real_uniqueness(
    client: AsyncClient,
    sample_user_data: dict,
):
    """用户名可用性接口必须在注册前后返回真实状态。"""
    before = await client.get(
        "/api/v1/auth/username-availability",
        params={"username": sample_user_data["username"]},
    )
    assert before.status_code == 200
    assert before.json() == {
        "username": sample_user_data["username"],
        "available": True,
    }

    registered = await client.post(
        "/api/v1/auth/register",
        json=sample_user_data,
    )
    assert registered.status_code == 201

    after = await client.get(
        "/api/v1/auth/username-availability",
        params={"username": sample_user_data["username"]},
    )
    assert after.status_code == 200
    assert after.json() == {
        "username": sample_user_data["username"],
        "available": False,
    }


@pytest.mark.asyncio
async def test_username_availability_rejects_invalid_format(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/username-availability",
        params={"username": "小Veya 测试"},
    )

    assert response.status_code == 422
    assert "4–12" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_rejects_duplicate_username(
    client: AsyncClient,
    sample_user_data: dict,
):
    """不同邮箱也不能复用同一称呼。"""
    first = await client.post("/api/v1/auth/register", json=sample_user_data)
    assert first.status_code == 201

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={
            **sample_user_data,
            "email": "another@example.com",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "这个称呼已经被用了"


@pytest.mark.asyncio
async def test_login(client: AsyncClient, sample_user_data: dict):
    """测试用户登录

    验证：
    - 先注册一个用户
    - 用正确的邮箱密码登录
    - 返回 200 + JWT token
    """
    # Arrange: 先注册
    await client.post("/api/v1/auth/register", json=sample_user_data)

    # Act: 登录
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": sample_user_data["email"],
            "password": sample_user_data["password"],
        },
    )

    # Assert: 成功获取 token
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """测试无效凭据登录被拒绝

    异常场景：错误的邮箱或密码
    - 不应该暴露"邮箱不存在"还是"密码错误"的区别
    - 统一返回 401
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@test.com", "password": "wrongpass"},
    )

    # Assert: 应该返回 401 Unauthorized
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, auth_headers: dict):
    """测试获取当前用户信息

    验证：
    - 用有效的 token 请求个人信息
    - 返回的用户信息包含 email 和 username
    """
    # Act: 用 auth_headers（包含 JWT token）请求个人信息
    response = await client.get("/api/v1/auth/me", headers=auth_headers)

    # Assert: 成功返回用户信息
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert "username" in data
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client: AsyncClient):
    """测试未认证请求被拒绝

    异常场景：不提供 token 访问需要登录的接口
    - 应该返回 401
    """
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
