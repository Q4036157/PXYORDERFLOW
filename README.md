# PXYORDERFLOW

面向多交易所市场的开源订单流分析、执行与研究框架。首期支持 Lighter
公共行情，并提供交易所行情与交易接入的定制开发能力。

Open-source order-flow analytics, execution, and research framework. Lighter
market data is supported first, with adapter interfaces for additional venues.

## 在线体验

- 体验地址：https://pxy.xyz.hr/apps/orderflow/
- 当前状态：开发预览版，功能与接口会持续调整
- 真实交易：仅向授权测试账户开放

体验站为独立部署演示，并非 Lighter 或其他交易所的官方服务。

## 已有功能

- 60 档 DOM 价格梯子、盘口自动居中与一键被动限价单
- 多 Bar Footprint、3:1 Imbalance、POC、逐笔成交与独立 CVD 面板
- Working Orders、Positions、Fills 工作区与单笔撤单
- 图表拖动、缩放、十字光标以及桌面/手机响应式布局
- Lighter WebSocket 行情，异常时自动回退到 REST
- 默认启用 Post Only 的限价下单、撤单与全部撤单 Mock 流程
- 订单数量和名义金额风控门闩
- FastAPI、WebSocket、Vue 3 前后端结构
- 可扩展的 `TradeClient` 交易适配协议

## 快速启动

需要 Python 3.11+、Node.js 20+。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OF_MD_MODE = "mock"
$env:OF_TRADE_MODE = "mock"
$env:OF_TRADING = "true"  # 仅显式解锁本地 Mock 下单
python -m uvicorn app.main:app --host 127.0.0.1 --port 3811
```

另开一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:3810`。交易开关默认关闭；上面的显式开关只解锁
内存 Mock 流程，不会连接真实账户或发送真实订单。

使用 Lighter 公共行情：

```powershell
$env:OF_MD_MODE = "lighter"
```

## 交易所适配

公开仓库不包含任何私有网关、交易凭据或生产账户配置。接入真实交易时，
请在 `backend/app/trade/clients.py` 中实现 `TradeClient` 协议，并在服务端完成：

- 用户、租户与交易账户授权
- 凭据加密和密钥轮换
- 下单幂等、审计记录与风控限制
- WebSocket 事件按租户隔离
- 交易所限频、重试和错误映射

多租户设计要求见 [docs/MULTITENANCY.md](docs/MULTITENANCY.md)，适配开发约定见
[docs/EXCHANGE_ADAPTERS.md](docs/EXCHANGE_ADAPTERS.md)。

## 项目结构

```text
backend/   FastAPI、行情、订单流引擎、风控与交易适配协议
frontend/  Vue 3 价格梯子、Footprint、Tape 与下单界面
docs/      架构、多租户与交易所适配文档
tests/     不依赖外部服务的单元测试
scripts/   本地开发辅助脚本
```

## 参与开发

路线图见 [ROADMAP.md](ROADMAP.md)，提交代码前请阅读
[CONTRIBUTING.md](CONTRIBUTING.md)。欢迎通过 Issue 参与订单流算法、UI、回放、
交易所适配和测试建设。

量化交易相关定制开发与交易所接入：

- QQ：4036157
- 邮箱：4036157@qq.com

## 许可与风险声明

代码采用 [Apache License 2.0](LICENSE) 发布，依赖归属见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本项目用于软件开发、市场数据研究和技术演示，不承诺收益，不构成投资建议，
也不代管用户资金。真实交易具有损失风险，请先在模拟或测试账户验证。
