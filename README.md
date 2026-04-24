# 自动签到脚本

使用 Playwright 和 ddddocr 实现的自动签到工具，支持网易滑块验证码自动识别。

## 功能

- 自动登录
- 滑块验证码自动识别（ddddocr）
- 自动签到
- GitHub Action 定时运行

## 环境要求

- Python 3.13+
- Playwright
- ddddocr

## 本地使用

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置账号

复制 `.env` 文件并填入账号密码：

```env
SIGN_IN_USERNAME=你的用户名
SIGN_IN_PASSWORD=你的密码
HEADLESS=True
```

### 3. 运行

```bash
python sign_in.py
```

## GitHub Action 部署

### 1. 添加 Secrets

在 GitHub 仓库设置 → Secrets and variables → Actions 中添加：

- `SIGN_IN_USERNAME` - 用户名
- `SIGN_IN_PASSWORD` - 密码

### 2. 自动运行

工作流会在每天北京时间 00:00 自动执行。

也可以手动触发：Actions → Sign In → Run workflow

## 目录结构

```
├── sign_in.py           # 主签到脚本
├── slider_solver.py     # 滑块验证码解决器
├── config/
│   └── settings.py      # 配置文件
├── .github/workflows/
│   └── sign-in.yml      # GitHub Action 工作流
├── .env                 # 环境变量（不提交）
└── requirements.txt     # Python 依赖
```

## 调试

有头模式运行（可以看到浏览器操作）：

```env
# .env 文件中设置
HEADLESS=False
```