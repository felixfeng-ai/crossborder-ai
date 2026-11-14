# 首页与前端加载性能优化

## 目标

降低首次访问的初始 JavaScript、缩短白屏时间，并减少非首屏资源的下载和渲染。

## Requirement 1：路由级拆包

- 公开首页、登录注册和所有应用页面按路由动态加载。
- 应用壳使用独立 Suspense fallback，不因子页面加载遮挡现有导航。
- 首页不得下载完整工作台的页面代码。

## Requirement 2：首屏与启动体验

- `index.html` 在 React 执行前显示轻量 VeyaShip 启动壳。
- 首屏以下内容使用 `content-visibility: auto` 延迟布局和绘制。
- 首页演示图片使用 `loading="lazy"` 与 `decoding="async"`。

## Requirement 3：网络与缓存

- `/assets/` 保持内容哈希长期缓存。
- `/fonts/` 与 `/demo/` 增加独立边缘缓存和浏览器缓存。
- 只有 `/api/v1/agent/` 关闭 Nginx 缓冲，其他页面恢复正常缓冲。
- 继续使用 HTTP/2、TLS 会话缓存和 gzip。

## Requirement 4：体积门禁

- 生产构建生成 Vite manifest。
- CI 检查“入口 + 首页 chunk + 字体”的初始 gzip 体积。
- 初始预算上限 250 KB gzip，单文件上限 120 KB gzip。

## 验收结果

- 初始首页资源从优化前约 544 KB gzip 降至 219 KB gzip。
- 路由入口约 58 KB gzip，首页业务 chunk 约 9 KB gzip。
- 公网法务页脚与完整法务正文拆分后，页脚共享包约 1 KB gzip。
- 118 个前端测试通过，类型检查和生产构建通过。
- 本地生产构建已用真实 Edge 验证首页、注册、仪表盘和教程懒加载路由，桌面 1440px 与移动端 390px 截图无溢出。

## SSR 决策

当前不迁移全站 SSR：

- 后端是独立 FastAPI，前端是 Vite SPA，迁移 SSR 会同时改造路由、鉴权、查询缓存和部署链路。
- 登录后工作台依赖浏览器 token、上传、媒体任务和 SSE，SSR 对这类交互页面收益有限。
- 当前最大瓶颈是整站 JS 首包和静态资源传输，路由拆包与边缘缓存能先覆盖主要问题。

后续 SEO 或公开营销页需要更强首屏时，优先做 Landing Page 的静态预渲染或 SSG，而不是全站 SSR。
