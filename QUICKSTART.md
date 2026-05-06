# PaperPulse 快速启动指南

## 🚀 启动应用

### 方法 1: 使用启动脚本（推荐）

```bash
./start.sh
```

### 方法 2: 手动启动

**启动后端：**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**启动前端（新终端）：**
```bash
cd frontend
npm run dev
```

## 🛑 停止应用

```bash
./stop.sh
```

或者手动停止：
```bash
pkill -f "uvicorn app.main:app"
pkill -f "next dev"
```

## 📍 访问地址

- **前端界面**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs

## 📊 添加示例数据

```bash
cd backend
source venv/bin/activate
python add_sample_data.py
```

## 🔧 配置说明

### 后端配置 (backend/.env)
- `DATABASE_URL`: 数据库连接（默认使用 SQLite）
- `SCHEDULER_ENABLED`: 是否启用自动抓取（默认关闭）
- `CORS_ORIGINS`: 允许的前端域名

### 前端配置 (frontend/.env.local)
- `NEXT_PUBLIC_API_URL`: 后端 API 地址

## 📝 当前状态

✅ 后端服务运行中（端口 8000）
✅ 前端服务运行中（端口 3000）
✅ 数据库已初始化
✅ 示例数据已添加

## 🎯 功能特性

- 📄 论文浏览与搜索
- 🔍 智能评分系统
- 📈 趋势分析
- 🏷️ 主题分类
- 📊 相似论文推荐

## 🆘 常见问题

**Q: 如何查看日志？**
```bash
# 后端日志
tail -f backend/backend.log

# 前端日志
tail -f frontend/frontend.log
```

**Q: 如何重启服务？**
```bash
./stop.sh
./start.sh
```

**Q: 如何添加 OpenAI API Key？**
编辑 `backend/.env` 文件，添加：
```
OPENAI_API_KEY=your_api_key_here
```

## 📚 更多信息

详细文档请查看 [README.md](README.md)
