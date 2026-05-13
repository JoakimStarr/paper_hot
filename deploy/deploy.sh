#!/bin/bash
# 轻量应用服务器部署脚本 (Ubuntu 22.04)

echo "=== 安装系统依赖 ==="
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip nodejs npm nginx

echo "=== 安装前端依赖 ==="
cd frontend
npm install
npm run build
cd ..

echo "=== 安装后端依赖 ==="
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

echo "=== 配置 Nginx ==="
sudo cp deploy/nginx.conf /etc/nginx/sites-available/paperpulse
sudo ln -sf /etc/nginx/sites-available/paperpulse /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

echo "=== 配置 systemd 服务 ==="
sudo cp deploy/backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable backend
sudo systemctl start backend

echo "=== 部署完成 ==="
echo "后端服务: http://your-server-ip:8000"
echo "前端应用: http://your-server-ip:3000"
