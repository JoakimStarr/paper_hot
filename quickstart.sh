#!/bin/bash

echo "🚀 Setting up PaperPulse..."

# Check if Docker is installed
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    echo "✅ Docker detected. Using Docker setup..."
    
    # Check for .env file
    if [ ! -f .env ]; then
        echo "📝 Creating .env file..."
        cat > .env << EOF
OPENAI_API_KEY=your_openai_api_key_here
EOF
        echo "⚠️  Please edit .env and add your OpenAI API key"
    fi
    
    echo "🐳 Starting services with Docker Compose..."
    docker-compose up -d
    
    echo "✅ PaperPulse is running!"
    echo "   Frontend: http://localhost:3000"
    echo "   Backend: http://localhost:8000"
    echo "   API Docs: http://localhost:8000/docs"
    
else
    echo "📦 Docker not found. Setting up manually..."
    
    # Setup backend
    echo "Setting up backend..."
    cd backend
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    pip install -r requirements.txt
    
    if [ ! -f ".env" ]; then
        cp .env.example .env
        echo "⚠️  Please edit backend/.env and add your configuration"
    fi
    
    cd ..
    
    # Setup frontend
    echo "Setting up frontend..."
    cd frontend
    npm install
    
    if [ ! -f ".env.local" ]; then
        echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api" > .env.local
    fi
    
    cd ..
    
    echo ""
    echo "✅ Setup complete!"
    echo ""
    echo "To start the application:"
    echo ""
    echo "1. Start PostgreSQL and create database:"
    echo "   createdb paperpulse"
    echo "   psql -d paperpulse -f database/init.sql"
    echo ""
    echo "2. Start the backend:"
    echo "   cd backend"
    echo "   source venv/bin/activate"
    echo "   uvicorn app.main:app --reload"
    echo ""
    echo "3. In a new terminal, start the frontend:"
    echo "   cd frontend"
    echo "   npm run dev"
    echo ""
    echo "4. Access the application:"
    echo "   Frontend: http://localhost:3000"
    echo "   Backend: http://localhost:8000"
fi
